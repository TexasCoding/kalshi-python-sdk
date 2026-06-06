"""Tests for the order-group FIX flow (GH #427)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.enums import OrderGroupAction
from kalshi.fix.messages import (
    OrderGroupRequest,
    OrderGroupResponse,
    decode_app_message,
)
from kalshi.fix.messages.base import FixMessage
from kalshi.fix.session import FixSession
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor

GID = "770e8400-e29b-41d4-a716-446655440002"


def _roundtrip(msg: FixMessage) -> FixMessage:
    full = [
        (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
        (int(Tag.MSG_SEQ_NUM), "1"),
        (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
        *msg.to_body_fields(),
    ]
    return type(msg).from_raw(decode(encode(full)))


def _wire(msg: FixMessage) -> str:
    return "|".join(f"{t}={v}" for t, v in msg.to_body_fields())


# ---------------------------------------------------------------------------
# Outbound: OrderGroupRequest (35=UOG) — golden wire per the docs examples
# ---------------------------------------------------------------------------


def test_order_group_create_golden_wire() -> None:
    msg = OrderGroupRequest.create(5000)
    # Create omits OrderGroupID (the server assigns it).
    assert _wire(msg) == "20131=1|20132=5000"
    assert int(Tag.ORDER_GROUP_ID) not in {t for t, _ in msg.to_body_fields()}
    assert _roundtrip(msg) == msg


def test_order_group_create_with_subaccount_golden_wire() -> None:
    assert _wire(OrderGroupRequest.create(5000, alloc_account=2)) == "20131=1|20132=5000|79=2"


def test_order_group_reset_golden_wire() -> None:
    assert _wire(OrderGroupRequest.reset(GID)) == f"20131=2|20130={GID}"


def test_order_group_delete_golden_wire() -> None:
    assert _wire(OrderGroupRequest.delete(GID)) == f"20131=3|20130={GID}"


def test_order_group_trigger_golden_wire() -> None:
    assert _wire(OrderGroupRequest.trigger(GID)) == f"20131=4|20130={GID}"


def test_order_group_update_golden_wire() -> None:
    assert _wire(OrderGroupRequest.update(GID, 2500)) == f"20131=5|20130={GID}|20132=2500"


@pytest.mark.parametrize(
    ("msg", "action"),
    [
        (OrderGroupRequest.create(1), OrderGroupAction.CREATE),
        (OrderGroupRequest.reset(GID), OrderGroupAction.RESET),
        (OrderGroupRequest.delete(GID), OrderGroupAction.DELETE),
        (OrderGroupRequest.trigger(GID), OrderGroupAction.TRIGGER_CANCEL),
        (OrderGroupRequest.update(GID, 9), OrderGroupAction.UPDATE),
    ],
)
def test_order_group_request_roundtrip(msg: OrderGroupRequest, action: OrderGroupAction) -> None:
    rt = _roundtrip(msg)
    assert rt == msg
    assert isinstance(rt, OrderGroupRequest)
    assert rt.order_group_action == action


# ---------------------------------------------------------------------------
# Inbound: OrderGroupResponse (35=UOH)
# ---------------------------------------------------------------------------


def test_order_group_response_roundtrip() -> None:
    msg = OrderGroupResponse(order_group_id=GID, order_group_contracts_limit=5000, alloc_account=2)
    back = _roundtrip(msg)
    assert back == msg
    assert isinstance(back, OrderGroupResponse)
    assert back.order_group_id == GID
    assert back.order_group_contracts_limit == 5000


def test_order_group_response_minimal() -> None:
    # Reset/Delete/Trigger responses echo only the id (no contracts limit).
    msg = OrderGroupResponse(order_group_id=GID)
    back = _roundtrip(msg)
    assert back == msg
    assert back.order_group_contracts_limit is None


def test_decode_app_message_order_group_response() -> None:
    msg = OrderGroupResponse(order_group_id=GID, order_group_contracts_limit=5000)
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), msg.MSG_TYPE.value),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                *msg.to_body_fields(),
            ]
        )
    )
    decoded = decode_app_message(raw)
    assert isinstance(decoded, OrderGroupResponse)
    assert decoded == msg


# ---------------------------------------------------------------------------
# Lifecycle against the mock acceptor
# ---------------------------------------------------------------------------


async def test_order_group_lifecycle(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=on_message
    )
    await session.start()
    try:
        # Create: the gateway assigns and returns the OrderGroupID.
        await session.send(OrderGroupRequest.create(5000))
        await until(lambda: acceptor.first("UOG") is not None)
        uog = acceptor.first("UOG")
        assert uog is not None
        assert uog.get(Tag.ORDER_GROUP_ACTION) == str(int(OrderGroupAction.CREATE))
        assert uog.get(Tag.ORDER_GROUP_CONTRACTS_LIMIT) == "5000"

        resp = OrderGroupResponse(order_group_id=GID, order_group_contracts_limit=5000)
        await acceptor.push("UOH", resp.to_body_fields(), seq=2)
        await until(lambda: len(received) == 1)
        decoded = decode_app_message(received[0])
        assert isinstance(decoded, OrderGroupResponse)
        assert decoded.order_group_id == GID

        # Delete the returned group.
        await session.send(OrderGroupRequest.delete(decoded.order_group_id or ""))
        await until(lambda: len([m for m in acceptor.received if m.msg_type == "UOG"]) == 2)
        delete_req = [m for m in acceptor.received if m.msg_type == "UOG"][1]
        assert delete_req.get(Tag.ORDER_GROUP_ACTION) == str(int(OrderGroupAction.DELETE))
        assert delete_req.get(Tag.ORDER_GROUP_ID) == GID
    finally:
        await session.close()

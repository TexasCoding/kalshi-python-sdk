"""Tests for inbound decode-error routing (GH #432).

``decode_app_message`` collapses "no registered model" and "registered but
malformed" to ``None``; ``decode_app_message_strict`` and ``FixSession``'s
``on_decode_error`` hook make the malformed case observable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from kalshi.fix.auth import FixSigner
from kalshi.fix.codec import RawMessage, decode, encode
from kalshi.fix.config import FixConfig, FixSessionType
from kalshi.fix.errors import FixDecodeError
from kalshi.fix.messages import (
    ExecutionReport,
    decode_app_message,
    decode_app_message_strict,
)
from kalshi.fix.session import FixSession
from kalshi.fix.tags import Tag

from .conftest import MockAcceptor


def _exec_report_raw(*body: tuple[int, str]) -> RawMessage:
    return decode(
        encode(
            [
                (int(Tag.MSG_TYPE), "8"),
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
                *body,
            ]
        )
    )


# ---------------------------------------------------------------------------
# decode_app_message_strict vs decode_app_message
# ---------------------------------------------------------------------------


def test_strict_decode_valid_message() -> None:
    msg = decode_app_message_strict(_exec_report_raw((int(Tag.AVG_PX), "0.66")))
    assert isinstance(msg, ExecutionReport)
    assert msg.avg_px == Decimal("0.66")


def test_strict_decode_malformed_raises() -> None:
    raw = _exec_report_raw((int(Tag.AVG_PX), "notanumber"))  # bad Decimal
    with pytest.raises(FixDecodeError) as ei:
        decode_app_message_strict(raw)
    assert ei.value.msg_type == "8"
    assert ei.value.raw is raw
    assert ei.value.__cause__ is not None  # underlying validation error chained


def test_strict_decode_unregistered_returns_none() -> None:
    # An admin / unregistered MsgType has no model — None, not raised.
    raw = decode(
        encode(
            [
                (int(Tag.MSG_TYPE), "0"),  # Heartbeat
                (int(Tag.MSG_SEQ_NUM), "2"),
                (int(Tag.SENDING_TIME), "20250101-00:00:00.000"),
            ]
        )
    )
    assert decode_app_message_strict(raw) is None


def test_decode_app_message_still_swallows_malformed() -> None:
    # The lenient contract is unchanged: malformed -> None (logged, not raised).
    assert decode_app_message(_exec_report_raw((int(Tag.AVG_PX), "notanumber"))) is None


# ---------------------------------------------------------------------------
# FixSession on_decode_error routing
# ---------------------------------------------------------------------------


async def test_session_routes_decode_error(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []
    errors: list[tuple[RawMessage, FixDecodeError]] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    async def on_decode_error(raw: RawMessage, exc: FixDecodeError) -> None:
        errors.append((raw, exc))

    session = FixSession(
        fix_signer,
        fix_config,
        FixSessionType.ORDER_ENTRY_NR,
        on_message=on_message,
        on_decode_error=on_decode_error,
    )
    await session.start()
    try:
        await acceptor.push("8", [(int(Tag.AVG_PX), "notanumber")], seq=2)
        await until(lambda: bool(errors))
        err_raw, exc = errors[0]
        assert isinstance(exc, FixDecodeError)
        assert exc.msg_type == "8"
        assert err_raw.msg_type == "8"
        # The raw message is still delivered to on_message — nothing silently lost.
        await until(lambda: bool(received))
        assert received[0].msg_type == "8"
    finally:
        await session.close()


async def test_session_no_decode_error_on_valid_message(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    received: list[RawMessage] = []
    errors: list[tuple[RawMessage, FixDecodeError]] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    async def on_decode_error(raw: RawMessage, exc: FixDecodeError) -> None:
        errors.append((raw, exc))

    session = FixSession(
        fix_signer,
        fix_config,
        FixSessionType.ORDER_ENTRY_NR,
        on_message=on_message,
        on_decode_error=on_decode_error,
    )
    await session.start()
    try:
        await acceptor.push("8", [(int(Tag.ORDER_ID), "OID-1")], seq=2)
        await until(lambda: bool(received))
        assert errors == []  # a valid ExecutionReport does not trigger the hook
    finally:
        await session.close()


async def test_session_without_hook_delivers_raw_on_malformed(
    fix_signer: FixSigner,
    fix_config: FixConfig,
    acceptor: MockAcceptor,
    until: Callable[..., Awaitable[None]],
) -> None:
    # No on_decode_error: behaviour is unchanged — the raw still reaches
    # on_message and the session survives the malformed payload.
    received: list[RawMessage] = []

    async def on_message(raw: RawMessage) -> None:
        received.append(raw)

    session = FixSession(
        fix_signer, fix_config, FixSessionType.ORDER_ENTRY_NR, on_message=on_message
    )
    await session.start()
    try:
        await acceptor.push("8", [(int(Tag.AVG_PX), "notanumber")], seq=2)
        await until(lambda: bool(received))
        assert received[0].msg_type == "8"
        assert session.state.value == "active"
    finally:
        await session.close()

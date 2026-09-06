"""End-to-end channel tests: subscribe helper -> fake server frame -> typed model.

Drives the six typed ``subscribe_*`` helpers through the FakePerpsWS server and
asserts the dispatched frame arrives as the correct ``Margin*Message`` model.
Also verifies the orderbook-apply seam in ``_process_frame`` feeds the
:class:`PerpsOrderbookManager`.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from kalshi.perps.config import PerpsConfig
from kalshi.perps.ws import PerpsWebSocket
from kalshi.perps.ws.models.fill import MarginFillMessage
from kalshi.perps.ws.models.order_group import OrderGroupUpdatesMessage
from kalshi.perps.ws.models.orderbook import (
    MarginOrderbookDeltaMessage,
    MarginOrderbookSnapshotMessage,
)
from kalshi.perps.ws.models.ticker import MarginTickerMessage
from kalshi.perps.ws.models.trade import MarginTradeMessage
from kalshi.perps.ws.models.user_orders import MarginUserOrderMessage

from .conftest import FakePerpsWS

pytestmark = pytest.mark.asyncio


async def _sid(fake: FakePerpsWS) -> int:
    return next(iter(fake.subscriptions))


async def test_subscribe_ticker_yields_typed_message(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_ticker(tickers=["BTC-PERP"])
        sid = await _sid(fake_perps_ws)
        await fake_perps_ws.send_to_all({
            "type": "ticker", "sid": sid,
            "msg": {
                "market_ticker": "BTC-PERP", "price": "100.0000",
                "bid": "99.5000", "ask": "100.5000",
                "bid_size_fp": "10.00", "ask_size_fp": "12.00",
                "last_trade_size_fp": "1.00", "volume": "1000.00",
                "volume_24h": "5000.00", "open_interest": "200.00",
                "volume_notional_value_dollars": "100000.0000",
                "volume_24h_notional_value_dollars": "500000.0000",
                "open_interest_notional_value_dollars": "20000.0000",
                "funding_rate": {"rate": 0.0001, "next_funding_time_ms": 1, "ts_ms": 2},
                "ts_ms": 1700000000000,
            },
        })
        frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(frame, MarginTickerMessage)
        assert frame.msg.funding_rate is not None
        assert frame.msg.funding_rate.rate == Decimal("0.0001")


async def test_subscribe_trade_yields_typed_message(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_trade(tickers=["BTC-PERP"])
        sid = await _sid(fake_perps_ws)
        await fake_perps_ws.send_to_all({
            "type": "trade", "sid": sid,
            "msg": {
                "trade_id": "t1", "market_ticker": "BTC-PERP",
                "price": "100.0000", "count": "5.00",
                "taker_side": "ask", "ts_ms": 1700000000000,
            },
        })
        frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(frame, MarginTradeMessage)
        assert frame.msg.taker_side == "ask"


async def test_subscribe_fill_yields_typed_message(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_fill()
        sid = await _sid(fake_perps_ws)
        await fake_perps_ws.send_to_all({
            "type": "fill", "sid": sid,
            "msg": {
                "trade_id": "t1", "order_id": "o1", "market_ticker": "BTC-PERP",
                "is_taker": True, "side": "bid", "ts_ms": 1700000000000,
                "price": "100.0000", "count": "5.00",
                "fee_cost": "0.0500", "post_position": "15.00",
                "order_source": "user",
            },
        })
        frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(frame, MarginFillMessage)
        assert frame.msg.post_position == Decimal("15.00")


async def test_subscribe_user_orders_yields_typed_message(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_user_orders()
        sid = await _sid(fake_perps_ws)
        # Subscribe channel is user_orders; envelope type is user_order.
        await fake_perps_ws.send_to_all({
            "type": "user_order", "sid": sid,
            "msg": {
                "order_id": "o1", "user_id": "u1", "client_order_id": "c1",
                "ticker": "BTC-PERP", "side": "ask", "price": "100.0000",
                "fill_count": "2.00", "remaining_count": "8.00",
                "created_ts_ms": 1700000000000, "order_source": "user",
            },
        })
        frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(frame, MarginUserOrderMessage)
        assert frame.msg.ticker == "BTC-PERP"


async def test_subscribe_order_group_yields_typed_message(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_order_group()
        sid = await _sid(fake_perps_ws)
        await fake_perps_ws.send_to_all({
            "type": "order_group_updates", "sid": sid, "seq": 1,
            "msg": {
                "event_type": "limit_updated", "order_group_id": "og_1",
                "contracts_limit_fp": "150.00", "ts_ms": 1700000000000,
            },
        })
        frame = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(frame, OrderGroupUpdatesMessage)
        assert frame.msg.contracts_limit == Decimal("150.00")


async def test_stale_order_group_updates_for_unmapped_sid_dropped(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    # #411: order_group_updates is sequenced (carries `seq`), so a stale frame
    # for a sid with no current subscription must be dropped BEFORE seq tracking.
    # Otherwise track_sync() re-arms the watermark for the dead/recycled sid and
    # manufactures a spurious gap on a later subscription to that sid.
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        assert session._sub_mgr is not None and session._seq_tracker is not None
        unmapped_sid = 9999
        assert session._sub_mgr.get_subscription_by_sid(unmapped_sid) is None
        raw = json.dumps({
            "type": "order_group_updates", "sid": unmapped_sid, "seq": 7,
            "msg": {
                "event_type": "limit_updated", "order_group_id": "og",
                "contracts_limit_fp": "10.00", "ts_ms": 1700000000000,
            },
        })
        await session._process_frame(raw)
        # The stale frame must NOT have armed the watermark for the unmapped sid.
        assert session._seq_tracker.peek(unmapped_sid) is None


async def test_subscribe_orderbook_delta_snapshot_then_delta(
    fake_perps_ws: FakePerpsWS, perps_ws_config: PerpsConfig, perps_auth
) -> None:
    ws = PerpsWebSocket(auth=perps_auth, config=perps_ws_config)
    async with ws.connect() as session:
        stream = await session.subscribe_orderbook_delta(tickers=["BTC-PERP"])
        sid = await _sid(fake_perps_ws)
        # Forces send_initial_snapshot=True on the wire.
        cmd = fake_perps_ws.received_commands[-1]
        assert cmd["params"]["send_initial_snapshot"] is True

        await fake_perps_ws.send_to_all({
            "type": "orderbook_snapshot", "sid": sid, "seq": 1,
            "msg": {
                "market_ticker": "BTC-PERP",
                "bid": [["100.0000", "10.00"]],
                "ask": [["101.0000", "5.00"]],
            },
        })
        snap = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(snap, MarginOrderbookSnapshotMessage)
        assert snap.msg.bid == {Decimal("100.0000"): Decimal("10.00")}

        # The orderbook-apply seam fed the manager.
        book = session._orderbook_mgr.get("BTC-PERP")  # type: ignore[union-attr]
        assert book is not None
        assert book.bids[0].price == Decimal("100.0000")

        await fake_perps_ws.send_to_all({
            "type": "orderbook_delta", "sid": sid, "seq": 2,
            "msg": {
                "market_ticker": "BTC-PERP", "price": "100.0000",
                "delta": "-4.00", "side": "bid", "ts_ms": 1700000000000,
            },
        })
        delta = await asyncio.wait_for(stream.__anext__(), timeout=2.0)
        assert isinstance(delta, MarginOrderbookDeltaMessage)
        assert delta.msg.delta == Decimal("-4.00")

        book2 = session._orderbook_mgr.get("BTC-PERP")  # type: ignore[union-attr]
        assert book2 is not None
        assert book2.bids[0].quantity == Decimal("6.00")

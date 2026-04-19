"""Provoke a user_order frame on demo WS by placing and canceling a tiny order.

Subscribes to the user_orders channel on demo (raw WS, not the SDK dispatcher),
places a far-OTM non-marketable limit order via REST, waits briefly, cancels
the order, and prints every raw frame it sees as JSONL.

Used by v0.14.0 envelope-drift evidence gathering when demo is otherwise idle
(no existing orders to trigger user_order events). The captured `type` value
is the source of truth for whether demo emits 'user_order' (spec singular) or
'user_orders' (plural). Does NOT use the SDK dispatcher — raw wire only.

Usage:
    uv run python scripts/ws_provoke_user_order.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

# Bridge .env-style KALSHI_DEMO_* to KALSHI_* (same pattern as ws_capture.py).
if os.environ.get("KALSHI_DEMO_KEY_ID") and not os.environ.get("KALSHI_KEY_ID"):
    os.environ["KALSHI_KEY_ID"] = os.environ["KALSHI_DEMO_KEY_ID"]
if os.environ.get("KALSHI_DEMO_PRIVATE_KEY_PATH") and not os.environ.get(
    "KALSHI_PRIVATE_KEY_PATH"
):
    _path = os.environ["KALSHI_DEMO_PRIVATE_KEY_PATH"]
    if not os.path.isabs(_path):
        _path = str((_ROOT / _path).resolve())
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = _path
os.environ.setdefault("KALSHI_DEMO", "true")

from kalshi.auth import KalshiAuth  # noqa: E402
from kalshi.client import KalshiClient  # noqa: E402
from kalshi.config import KalshiConfig  # noqa: E402
from kalshi.ws.connection import ConnectionManager  # noqa: E402


async def run() -> int:
    base_url = os.environ.get("KALSHI_BASE_URL", "https://demo-api.kalshi.co/trade-api/v2")
    if "demo" not in base_url:
        print(f"refusing non-demo base url: {base_url}", file=sys.stderr)
        return 2

    ws_url = (
        base_url.replace("https://", "wss://").replace("/trade-api/v2", "/trade-api/ws/v2")
    )
    config = KalshiConfig(base_url=base_url, ws_base_url=ws_url)
    auth = KalshiAuth.from_env()

    # REST client for order placement.
    rest = KalshiClient.from_env(demo=True)

    # Pick an open market.
    page = rest.markets.list(status="open", limit=1)
    if not page.items:
        print("no open markets on demo", file=sys.stderr)
        return 3
    ticker = page.items[0].ticker
    print(f"probe market: {ticker}", file=sys.stderr)

    conn = ConnectionManager(auth=auth, config=config)
    try:
        await conn.connect()
        await conn.send({
            "id": 1,
            "cmd": "subscribe",
            "params": {"channels": ["user_orders"]},
        })

        # Drain the subscribe ack before placing the order so the ack doesn't
        # crowd the first frames we care about.
        raw = await asyncio.wait_for(conn.recv(), timeout=5.0)
        print(raw, flush=True)

        # Place far-OTM non-marketable limit order (will rest on the book).
        order = rest.orders.create(
            ticker=ticker, side="yes", action="buy", count=1, yes_price="0.01"
        )
        print(f"placed: {order.order_id}", file=sys.stderr)

        # Capture frames for 3s after placement.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(conn.recv(), timeout=deadline - time.monotonic())
            except TimeoutError:
                break
            print(raw, flush=True)

        # Cancel.
        rest.orders.cancel(order.order_id)
        print(f"canceled: {order.order_id}", file=sys.stderr)

        # Capture frames for another 3s after cancel.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(conn.recv(), timeout=deadline - time.monotonic())
            except TimeoutError:
                break
            print(raw, flush=True)
    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

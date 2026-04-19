"""Dump raw WS frames from demo for a single channel.

Usage:
    uv run python scripts/ws_capture.py <channel> [--params KEY=VALUE ...]
        [--count N] [--timeout SEC]

Prints one JSON object per line (JSONL) to stdout until count or timeout.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.ws.connection import ConnectionManager


async def capture(
    channel: str,
    params: dict[str, object],
    count: int,
    timeout: float,
) -> int:
    base_url = os.environ.get("KALSHI_BASE_URL", "https://demo-api.kalshi.co/trade-api/v2")
    if "demo" not in base_url:
        print(f"refusing non-demo base url: {base_url}", file=sys.stderr)
        return 2

    ws_url = (
        base_url.replace("https://", "wss://").replace("/trade-api/v2", "/trade-api/ws/v2")
    )
    config = KalshiConfig(base_url=base_url, ws_base_url=ws_url)
    auth = KalshiAuth.from_env()

    conn = ConnectionManager(auth=auth, config=config)
    try:
        await conn.connect()

        subscribe: dict[str, object] = {
            "id": 1,
            "cmd": "subscribe",
            "params": {"channels": [channel], **params},
        }
        await conn.send(subscribe)

        received = 0
        deadline = time.monotonic() + timeout

        while received < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(conn.recv(), timeout=remaining)
            except TimeoutError:
                break
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                print(raw, flush=True)
                continue
            print(raw, flush=True)
            if parsed.get("type") not in ("subscribed", "ok", "error"):
                received += 1
    finally:
        await conn.close()

    return 0 if received > 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dump raw WS frames from demo for a single channel."
    )
    ap.add_argument("channel")
    ap.add_argument("--params", nargs="*", default=[], help="KEY=VALUE pairs")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=15.0)
    args = ap.parse_args()

    params: dict[str, object] = {}
    for kv in args.params:
        k, _, v = kv.partition("=")
        if v.startswith("[") and v.endswith("]"):
            params[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            params[k] = v

    return asyncio.run(capture(args.channel, params, args.count, args.timeout))


if __name__ == "__main__":
    raise SystemExit(main())

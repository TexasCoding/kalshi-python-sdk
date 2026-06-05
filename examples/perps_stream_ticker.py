"""Stream the perps ``ticker`` channel and print live funding mechanics.

Connects to the perps margin WebSocket and prints each ticker update's
``funding_rate`` and ``next_funding_time_ms`` (the perpetual-futures funding
tether) as messages arrive.

Run:
    python examples/perps_stream_ticker.py [TICKER]

Required environment variables:
    KALSHI_PERPS_KEY_ID
    KALSHI_PERPS_PRIVATE_KEY_PATH
"""

from __future__ import annotations

import asyncio
import os
import sys

from kalshi.auth import KalshiAuth
from kalshi.perps import PerpsConfig, PerpsWebSocket


async def main() -> None:
    key_id = os.environ.get("KALSHI_PERPS_KEY_ID")
    key_path = os.environ.get("KALSHI_PERPS_PRIVATE_KEY_PATH")
    if not key_id or not key_path:
        raise SystemExit("Set KALSHI_PERPS_KEY_ID + KALSHI_PERPS_PRIVATE_KEY_PATH first.")

    ticker = sys.argv[1] if len(sys.argv) > 1 else "BTC-PERP"
    auth = KalshiAuth.from_key_path(key_id, key_path)
    ws = PerpsWebSocket(auth=auth, config=PerpsConfig.demo())

    async with ws.connect() as session:
        async for msg in await session.subscribe_ticker(tickers=[ticker]):
            fr = msg.msg.funding_rate
            if fr is not None:
                print(
                    f"{msg.msg.market_ticker} funding_rate={fr.rate} "
                    f"next={fr.next_funding_time_ms}"
                )
            else:
                print(f"{msg.msg.market_ticker} price={msg.msg.price} (no funding update)")
    auth.close()


if __name__ == "__main__":
    asyncio.run(main())

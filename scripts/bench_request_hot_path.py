"""Microbench for the REST request hot path.

Wires a respx mock transport so every ``client.markets.list(limit=10)``
short-circuits without touching the network, and measures requests/sec
for the sync and async clients. Catches regressions in per-request
allocations / sign overhead.

Usage::

    uv run python scripts/bench_request_hot_path.py [--requests N]
"""

from __future__ import annotations

import argparse
import asyncio
import time

import httpx
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import KalshiConfig

_MOCK_RESPONSE = {"markets": [], "cursor": ""}


def _make_auth() -> KalshiAuth:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return KalshiAuth(key_id="bench", private_key=key)


def _config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://bench.kalshi.com/trade-api/v2",
        max_retries=0,
        timeout=5.0,
    )


def _bench_sync(requests_n: int) -> float:
    with respx.mock:
        respx.get("https://bench.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json=_MOCK_RESPONSE)
        )
        client = KalshiClient(auth=_make_auth(), config=_config())
        try:
            t0 = time.perf_counter()
            for _ in range(requests_n):
                client.markets.list(limit=10)
            return time.perf_counter() - t0
        finally:
            client.close()


async def _bench_async(requests_n: int) -> float:
    with respx.mock:
        respx.get("https://bench.kalshi.com/trade-api/v2/markets").mock(
            return_value=httpx.Response(200, json=_MOCK_RESPONSE)
        )
        client = AsyncKalshiClient(auth=_make_auth(), config=_config())
        try:
            t0 = time.perf_counter()
            for _ in range(requests_n):
                await client.markets.list(limit=10)
            return time.perf_counter() - t0
        finally:
            await client.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--requests", type=int, default=2000)
    args = p.parse_args()

    sync_elapsed = _bench_sync(args.requests)
    print(f"sync  : {args.requests} reqs in {sync_elapsed * 1000:.1f} ms "
          f"({args.requests / sync_elapsed:,.0f} req/s)")

    async_elapsed = asyncio.run(_bench_async(args.requests))
    print(f"async : {args.requests} reqs in {async_elapsed * 1000:.1f} ms "
          f"({args.requests / async_elapsed:,.0f} req/s)")


if __name__ == "__main__":
    main()

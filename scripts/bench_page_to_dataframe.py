"""Microbench for :meth:`Page.to_dataframe` / :meth:`Page.to_polars` (#271 item 4).

A 1000-item Page of :class:`Market` instances is built once, then handed
to pandas and polars in turn. Catches regressions in the column-oriented
build path (#264) and confirms the Decimal contract (#225/#190) doesn't
silently fall back to per-row ``model_dump``.

Usage::

    uv run python scripts/bench_page_to_dataframe.py [--rows N]
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import time
from typing import Any

from kalshi.models.common import Page
from kalshi.models.markets import Market


def _market_dict(ticker: str) -> dict[str, Any]:
    """Spec-shaped wire dict; mirrors ``tests/_model_fixtures.market_dict`` so
    bench scripts don't pull a tests-only helper."""
    return {
        "ticker": ticker,
        "event_ticker": "EVT-A",
        "market_type": "binary",
        "yes_sub_title": "Yes",
        "no_sub_title": "No",
        "status": "open",
        "yes_bid_dollars": "0.5000",
        "yes_ask_dollars": "0.5100",
        "no_bid_dollars": "0.4900",
        "no_ask_dollars": "0.5000",
        "last_price_dollars": "0.5000",
        "previous_yes_bid_dollars": "0.5000",
        "previous_yes_ask_dollars": "0.5100",
        "previous_price_dollars": "0.5000",
        "notional_value_dollars": "1.0000",
        "liquidity_dollars": "100.0000",
        "yes_bid_size_fp": "0.00",
        "yes_ask_size_fp": "0.00",
        "volume_fp": "0.00",
        "volume_24h_fp": "0.00",
        "open_interest_fp": "0.00",
        "created_time": "2026-01-01T00:00:00Z",
        "updated_time": "2026-01-01T00:00:00Z",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-12-31T23:59:59Z",
        "latest_expiration_time": "2026-12-31T23:59:59Z",
        "settlement_timer_seconds": 0,
        "result": "",
        "can_close_early": False,
        "fractional_trading_enabled": False,
        "expiration_value": "",
        "rules_primary": "",
        "rules_secondary": "",
        "price_level_structure": "binary",
        "price_ranges": [],
    }


def _build_page(rows: int) -> Page[Market]:
    items = [Market.model_validate(_market_dict(f"BENCH-{i:05d}")) for i in range(rows)]
    return Page[Market](items=items, cursor=None)


def _time_call(fn: Any, repeats: int) -> float:
    gc.collect()
    t0 = time.perf_counter()
    for _ in range(repeats):
        fn()
    return time.perf_counter() - t0


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--rows", type=int, default=1_000)
    p.add_argument("--repeats", type=int, default=10)
    args = p.parse_args()

    page = _build_page(args.rows)
    total_conversions = args.rows * args.repeats

    pandas_available = importlib.util.find_spec("pandas") is not None
    polars_available = importlib.util.find_spec("polars") is not None

    if pandas_available:
        elapsed = _time_call(page.to_dataframe, args.repeats)
        rate = total_conversions / elapsed if elapsed > 0 else float("inf")
        print(
            f"pandas: rows={args.rows} repeats={args.repeats} "
            f"elapsed={elapsed * 1000:.1f} ms rate={rate:,.0f} rows/sec"
        )
    else:
        print("pandas: not installed (skip — install kalshi-sdk[pandas])")

    if polars_available:
        elapsed = _time_call(page.to_polars, args.repeats)
        rate = total_conversions / elapsed if elapsed > 0 else float("inf")
        print(
            f"polars: rows={args.rows} repeats={args.repeats} "
            f"elapsed={elapsed * 1000:.1f} ms rate={rate:,.0f} rows/sec"
        )
    else:
        print("polars: not installed (skip — install kalshi-sdk[polars])")


if __name__ == "__main__":
    main()

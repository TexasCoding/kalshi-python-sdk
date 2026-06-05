"""Place (and immediately cancel) a resting margin order on the perps demo exchange.

Demonstrates the standalone ``PerpsClient`` order flow with a safe, non-marketable
limit price (far from the market) so the order rests rather than fills.

Run:
    python examples/perps_create_order.py

Required environment variables (perps-specific — separate from the KALSHI_* vars):
    KALSHI_PERPS_KEY_ID
    KALSHI_PERPS_PRIVATE_KEY_PATH   (or KALSHI_PERPS_PRIVATE_KEY)
Optional:
    KALSHI_PERPS_DEMO=true          (defaulted on below; this example always uses demo)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from kalshi import PerpsClient


def main() -> None:
    # Always demo for this example — never place real orders from a sample script.
    with PerpsClient.from_env(demo=True) as perps:
        if not perps.is_authenticated:
            raise SystemExit("Set KALSHI_PERPS_KEY_ID + KALSHI_PERPS_PRIVATE_KEY_PATH first.")
        if not perps.exchange.enabled().enabled:
            raise SystemExit("This account is not margin-enabled on demo.")

        markets = perps.markets.list(status="active")
        if not markets:
            raise SystemExit("No active margin markets on demo right now.")
        ticker = markets[0].ticker

        # A bid far below market rests; it will not fill.
        order = perps.orders.create(
            ticker=ticker,
            client_order_id=str(uuid.uuid4()),
            side="bid",
            count="1",
            price=Decimal("0.0100"),
            time_in_force="good_till_canceled",
            self_trade_prevention_type="taker_at_cross",
        )
        print(f"created resting order {order.order_id} (remaining={order.remaining_count})")

        cancelled = perps.orders.cancel(order.order_id)
        print(f"cancelled {cancelled.order_id} (reduced_by={cancelled.reduced_by})")


if __name__ == "__main__":
    main()

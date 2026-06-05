"""Print perps margin balance and per-position risk.

Calls ``GetMarginBalance`` and ``GetMarginRisk`` and prints the account's balance
breakdown, maintenance-margin requirement, leverage, and per-position estimated
liquidation prices.

Run:
    python examples/perps_balance_risk.py

Required environment variables:
    KALSHI_PERPS_KEY_ID
    KALSHI_PERPS_PRIVATE_KEY_PATH
"""

from __future__ import annotations

from kalshi import PerpsClient


def main() -> None:
    with PerpsClient.from_env(demo=True) as perps:
        if not perps.is_authenticated:
            raise SystemExit("Set KALSHI_PERPS_KEY_ID + KALSHI_PERPS_PRIVATE_KEY_PATH first.")

        bal = perps.margin.balance(compute_available_balance=True)
        print(f"settled funds: {bal.settled_funds}")
        for sub in bal.subaccount_balances:
            print(
                f"  subaccount {sub.subaccount}: equity={sub.account_equity} "
                f"position_value={sub.position_value} "
                f"maintenance_margin={sub.maintenance_margin} "
                f"available={sub.available_balance}"
            )

        risk = perps.margin.risk()
        print(f"account leverage: {risk.account_leverage}")
        print(
            f"total notional={risk.total_position_notional} "
            f"total maintenance_margin={risk.total_maintenance_margin}"
        )
        for pos in risk.positions:
            print(
                f"  {pos.market_ticker}: position={pos.position} "
                f"leverage={pos.position_leverage} "
                f"est_liq_price={pos.estimated_liquidation_price}"
            )


if __name__ == "__main__":
    main()

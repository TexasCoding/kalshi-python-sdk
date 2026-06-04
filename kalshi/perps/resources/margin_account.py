"""Perps margin-account resource — balance, risk, notional risk limit, fee tiers.

Stub wired by the foundation issue (#388); endpoints implemented in #394.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class MarginAccountResource(SyncResource):
    """Sync perps margin-account API (balance / risk / notional_risk_limit / fee_tiers)."""


class AsyncMarginAccountResource(AsyncResource):
    """Async perps margin-account API (balance / risk / notional_risk_limit / fee_tiers)."""

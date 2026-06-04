"""Perps funding resource — rate estimate, historical rates, payment history.

Stub wired by the foundation issue (#388); endpoints implemented in #395.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class FundingResource(SyncResource):
    """Sync perps funding API (``rate_estimate`` / ``historical_rates`` / ``history``)."""


class AsyncFundingResource(AsyncResource):
    """Async perps funding API (``rate_estimate`` / ``historical_rates`` / ``history``)."""

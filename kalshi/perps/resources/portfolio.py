"""Perps portfolio resource — positions, fills, trades.

Stub wired by the foundation issue (#388); endpoints implemented in #393.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class PerpsPortfolioResource(SyncResource):
    """Sync perps portfolio API (``positions`` / ``fills`` / ``trades`` + paginators)."""


class AsyncPerpsPortfolioResource(AsyncResource):
    """Async perps portfolio API (``positions`` / ``fills`` / ``trades`` + paginators)."""

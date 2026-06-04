"""Perps markets resource — list/get, orderbook, candlesticks.

Stub wired by the foundation issue (#388); endpoints implemented in #390.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class PerpsMarketsResource(SyncResource):
    """Sync perps markets API (``list`` / ``get`` / ``orderbook`` / ``candlesticks``)."""


class AsyncPerpsMarketsResource(AsyncResource):
    """Async perps markets API (``list`` / ``get`` / ``orderbook`` / ``candlesticks``)."""

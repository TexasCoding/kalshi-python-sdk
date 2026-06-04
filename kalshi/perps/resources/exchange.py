"""Perps exchange resource — status, margin-enabled gate, risk parameters.

Stub wired by the foundation issue (#388); endpoints implemented in #389.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class PerpsExchangeResource(SyncResource):
    """Sync perps exchange API (``status`` / ``enabled`` / ``risk_parameters``)."""


class AsyncPerpsExchangeResource(AsyncResource):
    """Async perps exchange API (``status`` / ``enabled`` / ``risk_parameters``)."""

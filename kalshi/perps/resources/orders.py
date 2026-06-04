"""Perps orders resource — create/get/list/cancel/decrease/amend + FCM orders.

Stub wired by the foundation issue (#388); endpoints implemented in #391.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class MarginOrdersResource(SyncResource):
    """Sync perps orders API (create/get/list/cancel/decrease/amend + FCM orders)."""


class AsyncMarginOrdersResource(AsyncResource):
    """Async perps orders API (create/get/list/cancel/decrease/amend + FCM orders)."""

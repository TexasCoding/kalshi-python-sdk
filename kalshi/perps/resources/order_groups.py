"""Perps order-groups resource — create/get/list/delete/reset/trigger/update-limit.

Stub wired by the foundation issue (#388); endpoints implemented in #392.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class OrderGroupsResource(SyncResource):
    """Sync perps order-groups API (rolling 15-second contracts-limit groups)."""


class AsyncOrderGroupsResource(AsyncResource):
    """Async perps order-groups API (rolling 15-second contracts-limit groups)."""

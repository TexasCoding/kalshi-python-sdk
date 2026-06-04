"""Perps transfers & subaccounts resource.

Intra-exchange-instance transfer, create margin subaccount, transfer between
margin subaccounts. Stub wired by the foundation issue (#388); endpoints
implemented in #396.
"""

from __future__ import annotations

from kalshi.resources._base import AsyncResource, SyncResource


class TransfersResource(SyncResource):
    """Sync perps transfers API (transfer_instance / create_subaccount / transfer_subaccount)."""


class AsyncTransfersResource(AsyncResource):
    """Async perps transfers API (transfer_instance / create_subaccount / transfer_subaccount)."""

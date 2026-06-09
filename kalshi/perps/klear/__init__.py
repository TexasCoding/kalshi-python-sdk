"""Kalshi Self-Clearing-Member (SCM) "Klear" API.

The Klear API (``klear-api/v1``) authenticates with a pre-generated Bearer token
passed as ``Authorization: Bearer <admin_user_id>:<access_token>`` on every
request — a different auth model from the RSA-PSS signing used by the prediction
and perps trade-api surfaces. It is therefore exposed via standalone
:class:`KlearClient` / :class:`AsyncKlearClient` with their own
:class:`KlearConfig` and a :class:`KlearAuth` Bearer-credential holder.

Security: the ``access_token`` is a secret — it is never logged, never placed in
exception messages, and redacted from ``repr()``.
"""

from __future__ import annotations

from kalshi.perps.klear.async_client import AsyncKlearClient
from kalshi.perps.klear.auth import KlearAuth
from kalshi.perps.klear.client import KlearClient
from kalshi.perps.klear.config import (
    DEMO_KLEAR_URL,
    PRODUCTION_KLEAR_URL,
    KlearConfig,
)
from kalshi.perps.klear.models.common import Error

__all__ = [
    "DEMO_KLEAR_URL",
    "PRODUCTION_KLEAR_URL",
    "AsyncKlearClient",
    "Error",
    "KlearAuth",
    "KlearClient",
    "KlearConfig",
]

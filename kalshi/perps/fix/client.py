"""Margin (perps) FIX client facade.

A thin product facade over the shared FIX core in :mod:`kalshi.fix`. The Kalshi
FIX dictionary is identical across products, so the margin client reuses the
same codec / session engine / message models; it differs only in:

* product = margin (host/port tables resolve to the ``margin-*`` endpoints),
* ``UseDollars`` is always on (fixed-point dollar pricing — enforced by
  :class:`~kalshi.fix.config.FixConfig` for the margin product),
* available sessions are NR / RT / DC / MD (no post-trade or RFQ),
* credentials come from the separate ``KALSHI_PERPS_*`` env vars, matching the
  perps REST/WS clients.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable

from kalshi.errors import KalshiAuthError
from kalshi.fix.auth import FixSigner
from kalshi.fix.client import _BaseFixClient
from kalshi.fix.config import FixConfig, FixEnvironment, FixProduct
from kalshi.perps._env import try_perps_auth_from_env


class MarginFixClient(_BaseFixClient):
    """FIX client for the margin (perps) gateway.

    Supports order entry (NR/RT), drop copy, and market data. Construct from a
    :class:`~kalshi.fix.auth.FixSigner`, from an existing
    :class:`~kalshi.auth.KalshiAuth` via :meth:`from_auth`, or from the
    ``KALSHI_PERPS_*`` environment via :meth:`from_env`.
    """

    _PRODUCT = FixProduct.MARGIN

    @classmethod
    def from_env(
        cls,
        *,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        config: FixConfig | None = None,
        ssl_context: ssl.SSLContext | None = None,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> MarginFixClient:
        """Build a margin FIX client from the ``KALSHI_PERPS_*`` environment vars."""
        auth = try_perps_auth_from_env(password=password)
        if auth is None:
            raise KalshiAuthError(
                "Margin FIX requires KALSHI_PERPS_KEY_ID and a private key "
                "(KALSHI_PERPS_PRIVATE_KEY or KALSHI_PERPS_PRIVATE_KEY_PATH). "
                "Kalshi recommends a separate API key for the perps exchange."
            )
        return cls(
            FixSigner.from_auth(auth),
            environment=environment,
            config=config,
            ssl_context=ssl_context,
        )

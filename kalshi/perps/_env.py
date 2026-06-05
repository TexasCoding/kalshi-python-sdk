"""Perps credential loading from the separate ``KALSHI_PERPS_*`` env vars.

Kalshi recommends a **separate API key** for the perps exchange, so perps
credentials live under their own environment-variable namespace rather than
reusing the prediction-API ``KALSHI_*`` vars. Mirrors
:meth:`kalshi.auth.KalshiAuth.try_from_env` semantics.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from kalshi.auth import KalshiAuth
from kalshi.errors import KalshiAuthError

logger = logging.getLogger("kalshi")


def try_perps_auth_from_env(
    *,
    password: bytes | str | Callable[[], bytes | str] | None = None,
) -> KalshiAuth | None:
    """Build a :class:`KalshiAuth` from ``KALSHI_PERPS_*`` env vars, or ``None``.

    Reads:
        KALSHI_PERPS_KEY_ID (required — return ``None`` if unset)
        KALSHI_PERPS_PRIVATE_KEY (PEM string) or KALSHI_PERPS_PRIVATE_KEY_PATH (path)
        KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE (optional; used when the PEM is encrypted)

    Returns ``None`` (with a warning) when ``KALSHI_PERPS_KEY_ID`` is set but no
    private-key source is configured, mirroring the prediction-API behaviour so
    a partial credential bundle yields an unauthenticated client rather than a
    hard error. The signer itself is reused unchanged — perps keys sign the same
    ``str(ts_ms) + METHOD + path`` payload.
    """
    key_id = os.environ.get("KALSHI_PERPS_KEY_ID")
    if not key_id:
        return None

    resolved_password = (
        password
        if password is not None
        else os.environ.get("KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE")
    )

    pem_string = os.environ.get("KALSHI_PERPS_PRIVATE_KEY")
    key_path = os.environ.get("KALSHI_PERPS_PRIVATE_KEY_PATH")
    if pem_string and key_path:
        raise KalshiAuthError(
            "Both KALSHI_PERPS_PRIVATE_KEY and KALSHI_PERPS_PRIVATE_KEY_PATH are "
            "set. Provide exactly one — unset whichever you don't intend to use."
        )
    if pem_string:
        return KalshiAuth.from_pem(key_id, pem_string, password=resolved_password)
    if key_path:
        return KalshiAuth.from_key_path(key_id, key_path, password=resolved_password)

    logger.warning(
        "KALSHI_PERPS_KEY_ID is set but neither KALSHI_PERPS_PRIVATE_KEY nor "
        "KALSHI_PERPS_PRIVATE_KEY_PATH is configured. Returning an "
        "unauthenticated perps client."
    )
    return None

"""Tests that ``KalshiConfig(http2=True)`` wires through to httpx (#271 item 3).

The advertised HTTP/2 multiplexing benefit (#233) only kicks in if the
underlying ``httpx.Client`` / ``httpx.AsyncClient`` actually has
``http2=True`` set, which in turn requires the ``h2`` package to be
importable. Without this check, a regression that silently disables h2
(e.g. dropping the ``http2`` kwarg from the transport's ``client_kwargs``)
would land with no test failing.

We avoid hitting the network: just construct each client and inspect
the httpx-internal flag.
"""

from __future__ import annotations

import importlib.util

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from kalshi.async_client import AsyncKalshiClient
from kalshi.auth import KalshiAuth
from kalshi.client import KalshiClient
from kalshi.config import KalshiConfig

_h2_missing = importlib.util.find_spec("h2") is None


def _make_auth() -> KalshiAuth:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return KalshiAuth(key_id="test", private_key=key)


@pytest.mark.skipif(_h2_missing, reason="h2 package not installed; httpx rejects http2=True")
class TestHttp2Wiring:
    """``http2=True`` on ``KalshiConfig`` must propagate to the httpx client."""

    def test_sync_client_enables_http2(self) -> None:
        config = KalshiConfig(http2=True)
        client = KalshiClient(auth=_make_auth(), config=config)
        try:
            # httpx exposes the negotiated h2 flag on the private transport
            # config; ``http2`` is also reflected on the public client's
            # ``_transport`` chain. We read the transport directly since
            # that is what carries the kwarg.
            httpx_client = client._transport._client
            # ``_transport`` is httpx's default ``HTTPTransport`` which stores
            # the http2 flag on its ``_pool``. Cheaper to just confirm the
            # kwarg made it onto the high-level client.
            assert httpx_client._transport is not None
            # Probe via the same path httpx uses internally: every default
            # transport built with http2=True sets ``http2`` on its pool.
            pool = httpx_client._transport._pool  # type: ignore[attr-defined]
            assert pool._http2 is True, (
                "KalshiConfig(http2=True) did not propagate to httpx.Client's pool"
            )
        finally:
            client.close()

    @pytest.mark.asyncio
    async def test_async_client_enables_http2(self) -> None:
        config = KalshiConfig(http2=True)
        client = AsyncKalshiClient(auth=_make_auth(), config=config)
        try:
            httpx_client = client._transport._client
            pool = httpx_client._transport._pool  # type: ignore[attr-defined]
            assert pool._http2 is True, (
                "KalshiConfig(http2=True) did not propagate to httpx.AsyncClient's pool"
            )
        finally:
            await client.close()

    def test_default_config_does_not_enable_http2(self) -> None:
        """``http2`` defaults to False so the test above is meaningful."""
        config = KalshiConfig()
        assert config.http2 is False
        client = KalshiClient(auth=_make_auth(), config=config)
        try:
            httpx_client = client._transport._client
            pool = httpx_client._transport._pool  # type: ignore[attr-defined]
            assert pool._http2 is False
        finally:
            client.close()

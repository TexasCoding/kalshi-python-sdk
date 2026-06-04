"""Synchronous Kalshi Perps (margin) client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import TypedDict, Unpack

import httpx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.perps._env import try_perps_auth_from_env
from kalshi.perps.config import (
    PERPS_DEMO_BASE_URL,
    PERPS_DEMO_WS_URL,
    PerpsConfig,
)
from kalshi.perps.resources.exchange import PerpsExchangeResource
from kalshi.perps.resources.funding import FundingResource
from kalshi.perps.resources.margin_account import MarginAccountResource
from kalshi.perps.resources.markets import PerpsMarketsResource
from kalshi.perps.resources.order_groups import OrderGroupsResource
from kalshi.perps.resources.orders import MarginOrdersResource
from kalshi.perps.resources.portfolio import PerpsPortfolioResource
from kalshi.perps.resources.transfers import TransfersResource


class PerpsClientInitKwargs(TypedDict, total=False):
    """Typed forwarder shape for :meth:`PerpsClient.from_env`.

    Mirrors the ``__init__`` keyword surface so ``mypy --strict`` catches typos
    like ``from_env(time_out=10)`` instead of silently swallowing them.
    """

    key_id: str | None
    private_key: str | bytes | None
    private_key_path: str | Path | None
    auth: KalshiAuth | None
    config: PerpsConfig | None
    demo: bool
    base_url: str | None
    timeout: float | None
    max_retries: int | None
    transport: httpx.BaseTransport | None


class PerpsClient:
    """Synchronous client for the Kalshi **Perps (margin)** API.

    The perps API lives on a separate host (``external-api.kalshi.com``) and
    Kalshi recommends a **separate API key** for it, so this is a standalone
    client rather than a namespace on :class:`kalshi.KalshiClient`. It reuses the
    same RSA-PSS signer (:class:`kalshi.auth.KalshiAuth`) and HTTP transport
    unchanged.

    Usage::

        with PerpsClient(key_id="...", private_key_path="~/.kalshi/perps.pem") as c:
            status = c.exchange.status()

    ``from_env`` reads a **separate** ``KALSHI_PERPS_*`` credential namespace —
    perps requires keys issued for the perps exchange.
    """

    def __init__(
        self,
        *,
        key_id: str | None = None,
        private_key_path: str | Path | None = None,
        private_key: str | bytes | None = None,
        auth: KalshiAuth | None = None,
        config: PerpsConfig | None = None,
        demo: bool = False,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if key_id is not None and not key_id.strip():
            raise ValueError("key_id must not be empty. Omit it for unauthenticated access.")
        if private_key_path is not None and private_key is not None:
            raise ValueError("Provide either private_key_path or private_key, not both.")
        self._auth: KalshiAuth | None
        self._auth_owned: bool
        if auth is not None:
            self._auth = auth
            self._auth_owned = False
        elif key_id and private_key_path:
            self._auth = KalshiAuth.from_key_path(key_id, private_key_path)
            self._auth_owned = True
        elif key_id and private_key:
            self._auth = KalshiAuth.from_pem(key_id, private_key)
            self._auth_owned = True
        else:
            self._auth = None
            self._auth_owned = False

        if config is not None:
            self._config: PerpsConfig = config
        else:
            if demo and base_url is not None and base_url.rstrip("/") != PERPS_DEMO_BASE_URL:
                raise ValueError(
                    "Conflicting environment: demo=True together with explicit "
                    f"base_url={base_url!r}. demo=True implies base_url="
                    f"{PERPS_DEMO_BASE_URL!r}; passing a different REST endpoint "
                    "would leave ws_base_url pinned to the demo WS feed, producing "
                    "a split REST/WS environment. Drop demo=True and pass both "
                    "base_url and ws_base_url via a PerpsConfig, or use "
                    "PerpsConfig.demo() / PerpsConfig.production()."
                )
            config_kwargs: dict[str, object] = {}
            if base_url:
                config_kwargs["base_url"] = base_url
            if demo:
                config_kwargs.setdefault("base_url", PERPS_DEMO_BASE_URL)
                config_kwargs.setdefault("ws_base_url", PERPS_DEMO_WS_URL)
            if timeout is not None:
                config_kwargs["timeout"] = timeout
            if max_retries is not None:
                config_kwargs["max_retries"] = max_retries
            self._config = PerpsConfig(**config_kwargs)  # type: ignore[arg-type]

        self._transport = SyncTransport(self._auth, self._config, transport=transport)
        self.exchange = PerpsExchangeResource(self._transport)
        self.markets = PerpsMarketsResource(self._transport)
        self.orders = MarginOrdersResource(self._transport)
        self.order_groups = OrderGroupsResource(self._transport)
        self.portfolio = PerpsPortfolioResource(self._transport)
        self.margin = MarginAccountResource(self._transport)
        self.funding = FundingResource(self._transport)
        self.transfers = TransfersResource(self._transport)

    @property
    def is_authenticated(self) -> bool:
        """Whether this client has auth credentials configured."""
        return self._auth is not None

    @classmethod
    def from_env(cls, **kwargs: Unpack[PerpsClientInitKwargs]) -> PerpsClient:
        """Create a perps client from the ``KALSHI_PERPS_*`` environment variables.

        Reads:
            KALSHI_PERPS_KEY_ID (optional — omit for unauthenticated access)
            KALSHI_PERPS_PRIVATE_KEY (PEM string) or KALSHI_PERPS_PRIVATE_KEY_PATH
            KALSHI_PERPS_API_BASE_URL (optional, overrides base_url)
            KALSHI_PERPS_DEMO (optional, "true" for the demo environment)

        Perps credentials are intentionally separate from the prediction-API
        ``KALSHI_*`` vars — Kalshi recommends a distinct API key for the perps
        exchange. Returns an unauthenticated client if no credentials are set.
        """
        caller_supplied_auth = (
            "auth" in kwargs
            or kwargs.get("key_id") is not None
            or kwargs.get("private_key") is not None
            or kwargs.get("private_key_path") is not None
        )
        env_built_auth: KalshiAuth | None = None
        if not caller_supplied_auth:
            env_built_auth = try_perps_auth_from_env()
            if env_built_auth is not None:
                kwargs["auth"] = env_built_auth
        kwargs.setdefault("demo", os.environ.get("KALSHI_PERPS_DEMO", "").lower() == "true")
        kwargs.setdefault("base_url", os.environ.get("KALSHI_PERPS_API_BASE_URL"))
        client = cls(**kwargs)
        if env_built_auth is not None:
            client._auth_owned = True
        return client

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()
        if self._auth is not None and self._auth_owned:
            self._auth.close()

    def __enter__(self) -> PerpsClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

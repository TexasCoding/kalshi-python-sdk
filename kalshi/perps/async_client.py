"""Asynchronous Kalshi Perps (margin) client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import TypedDict, Unpack

import httpx

from kalshi._base_client import AsyncTransport
from kalshi.auth import KalshiAuth
from kalshi.perps._env import try_perps_auth_from_env
from kalshi.perps.config import (
    PERPS_DEMO_BASE_URL,
    PERPS_DEMO_WS_URL,
    PerpsConfig,
)
from kalshi.perps.resources.exchange import AsyncPerpsExchangeResource
from kalshi.perps.resources.funding import AsyncFundingResource
from kalshi.perps.resources.margin_account import AsyncMarginAccountResource
from kalshi.perps.resources.markets import AsyncPerpsMarketsResource
from kalshi.perps.resources.order_groups import AsyncOrderGroupsResource
from kalshi.perps.resources.orders import AsyncMarginOrdersResource
from kalshi.perps.resources.portfolio import AsyncPerpsPortfolioResource
from kalshi.perps.resources.transfers import AsyncTransfersResource


class PerpsClientInitKwargs(TypedDict, total=False):
    """Typed forwarder shape for :meth:`AsyncPerpsClient.from_env`."""

    key_id: str | None
    private_key: str | bytes | None
    private_key_path: str | Path | None
    auth: KalshiAuth | None
    config: PerpsConfig | None
    demo: bool
    base_url: str | None
    timeout: float | None
    max_retries: int | None
    transport: httpx.AsyncBaseTransport | None


class AsyncPerpsClient:
    """Asynchronous client for the Kalshi **Perps (margin)** API.

    Async sibling of :class:`kalshi.perps.PerpsClient`; see that class for the
    separate-host / separate-key rationale. Reuses the RSA-PSS signer and the
    async transport unchanged.

    Usage::

        async with AsyncPerpsClient.from_env(demo=True) as c:
            status = await c.exchange.status()
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
        transport: httpx.AsyncBaseTransport | None = None,
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
        elif key_id or private_key or private_key_path:
            # Partial credentials — fail fast instead of silently building an
            # unauthenticated client (which would surface later as confusing
            # 401s). Reaching here means exactly one half of the pair is set.
            raise ValueError(
                "Incomplete credentials: provide BOTH key_id and one of "
                "private_key / private_key_path to authenticate, or omit all "
                "of them for unauthenticated access."
            )
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

        self._transport = AsyncTransport(self._auth, self._config, transport=transport)
        self.exchange = AsyncPerpsExchangeResource(self._transport)
        self.markets = AsyncPerpsMarketsResource(self._transport)
        self.orders = AsyncMarginOrdersResource(self._transport)
        self.order_groups = AsyncOrderGroupsResource(self._transport)
        self.portfolio = AsyncPerpsPortfolioResource(self._transport)
        self.margin = AsyncMarginAccountResource(self._transport)
        self.funding = AsyncFundingResource(self._transport)
        self.transfers = AsyncTransfersResource(self._transport)

    @property
    def is_authenticated(self) -> bool:
        """Whether this client has auth credentials configured."""
        return self._auth is not None

    @classmethod
    def from_env(cls, **kwargs: Unpack[PerpsClientInitKwargs]) -> AsyncPerpsClient:
        """Create an async perps client from the ``KALSHI_PERPS_*`` env vars.

        See :meth:`kalshi.perps.PerpsClient.from_env` for the variable list and
        the separate-credential rationale.
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

    async def close(self) -> None:
        """Close the underlying async HTTP connection pool."""
        await self._transport.close()
        if self._auth is not None and self._auth_owned:
            self._auth.close()

    async def __aenter__(self) -> AsyncPerpsClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

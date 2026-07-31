"""Synchronous Kalshi Perps (margin) client."""

from __future__ import annotations

import os
from collections.abc import Callable
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
from kalshi.perps.resources.fcm import FcmResource
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
    password: bytes | str | Callable[[], bytes | str] | None
    auth: KalshiAuth | None
    config: PerpsConfig | None
    demo: bool
    base_url: str | None
    ws_base_url: str | None
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
        password: bytes | str | Callable[[], bytes | str] | None = None,
        auth: KalshiAuth | None = None,
        config: PerpsConfig | None = None,
        demo: bool = False,
        base_url: str | None = None,
        ws_base_url: str | None = None,
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
            self._auth = KalshiAuth.from_key_path(key_id, private_key_path, password=password)
            self._auth_owned = True
        elif key_id and private_key:
            self._auth = KalshiAuth.from_pem(key_id, private_key, password=password)
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
            # A PerpsConfig fully fixes the REST + WS endpoints. Combining it
            # with env-determining shorthand would silently ignore that
            # shorthand — a real-money footgun if an explicit demo=True is
            # dropped — so reject the combination outright.
            if demo or base_url is not None or ws_base_url is not None:
                raise ValueError(
                    "Pass either `config=` OR the demo/base_url/ws_base_url "
                    "shorthand, not both. A PerpsConfig already fixes the REST "
                    "and WS endpoints, so demo=True/base_url/ws_base_url would be "
                    "silently ignored. Drop whichever you don't need."
                )
            self._config: PerpsConfig = config
        else:
            if demo and (
                (base_url is not None and base_url.rstrip("/") != PERPS_DEMO_BASE_URL)
                or (ws_base_url is not None and ws_base_url.rstrip("/") != PERPS_DEMO_WS_URL)
            ):
                raise ValueError(
                    "Conflicting environment: demo=True together with an explicit "
                    f"base_url={base_url!r} / ws_base_url={ws_base_url!r} pointing "
                    "elsewhere. demo=True implies the demo REST + WS endpoints; "
                    "pass both base_url and ws_base_url via a PerpsConfig instead, "
                    "or use PerpsConfig.demo() / PerpsConfig.production()."
                )
            config_kwargs: dict[str, object] = {}
            if base_url:
                config_kwargs["base_url"] = base_url
            if ws_base_url:
                config_kwargs["ws_base_url"] = ws_base_url
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
        self.fcm = FcmResource(self._transport)

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
            KALSHI_PERPS_PRIVATE_KEY_PASSPHRASE (optional, for an encrypted key)
            KALSHI_PERPS_API_BASE_URL (optional, overrides base_url)
            KALSHI_PERPS_WS_BASE_URL (optional, overrides ws_base_url)
            KALSHI_PERPS_DEMO (optional, "true" for the demo environment)

        Perps credentials are intentionally separate from the prediction-API
        ``KALSHI_*`` vars — Kalshi recommends a distinct API key for the perps
        exchange. Returns an unauthenticated client if no credentials are set.
        An explicit ``password=`` (or ``config=``) overrides the env value.
        """
        caller_supplied_auth = (
            "auth" in kwargs
            or kwargs.get("key_id") is not None
            or kwargs.get("private_key") is not None
            or kwargs.get("private_key_path") is not None
        )
        env_built_auth: KalshiAuth | None = None
        if not caller_supplied_auth:
            env_built_auth = try_perps_auth_from_env(password=kwargs.get("password"))
            if env_built_auth is not None:
                kwargs["auth"] = env_built_auth
        # Only inject env endpoint overrides when no explicit config is given —
        # otherwise __init__'s config-vs-shorthand guard would reject them.
        if "config" not in kwargs:
            kwargs.setdefault("demo", os.environ.get("KALSHI_PERPS_DEMO", "").lower() == "true")
            kwargs.setdefault("base_url", os.environ.get("KALSHI_PERPS_API_BASE_URL"))
            kwargs.setdefault("ws_base_url", os.environ.get("KALSHI_PERPS_WS_BASE_URL"))
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

"""Synchronous Kalshi client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import TypedDict, Unpack

import httpx

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_BASE_URL, DEMO_WS_URL, KalshiConfig
from kalshi.resources.account import AccountResource
from kalshi.resources.api_keys import ApiKeysResource
from kalshi.resources.communications import CommunicationsResource
from kalshi.resources.events import EventsResource
from kalshi.resources.exchange import ExchangeResource
from kalshi.resources.fcm import FcmResource
from kalshi.resources.historical import HistoricalResource
from kalshi.resources.incentive_programs import IncentiveProgramsResource
from kalshi.resources.live_data import LiveDataResource
from kalshi.resources.markets import MarketsResource
from kalshi.resources.milestones import MilestonesResource
from kalshi.resources.multivariate import MultivariateCollectionsResource
from kalshi.resources.order_groups import OrderGroupsResource
from kalshi.resources.orders import OrdersResource
from kalshi.resources.portfolio import PortfolioResource
from kalshi.resources.search import SearchResource
from kalshi.resources.series import SeriesResource
from kalshi.resources.structured_targets import StructuredTargetsResource
from kalshi.resources.subaccounts import SubaccountsResource


class ClientInitKwargs(TypedDict, total=False):
    """Typed forwarder shape for :meth:`KalshiClient.from_env`.

    Mirrors the ``__init__`` keyword surface so ``mypy --strict`` catches typos
    like ``from_env(time_out=10)`` instead of silently swallowing them under
    ``**kwargs: object``. See #266.
    """

    key_id: str | None
    private_key: str | bytes | None
    private_key_path: str | Path | None
    auth: KalshiAuth | None
    config: KalshiConfig | None
    demo: bool
    base_url: str | None
    timeout: float | None
    max_retries: int | None
    transport: httpx.BaseTransport | None


class KalshiClient:
    """Synchronous client for the Kalshi prediction markets API.

    Usage:
        with KalshiClient(key_id="...", private_key_path="~/.kalshi/key.pem") as client:
            markets = client.markets.list(status="open")
            for market in markets:
                print(market.ticker, market.yes_ask)

    Or without context manager:
        client = KalshiClient(key_id="...", private_key_path="~/.kalshi/key.pem")
        try:
            markets = client.markets.list()
        finally:
            client.close()
    """

    def __init__(
        self,
        *,
        key_id: str | None = None,
        private_key_path: str | Path | None = None,
        private_key: str | bytes | None = None,
        auth: KalshiAuth | None = None,
        config: KalshiConfig | None = None,
        demo: bool = False,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # Build auth (optional — None means unauthenticated)
        # Reject empty strings that look like misconfigured credentials
        if key_id is not None and not key_id.strip():
            raise ValueError("key_id must not be empty. Omit it for unauthenticated access.")
        # #249: refuse ambiguous credential bundle — caller must pick exactly one
        # private-key source so a key-rotation mishap can't leave the SDK
        # silently signing with the wrong key.
        if private_key_path is not None and private_key is not None:
            raise ValueError("Provide either private_key_path or private_key, not both.")
        # #210: only shut down auth on close() when WE built it. If the
        # caller passed in their own KalshiAuth, they keep ownership.
        self._auth_owned: bool = auth is None
        self._auth: KalshiAuth | None
        if auth is not None:
            self._auth = auth
        elif key_id and private_key_path:
            self._auth = KalshiAuth.from_key_path(key_id, private_key_path)
        elif key_id and private_key:
            self._auth = KalshiAuth.from_pem(key_id, private_key)
        else:
            self._auth = None

        # Build config
        if config is not None:
            self._config = config
        else:
            # #239: reject demo=True combined with an explicit non-demo
            # base_url. The old setdefault logic silently honored base_url
            # while still pinning ws_base_url to DEMO_WS_URL, producing a
            # split REST/WS environment (real-money REST + demo WS feed).
            if demo and base_url is not None and base_url.rstrip("/") != DEMO_BASE_URL:
                raise ValueError(
                    "Conflicting environment: demo=True together with explicit "
                    f"base_url={base_url!r}. demo=True implies base_url="
                    f"{DEMO_BASE_URL!r}; passing a different REST endpoint would "
                    "leave ws_base_url pinned to the demo WS feed, producing a "
                    "split REST/WS environment. Drop demo=True and pass both "
                    "base_url and ws_base_url via a KalshiConfig, or use "
                    "KalshiConfig.demo() / KalshiConfig.production()."
                )
            config_kwargs: dict[str, object] = {}
            if base_url:
                config_kwargs["base_url"] = base_url
            if demo:
                config_kwargs.setdefault("base_url", DEMO_BASE_URL)
                config_kwargs.setdefault("ws_base_url", DEMO_WS_URL)
            if timeout is not None:
                config_kwargs["timeout"] = timeout
            if max_retries is not None:
                config_kwargs["max_retries"] = max_retries
            self._config = KalshiConfig(**config_kwargs)  # type: ignore[arg-type]

        # Build transport and resources
        self._transport = SyncTransport(self._auth, self._config, transport=transport)
        self.account = AccountResource(self._transport)
        self.api_keys = ApiKeysResource(self._transport)
        self.communications = CommunicationsResource(self._transport)
        self.events = EventsResource(self._transport)
        self.exchange = ExchangeResource(self._transport)
        self.fcm = FcmResource(self._transport)
        self.historical = HistoricalResource(self._transport)
        self.incentive_programs = IncentiveProgramsResource(self._transport)
        self.live_data = LiveDataResource(self._transport)
        self.markets = MarketsResource(self._transport)
        self.milestones = MilestonesResource(self._transport)
        self.order_groups = OrderGroupsResource(self._transport)
        self.orders = OrdersResource(self._transport)
        self.portfolio = PortfolioResource(self._transport)
        self.search = SearchResource(self._transport)
        self.series = SeriesResource(self._transport)
        self.structured_targets = StructuredTargetsResource(self._transport)
        self.subaccounts = SubaccountsResource(self._transport)
        self.multivariate_collections = MultivariateCollectionsResource(self._transport)

    @property
    def is_authenticated(self) -> bool:
        """Whether this client has auth credentials configured."""
        return self._auth is not None

    @classmethod
    def from_env(cls, **kwargs: Unpack[ClientInitKwargs]) -> KalshiClient:
        """Create client from environment variables.

        Reads:
            KALSHI_KEY_ID (optional — omit for unauthenticated access)
            KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
            KALSHI_API_BASE_URL (optional, overrides base_url)
            KALSHI_DEMO (optional, "true" for demo environment)

        Returns an unauthenticated client if no credentials are configured.
        """
        # Caller-supplied kwargs win over env-derived values (legacy behaviour
        # via ``cls(auth=..., demo=..., base_url=..., **kwargs)`` would have
        # TypeError'd on duplicates; setdefault preserves env semantics while
        # giving the static signature a clean shape). See #266.
        kwargs.setdefault("auth", KalshiAuth.try_from_env())
        kwargs.setdefault("demo", os.environ.get("KALSHI_DEMO", "").lower() == "true")
        kwargs.setdefault("base_url", os.environ.get("KALSHI_API_BASE_URL"))
        client = cls(**kwargs)
        # from_env constructs auth locally — caller never owned it.
        client._auth_owned = kwargs["auth"] is not None
        return client

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()
        if self._auth is not None and self._auth_owned:
            self._auth.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

"""Asynchronous Kalshi client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from kalshi._base_client import AsyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_BASE_URL, DEMO_WS_URL, KalshiConfig
from kalshi.errors import AuthRequiredError
from kalshi.resources.api_keys import AsyncApiKeysResource
from kalshi.resources.communications import AsyncCommunicationsResource
from kalshi.resources.events import AsyncEventsResource
from kalshi.resources.exchange import AsyncExchangeResource
from kalshi.resources.historical import AsyncHistoricalResource
from kalshi.resources.live_data import AsyncLiveDataResource
from kalshi.resources.markets import AsyncMarketsResource
from kalshi.resources.milestones import AsyncMilestonesResource
from kalshi.resources.multivariate import AsyncMultivariateCollectionsResource
from kalshi.resources.order_groups import AsyncOrderGroupsResource
from kalshi.resources.orders import AsyncOrdersResource
from kalshi.resources.portfolio import AsyncPortfolioResource
from kalshi.resources.series import AsyncSeriesResource
from kalshi.resources.subaccounts import AsyncSubaccountsResource

if TYPE_CHECKING:
    from kalshi.ws.client import KalshiWebSocket


class AsyncKalshiClient:
    """Asynchronous client for the Kalshi prediction markets API.

    Usage:
        async with AsyncKalshiClient(key_id="...", private_key_path="~/.kalshi/key.pem") as client:
            markets = await client.markets.list(status="open")
            for market in markets:
                print(market.ticker, market.yes_ask)
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
    ) -> None:
        # Build auth (optional — None means unauthenticated)
        # Reject empty strings that look like misconfigured credentials
        if key_id is not None and not key_id.strip():
            raise ValueError("key_id must not be empty. Omit it for unauthenticated access.")
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
        self._transport = AsyncTransport(self._auth, self._config)
        self.api_keys = AsyncApiKeysResource(self._transport)
        self.communications = AsyncCommunicationsResource(self._transport)
        self.events = AsyncEventsResource(self._transport)
        self.exchange = AsyncExchangeResource(self._transport)
        self.historical = AsyncHistoricalResource(self._transport)
        self.live_data = AsyncLiveDataResource(self._transport)
        self.markets = AsyncMarketsResource(self._transport)
        self.milestones = AsyncMilestonesResource(self._transport)
        self.order_groups = AsyncOrderGroupsResource(self._transport)
        self.orders = AsyncOrdersResource(self._transport)
        self.portfolio = AsyncPortfolioResource(self._transport)
        self.series = AsyncSeriesResource(self._transport)
        self.subaccounts = AsyncSubaccountsResource(self._transport)
        self.multivariate_collections = AsyncMultivariateCollectionsResource(self._transport)

    @property
    def is_authenticated(self) -> bool:
        """Whether this client has auth credentials configured."""
        return self._auth is not None

    @property
    def ws(self) -> KalshiWebSocket:
        """WebSocket client for real-time streaming.

        Usage::

            async with client.ws.connect() as session:
                async for msg in session.subscribe_ticker(tickers=["ECON-GDP-25Q1"]):
                    print(msg.msg.yes_bid)
        """
        if self._auth is None:
            raise AuthRequiredError(
                "WebSocket connections require authentication. "
                "Provide key_id + private_key_path, or use AsyncKalshiClient.from_env()."
            )
        from kalshi.ws.client import KalshiWebSocket as _KalshiWebSocket
        return _KalshiWebSocket(auth=self._auth, config=self._config)

    @classmethod
    def from_env(cls, **kwargs: object) -> AsyncKalshiClient:
        """Create async client from environment variables.

        Reads:
            KALSHI_KEY_ID (optional — omit for unauthenticated access)
            KALSHI_PRIVATE_KEY (PEM string) or KALSHI_PRIVATE_KEY_PATH (file path)
            KALSHI_API_BASE_URL (optional, overrides base_url)
            KALSHI_DEMO (optional, "true" for demo environment)

        Returns an unauthenticated client if no credentials are configured.
        """
        auth = KalshiAuth.try_from_env()
        demo = os.environ.get("KALSHI_DEMO", "").lower() == "true"
        base_url = os.environ.get("KALSHI_API_BASE_URL")
        return cls(auth=auth, demo=demo, base_url=base_url, **kwargs)  # type: ignore[arg-type]

    async def close(self) -> None:
        """Close the underlying async HTTP connection pool."""
        await self._transport.close()

    async def __aenter__(self) -> AsyncKalshiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

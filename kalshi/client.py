"""Synchronous Kalshi client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from kalshi._base_client import SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.resources.events import EventsResource
from kalshi.resources.exchange import ExchangeResource
from kalshi.resources.historical import HistoricalResource
from kalshi.resources.markets import MarketsResource
from kalshi.resources.orders import OrdersResource
from kalshi.resources.portfolio import PortfolioResource


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
    ) -> None:
        # Build auth
        if auth is not None:
            self._auth = auth
        elif key_id and private_key_path:
            self._auth = KalshiAuth.from_key_path(key_id, private_key_path)
        elif key_id and private_key:
            self._auth = KalshiAuth.from_pem(key_id, private_key)
        else:
            raise ValueError(
                "Provide auth, or key_id + private_key_path, or key_id + private_key. "
                "Or use KalshiClient.from_env()."
            )

        # Build config
        if config is not None:
            self._config = config
        else:
            config_kwargs: dict[str, object] = {}
            if base_url:
                config_kwargs["base_url"] = base_url
            elif demo:
                config_kwargs["base_url"] = DEMO_BASE_URL
            if timeout is not None:
                config_kwargs["timeout"] = timeout
            if max_retries is not None:
                config_kwargs["max_retries"] = max_retries
            self._config = KalshiConfig(**config_kwargs)  # type: ignore[arg-type]

        # Build transport and resources
        self._transport = SyncTransport(self._auth, self._config)
        self.events = EventsResource(self._transport)
        self.exchange = ExchangeResource(self._transport)
        self.historical = HistoricalResource(self._transport)
        self.markets = MarketsResource(self._transport)
        self.orders = OrdersResource(self._transport)
        self.portfolio = PortfolioResource(self._transport)

    @classmethod
    def from_env(cls, **kwargs: object) -> KalshiClient:
        """Create client from environment variables.

        Reads:
            KALSHI_KEY_ID (required)
            KALSHI_PRIVATE_KEY or KALSHI_PRIVATE_KEY_PATH (one required)
            KALSHI_API_BASE_URL (optional, overrides base_url)
            KALSHI_DEMO (optional, "true" for demo environment)
        """
        auth = KalshiAuth.from_env()
        demo = os.environ.get("KALSHI_DEMO", "").lower() == "true"
        base_url = os.environ.get("KALSHI_API_BASE_URL")
        return cls(auth=auth, demo=demo, base_url=base_url, **kwargs)  # type: ignore[arg-type]

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._transport.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

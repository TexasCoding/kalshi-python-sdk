"""Asynchronous Kalshi client."""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from kalshi._base_client import AsyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import DEMO_BASE_URL, KalshiConfig
from kalshi.resources.markets import AsyncMarketsResource
from kalshi.resources.orders import AsyncOrdersResource


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
                "Or use AsyncKalshiClient.from_env()."
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
        self._transport = AsyncTransport(self._auth, self._config)
        self.markets = AsyncMarketsResource(self._transport)
        self.orders = AsyncOrdersResource(self._transport)

    @classmethod
    def from_env(cls, **kwargs: object) -> AsyncKalshiClient:
        """Create async client from environment variables.

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

"""Asynchronous Kalshi Klear (SCM) client."""

from __future__ import annotations

import os
from types import TracebackType

import httpx

from kalshi._base_client import AsyncTransport
from kalshi.perps.klear.auth import KlearAuth
from kalshi.perps.klear.config import DEMO_KLEAR_URL, KlearConfig
from kalshi.perps.klear.models.auth import LogInResponse
from kalshi.perps.klear.resources.auth import AsyncAuthResource
from kalshi.perps.resources.margin import AsyncMarginResource


class AsyncKlearClient:
    """Asynchronous client for the Kalshi **Klear (SCM)** API.

    Async sibling of :class:`kalshi.perps.klear.KlearClient`; see that class for
    the cookie-session / no-RSA rationale.
    """

    def __init__(
        self,
        *,
        config: KlearConfig | None = None,
        demo: bool = False,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if config is not None:
            self._config: KlearConfig = config
        else:
            if demo and base_url is not None and base_url.rstrip("/") != DEMO_KLEAR_URL:
                raise ValueError(
                    "Conflicting environment: demo=True together with explicit "
                    f"base_url={base_url!r}. demo=True implies base_url={DEMO_KLEAR_URL!r}."
                )
            config_kwargs: dict[str, object] = {}
            if base_url:
                config_kwargs["base_url"] = base_url
            if demo:
                config_kwargs.setdefault("base_url", DEMO_KLEAR_URL)
            if timeout is not None:
                config_kwargs["timeout"] = timeout
            if max_retries is not None:
                config_kwargs["max_retries"] = max_retries
            self._config = KlearConfig(**config_kwargs)  # type: ignore[arg-type]

        self._transport = AsyncTransport(None, self._config, transport=transport)
        self._auth = KlearAuth()
        self.auth = AsyncAuthResource(self._transport, self._auth)
        self.margin = AsyncMarginResource(self._transport, self._auth)

    @property
    def is_authenticated(self) -> bool:
        """Whether a Klear session has been established via :meth:`login`."""
        return self._auth.is_authenticated

    @classmethod
    def from_env(
        cls,
        *,
        demo: bool | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> AsyncKlearClient:
        """Create an async Klear client, reading only environment routing.

        See :meth:`kalshi.perps.klear.KlearClient.from_env` — credentials are
        never read from the environment.
        """
        resolved_demo = (
            demo if demo is not None else os.environ.get("KALSHI_KLEAR_DEMO", "").lower() == "true"
        )
        resolved_base_url = (
            base_url if base_url is not None else os.environ.get("KALSHI_KLEAR_API_BASE_URL")
        )
        return cls(
            demo=resolved_demo,
            base_url=resolved_base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def login(
        self, *, email: str, password: str, code: str | None = None
    ) -> LogInResponse:
        """Convenience wrapper for :meth:`AsyncAuthResource.log_in`."""
        return await self.auth.log_in(email=email, password=password, code=code)

    async def close(self) -> None:
        """Close the underlying async HTTP connection pool and clear session state."""
        await self._transport.close()
        self._auth.reset()

    async def __aenter__(self) -> AsyncKlearClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

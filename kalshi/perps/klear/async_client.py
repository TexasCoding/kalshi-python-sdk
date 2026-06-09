"""Asynchronous Kalshi Klear (SCM) client."""

from __future__ import annotations

import os
from types import TracebackType

import httpx

from kalshi._base_client import AsyncTransport
from kalshi.perps.klear.auth import KlearAuth
from kalshi.perps.klear.config import DEMO_KLEAR_URL, KlearConfig
from kalshi.perps.klear.resources.margin import AsyncMarginResource


class AsyncKlearClient:
    """Asynchronous client for the Kalshi **Klear (SCM)** API.

    Async sibling of :class:`kalshi.perps.klear.KlearClient`; see that class for
    the Bearer-token / no-RSA rationale.
    """

    def __init__(
        self,
        *,
        admin_user_id: str,
        access_token: str,
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
        self._auth = KlearAuth(admin_user_id, access_token)
        self.margin = AsyncMarginResource(self._transport, self._auth)

    @classmethod
    def from_env(
        cls,
        *,
        admin_user_id: str | None = None,
        access_token: str | None = None,
        demo: bool | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> AsyncKlearClient:
        """Create an async Klear client, reading credentials and routing from the environment.

        See :meth:`kalshi.perps.klear.KlearClient.from_env`. ``transport`` is
        forwarded for tests.
        """
        resolved_admin = (
            admin_user_id
            if admin_user_id is not None
            else os.environ.get("KALSHI_KLEAR_ADMIN_USER_ID")
        )
        resolved_token = (
            access_token
            if access_token is not None
            else os.environ.get("KALSHI_KLEAR_ACCESS_TOKEN")
        )
        if not resolved_admin or not resolved_token:
            raise ValueError(
                "AsyncKlearClient.from_env requires KALSHI_KLEAR_ADMIN_USER_ID and "
                "KALSHI_KLEAR_ACCESS_TOKEN (or explicit admin_user_id/access_token)."
            )
        resolved_demo = (
            demo if demo is not None else os.environ.get("KALSHI_KLEAR_DEMO", "").lower() == "true"
        )
        resolved_base_url = (
            base_url if base_url is not None else os.environ.get("KALSHI_KLEAR_API_BASE_URL")
        )
        return cls(
            admin_user_id=resolved_admin,
            access_token=resolved_token,
            demo=resolved_demo,
            base_url=resolved_base_url,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    async def close(self) -> None:
        """Close the underlying async HTTP connection pool."""
        await self._transport.close()

    async def __aenter__(self) -> AsyncKlearClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

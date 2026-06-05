"""Synchronous Kalshi Klear (SCM) client."""

from __future__ import annotations

import os
from types import TracebackType

import httpx

from kalshi._base_client import SyncTransport
from kalshi.perps.klear.auth import KlearAuth
from kalshi.perps.klear.config import DEMO_KLEAR_URL, KlearConfig
from kalshi.perps.klear.models.auth import LogInResponse
from kalshi.perps.klear.resources.auth import AuthResource
from kalshi.perps.resources.margin import MarginResource


class KlearClient:
    """Synchronous client for the Kalshi **Klear (Self-Clearing-Member)** API.

    Authenticates with email + password (+ MFA) via :meth:`login`, which sets a
    ``session`` cookie replayed on every subsequent request. The RSA-PSS signing
    path is **not** used: the transport is constructed with ``auth=None`` so no
    ``KALSHI-ACCESS-*`` headers are ever signed, and the session cookie travels
    on the transport's httpx cookie jar.

    Usage::

        with KlearClient(demo=True) as c:
            resp = c.login(email="...", password="...")
            if resp.required_mfa_method:
                c.login(email="...", password="...", code="123456")
            # ... call SCM endpoints (c.margin.*, added in #400)
    """

    def __init__(
        self,
        *,
        config: KlearConfig | None = None,
        demo: bool = False,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
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

        # RSA-PSS signing is NOT used: auth=None means the transport never signs
        # a request. The session cookie is captured/replayed by the httpx jar.
        self._transport = SyncTransport(None, self._config, transport=transport)
        self._auth = KlearAuth()
        self.auth = AuthResource(self._transport, self._auth)
        self.margin = MarginResource(self._transport, self._auth)

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
    ) -> KlearClient:
        """Create a Klear client, reading only environment routing (not credentials).

        Reads ``KALSHI_KLEAR_API_BASE_URL`` and ``KALSHI_KLEAR_DEMO``. Klear
        credentials are supplied interactively via :meth:`login` — they are never
        read from the environment.
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

    def login(
        self, *, email: str, password: str, code: str | None = None
    ) -> LogInResponse:
        """Convenience wrapper for :meth:`AuthResource.log_in`.

        Returns the :class:`LogInResponse`; inspect ``required_mfa_method`` and
        re-call with ``code`` if MFA is required.
        """
        return self.auth.log_in(email=email, password=password, code=code)

    def close(self) -> None:
        """Close the underlying HTTP connection pool and clear session state."""
        self._transport.close()
        self._auth.reset()

    def __enter__(self) -> KlearClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

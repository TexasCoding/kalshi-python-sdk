"""Configuration for the Kalshi SDK client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

PRODUCTION_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

PRODUCTION_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_WS_MAX_RETRIES = 10

_KNOWN_HOSTS = frozenset(
    {"api.elections.kalshi.com", "demo-api.kalshi.co"}
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

logger = logging.getLogger("kalshi")


@dataclass(frozen=True)
class KalshiConfig:
    """Client configuration.

    Attributes:
        base_url: API base URL. Defaults to production.
        timeout: Request timeout in seconds. Defaults to 30.
        max_retries: Max retry attempts for transient errors. Defaults to 3.
        retry_base_delay: Base delay in seconds for exponential backoff. Defaults to 0.5.
        retry_max_delay: Maximum delay in seconds for backoff. Defaults to 30.
        http2: Enable HTTP/2 for REST requests. Off by default for compat.
            Requires the ``h2`` package (install ``httpx[http2]`` or ``h2``).
        limits: Custom ``httpx.Limits`` for connection pool tuning. ``None``
            uses httpx defaults.
    """

    base_url: str = PRODUCTION_BASE_URL  # trailing slash is stripped automatically
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    ws_base_url: str = PRODUCTION_WS_URL  # trailing slash is stripped automatically
    ws_max_retries: int = DEFAULT_WS_MAX_RETRIES
    http2: bool = False
    limits: httpx.Limits | None = None

    def __post_init__(self) -> None:
        # Strip trailing slash to prevent double-slash in auth signing paths
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if self.ws_base_url.endswith("/"):
            object.__setattr__(self, "ws_base_url", self.ws_base_url.rstrip("/"))
        KalshiConfig._validate_url(self.base_url, "base_url", secure="https", plaintext="http")
        KalshiConfig._validate_url(self.ws_base_url, "ws_base_url", secure="wss", plaintext="ws")

    @staticmethod
    def _validate_url(url: str, field_name: str, *, secure: str, plaintext: str) -> None:
        """Reject URLs that would expose credentials (bad scheme or plaintext-to-remote)."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme not in (secure, plaintext):
            raise ValueError(
                f"KalshiConfig.{field_name} must use {secure}:// or {plaintext}://, "
                f"got scheme={scheme!r} (url={url!r})"
            )
        if not host:
            raise ValueError(
                f"KalshiConfig.{field_name} is missing a host: {url!r}"
            )
        if scheme == plaintext and host not in _LOCAL_HOSTS:
            raise ValueError(
                f"KalshiConfig.{field_name} must use {secure}:// for non-loopback "
                f"hosts; {plaintext}:// is only allowed for {sorted(_LOCAL_HOSTS)} "
                f"(url={url!r}). Plaintext to a remote host would "
                f"expose the KALSHI-ACCESS-KEY header and request signature."
            )
        if host not in _KNOWN_HOSTS and host not in _LOCAL_HOSTS:
            logger.warning(
                "KalshiConfig.%s host %r is not a known Kalshi "
                "endpoint (%s). Requests will be signed and sent there "
                "with your API key — verify this is intentional.",
                field_name,
                host,
                sorted(_KNOWN_HOSTS),
            )

    @classmethod
    def production(cls, **kwargs: object) -> KalshiConfig:
        """Create config for Kalshi production environment."""
        return cls(base_url=PRODUCTION_BASE_URL, ws_base_url=PRODUCTION_WS_URL, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def demo(cls, **kwargs: object) -> KalshiConfig:
        """Create config for Kalshi demo/sandbox environment."""
        return cls(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, **kwargs)  # type: ignore[arg-type]

"""Configuration for the Kalshi SDK client."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

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
    """

    base_url: str = PRODUCTION_BASE_URL  # trailing slash is stripped automatically
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    extra_headers: dict[str, str] = field(default_factory=dict)
    ws_base_url: str = PRODUCTION_WS_URL  # trailing slash is stripped automatically
    ws_max_retries: int = DEFAULT_WS_MAX_RETRIES

    def __post_init__(self) -> None:
        # Strip trailing slash to prevent double-slash in auth signing paths
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if self.ws_base_url.endswith("/"):
            object.__setattr__(self, "ws_base_url", self.ws_base_url.rstrip("/"))
        self._validate_base_url(self.base_url)

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        """Reject base_urls that would leak API credentials.

        An attacker who can write to the process environment (``docker run
        -e``, CI variable, shell history) can otherwise redirect signed
        requests to an arbitrary host. Enforce https-only, and warn when
        the host isn't a known Kalshi endpoint so misroutes surface in
        logs.

        ``http://`` is permitted only for loopback hosts (localhost,
        127.0.0.1, ::1) so local mock servers and tests still work.
        """
        parsed = urlparse(base_url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme not in ("http", "https"):
            raise ValueError(
                f"KalshiConfig.base_url must use http:// or https://, got "
                f"scheme={scheme!r} (url={base_url!r})"
            )
        if not host:
            raise ValueError(
                f"KalshiConfig.base_url is missing a host: {base_url!r}"
            )
        if scheme == "http" and host not in _LOCAL_HOSTS:
            raise ValueError(
                f"KalshiConfig.base_url must use https:// for non-loopback "
                f"hosts; http:// is only allowed for {sorted(_LOCAL_HOSTS)} "
                f"(url={base_url!r}). Plaintext to a remote host would "
                f"expose the KALSHI-ACCESS-KEY header and request signature."
            )
        if host not in _KNOWN_HOSTS and host not in _LOCAL_HOSTS:
            logger.warning(
                "KalshiConfig.base_url host %r is not a known Kalshi "
                "endpoint (%s). Requests will be signed and sent there "
                "with your API key — verify this is intentional.",
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

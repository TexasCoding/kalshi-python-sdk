"""Configuration for the Kalshi SDK client."""

from __future__ import annotations

from dataclasses import dataclass, field

PRODUCTION_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"

PRODUCTION_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
DEMO_WS_URL = "wss://demo-api.kalshi.co/trade-api/ws/v2"

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_WS_MAX_RETRIES = 10


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

    @classmethod
    def production(cls, **kwargs: object) -> KalshiConfig:
        """Create config for Kalshi production environment."""
        return cls(base_url=PRODUCTION_BASE_URL, ws_base_url=PRODUCTION_WS_URL, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def demo(cls, **kwargs: object) -> KalshiConfig:
        """Create config for Kalshi demo/sandbox environment."""
        return cls(base_url=DEMO_BASE_URL, ws_base_url=DEMO_WS_URL, **kwargs)  # type: ignore[arg-type]

"""Configuration for the Kalshi SDK client."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
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
        total_timeout: Hard cap on cumulative time spent inside a single
            request including retries, in seconds. ``None`` disables (legacy
            behaviour: retry until ``max_retries`` exhausted regardless of
            wall-clock).
        http2: Enable HTTP/2 for REST requests. Off by default for compat.
            Requires the ``h2`` package (install ``httpx[http2]`` or ``h2``).
        limits: Custom ``httpx.Limits`` for connection pool tuning. ``None``
            uses httpx defaults.
        ws_ping_interval: Interval (s) between WS keepalive pings. Default 20.
        ws_close_timeout: Time (s) to wait for graceful WS close handshake.
            Default 5.
        ws_json_loads: Optional callable used to parse WS frames. ``None``
            falls back to :func:`json.loads`. Set to e.g. ``orjson.loads``
            for ~2-3x faster recv-loop parsing on high-volume streams.
        ws_json_dumps: Optional callable used to serialize outbound WS
            commands. ``None`` falls back to :func:`json.dumps`.
    """

    base_url: str = PRODUCTION_BASE_URL  # trailing slash is stripped automatically
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    total_timeout: float | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)
    ws_base_url: str = PRODUCTION_WS_URL  # trailing slash is stripped automatically
    ws_max_retries: int = DEFAULT_WS_MAX_RETRIES
    http2: bool = False
    limits: httpx.Limits | None = None
    ws_ping_interval: float = 20.0
    ws_close_timeout: float = 5.0
    ws_json_loads: Callable[[bytes | str], Any] | None = None
    ws_json_dumps: Callable[[Any], bytes | str] | None = None

    def __post_init__(self) -> None:
        # Strip trailing slash to prevent double-slash in auth signing paths
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if self.ws_base_url.endswith("/"):
            object.__setattr__(self, "ws_base_url", self.ws_base_url.rstrip("/"))
        KalshiConfig._validate_url(self.base_url, "base_url", secure="https", plaintext="http")
        KalshiConfig._validate_url(self.ws_base_url, "ws_base_url", secure="wss", plaintext="ws")
        # #202: prevent silently calling /trade-api or /v1 by enforcing the
        # v2 path component. Trailing slashes are already stripped above.
        base_path = urlparse(self.base_url).path
        if base_path != "/trade-api/v2":
            raise ValueError(
                f"KalshiConfig.base_url must include the /trade-api/v2 path "
                f"component, got base_url={self.base_url!r}"
            )
        # #239: reject split REST/WS environment. If base_url and ws_base_url
        # resolve to *different* known Kalshi environments (prod vs demo), a
        # caller who set demo=True alongside an explicit prod base_url would
        # otherwise place live orders against signals from a demo book.
        # Localhost on either side is fine (mock servers).
        base_host = (urlparse(self.base_url).hostname or "").lower()
        ws_host = (urlparse(self.ws_base_url).hostname or "").lower()
        _prod_host = "api.elections.kalshi.com"
        _demo_host = "demo-api.kalshi.co"
        if (base_host == _prod_host and ws_host == _demo_host) or (
            base_host == _demo_host and ws_host == _prod_host
        ):
            raise ValueError(
                "KalshiConfig: split REST/WS environment is not allowed. "
                f"base_url={self.base_url!r} and ws_base_url={self.ws_base_url!r} "
                "resolve to different Kalshi environments (production vs demo). "
                "REST and WS must point at the same environment to avoid placing "
                "live orders against demo-derived signals (or vice versa). Use "
                "KalshiConfig.production() / KalshiConfig.demo(), or pass both "
                "base_url and ws_base_url explicitly."
            )
        if self.http2:
            import importlib.util

            if importlib.util.find_spec("h2") is None:
                raise ValueError(
                    "http2=True requires the 'h2' package — install with "
                    "`pip install kalshi-sdk[http2]`"
                )

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

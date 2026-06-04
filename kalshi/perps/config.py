"""Configuration for the Kalshi Perps (margin) SDK client.

``PerpsConfig`` subclasses :class:`kalshi.config.KalshiConfig` so that the
reused :class:`kalshi._base_client.SyncTransport` / ``AsyncTransport`` (whose
constructors are annotated ``config: KalshiConfig``) accept it unchanged. The
subclass exists because ``KalshiConfig.__post_init__`` hard-fails on hosts
outside the prediction-API ``_KNOWN_HOSTS`` set — the perps hosts
``external-api.kalshi.com`` / ``external-api.demo.kalshi.co`` are not in that
set, so reusing ``KalshiConfig`` directly would raise at construction. The
``/trade-api/v2`` path component is identical for perps and is validated the
same way.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlparse

from kalshi._constants import AUTH_HEADER_PREFIX
from kalshi.config import KalshiConfig

PERPS_PRODUCTION_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
PERPS_DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"

PERPS_PRODUCTION_WS_URL = "wss://external-api-margin-ws.kalshi.com/trade-api/ws/v2/margin"
PERPS_DEMO_WS_URL = "wss://external-api-margin-ws.demo.kalshi.co/trade-api/ws/v2/margin"

# REST + WS hosts both validate against this union (the perps WS host differs
# from the perps REST host, unlike the prediction API where both share a host).
_PERPS_REST_HOSTS = frozenset(
    {"external-api.kalshi.com", "external-api.demo.kalshi.co"}
)
_PERPS_WS_HOSTS = frozenset(
    {"external-api-margin-ws.kalshi.com", "external-api-margin-ws.demo.kalshi.co"}
)
_PERPS_KNOWN_HOSTS = _PERPS_REST_HOSTS | _PERPS_WS_HOSTS
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Perps prod/demo host pairs, used by the split REST/WS environment guard.
_PERPS_PROD_REST_HOST = "external-api.kalshi.com"
_PERPS_DEMO_REST_HOST = "external-api.demo.kalshi.co"
_PERPS_PROD_WS_HOST = "external-api-margin-ws.kalshi.com"
_PERPS_DEMO_WS_HOST = "external-api-margin-ws.demo.kalshi.co"

logger = logging.getLogger("kalshi")


@dataclass(frozen=True)
class PerpsConfig(KalshiConfig):
    """Perps (margin) client configuration.

    Same field surface as :class:`kalshi.config.KalshiConfig` (timeouts, retry
    policy, ``extra_headers``, HTTP/2, custom JSON loaders, WS keepalive knobs),
    but defaults to the perps REST/WS base URLs and validates against the perps
    host set. Use :meth:`production` / :meth:`demo` for the canonical
    environments.

    The ``allow_unknown_host`` escape hatch (and the process-wide
    ``KALSHI_PERPS_ALLOW_UNKNOWN_HOST=1`` env var) relaxes the host check for
    mock servers / proxies, exactly mirroring the prediction-API config.
    """

    base_url: str = PERPS_PRODUCTION_BASE_URL  # trailing slash stripped automatically
    ws_base_url: str = PERPS_PRODUCTION_WS_URL  # trailing slash stripped automatically

    def __post_init__(self) -> None:
        # NB: deliberately does NOT call super().__post_init__() — that would
        # validate against the prediction-API host set and reject perps hosts.
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        if self.ws_base_url.endswith("/"):
            object.__setattr__(self, "ws_base_url", self.ws_base_url.rstrip("/"))
        allow_unknown = self.allow_unknown_host or (
            os.environ.get("KALSHI_PERPS_ALLOW_UNKNOWN_HOST", "").strip() == "1"
        )
        PerpsConfig._validate_perps_url(
            self.base_url,
            "base_url",
            secure="https",
            plaintext="http",
            allow_unknown_host=allow_unknown,
        )
        PerpsConfig._validate_perps_url(
            self.ws_base_url,
            "ws_base_url",
            secure="wss",
            plaintext="ws",
            allow_unknown_host=allow_unknown,
        )
        # Enforce the /trade-api/v2 REST path component (identical to the
        # prediction API). Trailing slashes already stripped above.
        base_path = urlparse(self.base_url).path
        if base_path != "/trade-api/v2":
            raise ValueError(
                f"PerpsConfig.base_url must include the /trade-api/v2 path "
                f"component, got base_url={self.base_url!r}"
            )
        # Reject a split REST/WS environment (prod REST + demo WS, or vice
        # versa) — the same real-money-vs-demo footgun KalshiConfig guards.
        base_host = (urlparse(self.base_url).hostname or "").lower()
        ws_host = (urlparse(self.ws_base_url).hostname or "").lower()
        is_split = (
            base_host == _PERPS_PROD_REST_HOST and ws_host == _PERPS_DEMO_WS_HOST
        ) or (base_host == _PERPS_DEMO_REST_HOST and ws_host == _PERPS_PROD_WS_HOST)
        if is_split:
            raise ValueError(
                "PerpsConfig: split REST/WS environment is not allowed. "
                f"base_url={self.base_url!r} and ws_base_url={self.ws_base_url!r} "
                "resolve to different perps environments (production vs demo). "
                "Use PerpsConfig.production() / PerpsConfig.demo(), or pass both "
                "base_url and ws_base_url explicitly."
            )
        # Reject KALSHI-ACCESS-* prefix at construction so callers cannot forge auth.
        if self.extra_headers:
            leaked = sorted(
                k for k in self.extra_headers if k.lower().startswith(AUTH_HEADER_PREFIX)
            )
            if leaked:
                raise ValueError(
                    f"PerpsConfig.extra_headers must not include KALSHI-ACCESS-* "
                    f"keys (got: {leaked!r}). These are reserved for SDK-managed "
                    f"RSA-PSS signing."
                )
        object.__setattr__(
            self, "extra_headers", MappingProxyType(dict(self.extra_headers))
        )
        if self.http2:
            import importlib.util

            if importlib.util.find_spec("h2") is None:
                raise ValueError(
                    "http2=True requires the 'h2' package — install with "
                    "`pip install kalshi-sdk[http2]`"
                )

    @staticmethod
    def _validate_perps_url(
        url: str,
        field_name: str,
        *,
        secure: str,
        plaintext: str,
        allow_unknown_host: bool,
    ) -> None:
        """Reject URLs that would expose credentials (bad scheme or plaintext-to-remote)."""
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()

        if scheme not in (secure, plaintext):
            raise ValueError(
                f"PerpsConfig.{field_name} must use {secure}:// or {plaintext}://, "
                f"got scheme={scheme!r} (url={url!r})"
            )
        if not host:
            raise ValueError(f"PerpsConfig.{field_name} is missing a host: {url!r}")
        if scheme == plaintext and host not in _LOCAL_HOSTS:
            raise ValueError(
                f"PerpsConfig.{field_name} must use {secure}:// for non-loopback "
                f"hosts; {plaintext}:// is only allowed for {sorted(_LOCAL_HOSTS)} "
                f"(url={url!r}). Plaintext to a remote host would "
                f"expose the KALSHI-ACCESS-KEY header and request signature."
            )
        if host not in _PERPS_KNOWN_HOSTS and host not in _LOCAL_HOSTS:
            if not allow_unknown_host:
                raise ValueError(
                    f"PerpsConfig.{field_name} host {host!r} is not a known "
                    f"Kalshi perps endpoint. Known hosts: {sorted(_PERPS_KNOWN_HOSTS)}. "
                    "If this is an intentional mock server, proxy, or alternate "
                    "perps region, opt in with PerpsConfig(allow_unknown_host=True) "
                    "or set the environment variable KALSHI_PERPS_ALLOW_UNKNOWN_HOST=1."
                )
            logger.warning(
                "PerpsConfig.%s host %r is not a known Kalshi perps endpoint (%s). "
                "Requests will be signed and sent there with your API key — "
                "verify this is intentional. (allow_unknown_host=True or "
                "KALSHI_PERPS_ALLOW_UNKNOWN_HOST=1 silenced the default error.)",
                field_name,
                host,
                sorted(_PERPS_KNOWN_HOSTS),
            )

    @classmethod
    def production(cls, **kwargs: object) -> PerpsConfig:
        """Create config for the Kalshi perps production environment."""
        return cls(
            base_url=PERPS_PRODUCTION_BASE_URL,
            ws_base_url=PERPS_PRODUCTION_WS_URL,
            **kwargs,  # type: ignore[arg-type]
        )

    @classmethod
    def demo(cls, **kwargs: object) -> PerpsConfig:
        """Create config for the Kalshi perps demo/sandbox environment."""
        return cls(
            base_url=PERPS_DEMO_BASE_URL,
            ws_base_url=PERPS_DEMO_WS_URL,
            **kwargs,  # type: ignore[arg-type]
        )

"""Configuration for the Kalshi Self-Clearing-Member (Klear / SCM) API.

``KlearConfig`` subclasses :class:`kalshi.config.KalshiConfig` so the reused
:class:`kalshi._base_client.SyncTransport` / ``AsyncTransport`` (annotated
``config: KalshiConfig``) accept it unchanged. The Klear API lives on its own
host with a ``/klear-api/v1`` path (NOT ``/trade-api/v2``) and has no WebSocket
surface, so ``__post_init__`` validates the Klear hosts/path and skips the WS
checks.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlparse

from kalshi._constants import AUTH_HEADER_PREFIX
from kalshi.config import KalshiConfig

PRODUCTION_KLEAR_URL = "https://api.klear.kalshi.com/klear-api/v1"
DEMO_KLEAR_URL = "https://demo-api.kalshi.co/klear-api/v1"

_KLEAR_KNOWN_HOSTS = frozenset({"api.klear.kalshi.com", "demo-api.kalshi.co"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

logger = logging.getLogger("kalshi")


@dataclass(frozen=True)
class KlearConfig(KalshiConfig):
    """Klear (SCM) client configuration.

    Same field surface as :class:`kalshi.config.KalshiConfig` (timeouts, retry
    policy, ``extra_headers``, HTTP/2, custom REST JSON loader) but defaults to
    the Klear base URL and validates the ``/klear-api/v1`` path + Klear hosts.
    Holds **no credentials** — email/password live only in the transient
    ``LogInRequest`` and the session cookie lives in the transport's cookie jar
    — so the default dataclass ``repr`` is already credential-safe.

    The ``allow_unknown_host`` escape hatch (and ``KALSHI_KLEAR_ALLOW_UNKNOWN_HOST=1``)
    relaxes the host check for mock servers / proxies.
    """

    base_url: str = PRODUCTION_KLEAR_URL  # trailing slash stripped automatically

    def __post_init__(self) -> None:
        # NB: deliberately does NOT call super().__post_init__() — the parent
        # validates the /trade-api/v2 path + prediction hosts and the WS URL,
        # none of which apply to Klear. The checks below manually mirror the
        # host-agnostic KalshiConfig.__post_init__ guards (base_url slash strip,
        # scheme + plaintext-to-remote, KALSHI-ACCESS-* rejection, extra_headers
        # freeze, http2/h2 check); mirror any newly added KalshiConfig guard here.
        if self.base_url.endswith("/"):
            object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        allow_unknown = self.allow_unknown_host or (
            os.environ.get("KALSHI_KLEAR_ALLOW_UNKNOWN_HOST", "").strip() == "1"
        )
        parsed = urlparse(self.base_url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if scheme not in ("https", "http"):
            raise ValueError(
                f"KlearConfig.base_url must use https:// or http://, got "
                f"scheme={scheme!r} (url={self.base_url!r})"
            )
        if not host:
            raise ValueError(f"KlearConfig.base_url is missing a host: {self.base_url!r}")
        if scheme == "http" and host not in _LOCAL_HOSTS:
            raise ValueError(
                f"KlearConfig.base_url must use https:// for non-loopback hosts; "
                f"http:// is only allowed for {sorted(_LOCAL_HOSTS)} (url={self.base_url!r}). "
                f"Plaintext to a remote host would expose the session cookie."
            )
        if host not in _KLEAR_KNOWN_HOSTS and host not in _LOCAL_HOSTS:
            if not allow_unknown:
                raise ValueError(
                    f"KlearConfig.base_url host {host!r} is not a known Kalshi Klear "
                    f"endpoint. Known hosts: {sorted(_KLEAR_KNOWN_HOSTS)}. If this is an "
                    "intentional mock server or proxy, opt in with "
                    "KlearConfig(allow_unknown_host=True) or set "
                    "KALSHI_KLEAR_ALLOW_UNKNOWN_HOST=1."
                )
            logger.warning(
                "KlearConfig.base_url host %r is not a known Kalshi Klear endpoint (%s). "
                "The session cookie will be sent there — verify this is intentional.",
                host,
                sorted(_KLEAR_KNOWN_HOSTS),
            )
        # #202-style path guard: enforce /klear-api/v1 (NOT /trade-api/v2).
        if parsed.path != "/klear-api/v1":
            raise ValueError(
                f"KlearConfig.base_url must include the /klear-api/v1 path component, "
                f"got base_url={self.base_url!r}"
            )
        # Reject KALSHI-ACCESS-* in extra_headers (harmless for Klear, kept for parity).
        if self.extra_headers:
            leaked = sorted(
                k for k in self.extra_headers if k.lower().startswith(AUTH_HEADER_PREFIX)
            )
            if leaked:
                raise ValueError(
                    f"KlearConfig.extra_headers must not include KALSHI-ACCESS-* keys "
                    f"(got: {leaked!r})."
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

    @classmethod
    def production(cls, **kwargs: object) -> KlearConfig:
        """Create config for the Kalshi Klear production environment."""
        return cls(base_url=PRODUCTION_KLEAR_URL, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def demo(cls, **kwargs: object) -> KlearConfig:
        """Create config for the Kalshi Klear demo environment."""
        return cls(base_url=DEMO_KLEAR_URL, **kwargs)  # type: ignore[arg-type]

"""Connectivity configuration for the Kalshi FIX gateway.

Resolves the TCP host + port and session parameters for a given product
(prediction vs margin), environment (production vs demo), and session type
(NR/RT/DC/PT/RFQ/MD). Mirrors the security posture of
:class:`kalshi.config.KalshiConfig`: TLS is required to non-loopback hosts, and
a host override outside the known Kalshi FIX endpoints must be opted into.

Endpoint tables come from docs.kalshi.com/fix/connectivity and
docs.kalshi.com/fix-margin/connectivity (see GH #402 / the spec-facts memo).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

# Production prediction market-data is served from the order-entry host in the
# published table; demo splits it onto a dedicated marketdata host. Margin
# production likewise co-locates MD with order entry, while demo splits it.


class FixEnvironment(StrEnum):
    """Kalshi FIX environment."""

    PRODUCTION = "production"
    DEMO = "demo"


class FixProduct(StrEnum):
    """Which Kalshi product line the FIX session trades."""

    PREDICTION = "prediction"
    MARGIN = "margin"


class FixSessionType(StrEnum):
    """FIX session type. The value is the wire ``TargetCompID`` (tag 56)."""

    ORDER_ENTRY_NR = "KalshiNR"
    ORDER_ENTRY_RT = "KalshiRT"
    DROP_COPY = "KalshiDC"
    POST_TRADE = "KalshiPT"
    RFQ = "KalshiRFQ"
    MARKET_DATA = "KalshiMD"


# Port is identical across products and environments.
_SESSION_PORTS: dict[FixSessionType, int] = {
    FixSessionType.ORDER_ENTRY_NR: 8228,
    FixSessionType.ORDER_ENTRY_RT: 8230,
    FixSessionType.DROP_COPY: 8229,
    FixSessionType.POST_TRADE: 8231,
    FixSessionType.RFQ: 8232,
    FixSessionType.MARKET_DATA: 8233,
}

# Sessions that support message retransmission (ResendRequest / SequenceReset).
# Everything else must logon with ResetSeqNumFlag=Y. PT is prediction-only.
_RETRANSMISSION_SESSIONS: frozenset[FixSessionType] = frozenset(
    {FixSessionType.ORDER_ENTRY_RT, FixSessionType.POST_TRADE}
)

# Allowed session types per product. Margin has no Post-Trade or RFQ sessions.
_PRODUCT_SESSIONS: dict[FixProduct, frozenset[FixSessionType]] = {
    FixProduct.PREDICTION: frozenset(FixSessionType),
    FixProduct.MARGIN: frozenset(
        {
            FixSessionType.ORDER_ENTRY_NR,
            FixSessionType.ORDER_ENTRY_RT,
            FixSessionType.DROP_COPY,
            FixSessionType.MARKET_DATA,
        }
    ),
}

# (product, environment) -> (order-entry host, market-data host).
_HOSTS: dict[tuple[FixProduct, FixEnvironment], tuple[str, str]] = {
    (FixProduct.PREDICTION, FixEnvironment.PRODUCTION): (
        "mm.fix.elections.kalshi.com",
        "mm.fix.elections.kalshi.com",
    ),
    (FixProduct.PREDICTION, FixEnvironment.DEMO): (
        "fix.demo.kalshi.co",
        "marketdata.fix.demo.kalshi.co",
    ),
    (FixProduct.MARGIN, FixEnvironment.PRODUCTION): (
        "margin-fix-api.fix.elections.kalshi.com",
        "margin-fix-api.fix.elections.kalshi.com",
    ),
    (FixProduct.MARGIN, FixEnvironment.DEMO): (
        "margin-fix.demo.kalshi.co",
        "margin-marketdata.fix.demo.kalshi.co",
    ),
}

# Every known Kalshi FIX host, for validating a host override.
_KNOWN_FIX_HOSTS: frozenset[str] = frozenset(
    host for pair in _HOSTS.values() for host in pair
)
_LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

# Default heartbeat interval (seconds). Server requires > 3.
DEFAULT_HEARTBEAT_INTERVAL = 30
DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 10


@dataclass(frozen=True)
class FixConfig:
    """FIX connectivity + session configuration.

    A single config describes a product/environment plus tuning; the concrete
    host/port are resolved per :class:`FixSessionType` (one TCP connection per
    session, one connection per API key). ``host`` / ``port`` overrides target a
    mock server or a local TLS proxy (stunnel) and, when set, apply to every
    session.

    A non-loopback ``host`` override outside the known Kalshi FIX endpoints is
    rejected unless ``allow_unknown_host=True`` or the process-wide
    ``KALSHI_FIX_ALLOW_UNKNOWN_HOST=1`` environment variable is set (an escape
    hatch for CI / staging proxies).

    Use :meth:`prediction` / :meth:`margin` for the canonical environments.
    """

    product: FixProduct = FixProduct.PREDICTION
    environment: FixEnvironment = FixEnvironment.PRODUCTION
    host: str | None = None
    port: int | None = None
    use_tls: bool = True
    heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_base_delay: float = 0.5
    retry_max_delay: float = 30.0
    cancel_orders_on_disconnect: bool = False
    # Listener (read-only streaming) session: receive execution reports without
    # an order-entry capability. Valid on NR/RT and requires skip_pending_exec_reports.
    listener_session: bool = False
    skip_pending_exec_reports: bool = False
    # ``None`` derives from the product: margin always uses fixed-point dollars,
    # prediction defaults to integer cents (opt into dollars by setting True).
    use_dollars: bool | None = None
    allow_unknown_host: bool = False

    def __post_init__(self) -> None:
        # Prediction requires HeartBtInt > 3; margin requires >= 3.
        min_hb = 4 if self.product is FixProduct.PREDICTION else 3
        if self.heartbeat_interval < min_hb:
            raise ValueError(
                f"FixConfig.heartbeat_interval must be >= {min_hb} for the "
                f"{self.product.value} FIX gateway (server requirement), "
                f"got {self.heartbeat_interval}"
            )
        if self.port is not None and not (0 < self.port < 65536):
            raise ValueError(f"FixConfig.port must be 1..65535, got {self.port}")
        if self.listener_session and not self.skip_pending_exec_reports:
            raise ValueError(
                "FixConfig.listener_session=True requires skip_pending_exec_reports=True "
                "(per the Kalshi FIX spec)."
            )

        allow_unknown = self.allow_unknown_host or (
            os.environ.get("KALSHI_FIX_ALLOW_UNKNOWN_HOST", "").strip() == "1"
        )
        if self.host is not None:
            host = self.host.lower()
            is_local = host in _LOCAL_HOSTS
            if not self.use_tls and not is_local:
                raise ValueError(
                    f"FixConfig.use_tls=False is only allowed for loopback hosts "
                    f"{sorted(_LOCAL_HOSTS)}; plaintext FIX to a remote host "
                    f"({self.host!r}) would expose the logon signature."
                )
            if host not in _KNOWN_FIX_HOSTS and not is_local and not allow_unknown:
                raise ValueError(
                    f"FixConfig.host {self.host!r} is not a known Kalshi FIX endpoint. "
                    f"Known hosts: {sorted(_KNOWN_FIX_HOSTS)}. If this is an intentional "
                    "mock server or TLS proxy, opt in with FixConfig(allow_unknown_host=True) "
                    "or set KALSHI_FIX_ALLOW_UNKNOWN_HOST=1."
                )
        elif not self.use_tls:
            # No host override: every session resolves to a real Kalshi FIX
            # gateway, which mandates TLS 1.2+. Plaintext there would expose the
            # logon signature. use_tls=False is only for a loopback host override.
            raise ValueError(
                "FixConfig.use_tls=False is only allowed with a loopback host override "
                "(e.g. host='127.0.0.1' for a mock server or local TLS proxy); the Kalshi "
                "FIX gateways require TLS 1.2+ (plaintext would expose the logon signature)."
            )

    @classmethod
    def prediction(
        cls,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        *,
        host: str | None = None,
        port: int | None = None,
        use_tls: bool = True,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 30.0,
        cancel_orders_on_disconnect: bool = False,
        listener_session: bool = False,
        skip_pending_exec_reports: bool = False,
        use_dollars: bool | None = None,
        allow_unknown_host: bool = False,
    ) -> FixConfig:
        """Config for the prediction (event-contract) FIX gateway."""
        return cls(
            product=FixProduct.PREDICTION,
            environment=environment,
            host=host,
            port=port,
            use_tls=use_tls,
            heartbeat_interval=heartbeat_interval,
            connect_timeout=connect_timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
            cancel_orders_on_disconnect=cancel_orders_on_disconnect,
            listener_session=listener_session,
            skip_pending_exec_reports=skip_pending_exec_reports,
            use_dollars=use_dollars,
            allow_unknown_host=allow_unknown_host,
        )

    @classmethod
    def margin(
        cls,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        *,
        host: str | None = None,
        port: int | None = None,
        use_tls: bool = True,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 30.0,
        cancel_orders_on_disconnect: bool = False,
        listener_session: bool = False,
        skip_pending_exec_reports: bool = False,
        use_dollars: bool = True,
        allow_unknown_host: bool = False,
    ) -> FixConfig:
        """Config for the margin (perps) FIX gateway (fixed-point dollars enforced)."""
        return cls(
            product=FixProduct.MARGIN,
            environment=environment,
            host=host,
            port=port,
            use_tls=use_tls,
            heartbeat_interval=heartbeat_interval,
            connect_timeout=connect_timeout,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            retry_max_delay=retry_max_delay,
            cancel_orders_on_disconnect=cancel_orders_on_disconnect,
            listener_session=listener_session,
            skip_pending_exec_reports=skip_pending_exec_reports,
            use_dollars=use_dollars,
            allow_unknown_host=allow_unknown_host,
        )

    @property
    def allowed_sessions(self) -> frozenset[FixSessionType]:
        """Session types valid for this product."""
        return _PRODUCT_SESSIONS[self.product]

    @property
    def effective_use_dollars(self) -> bool:
        """Resolved ``UseDollars`` flag: margin is always on; prediction opt-in."""
        if self.product is FixProduct.MARGIN:
            return True
        return bool(self.use_dollars)

    def _check_session(self, session: FixSessionType) -> None:
        if session not in self.allowed_sessions:
            raise ValueError(
                f"session {session.value!r} is not available for product "
                f"{self.product.value!r}. Allowed: "
                f"{sorted(s.value for s in self.allowed_sessions)}"
            )

    def host_for(self, session: FixSessionType) -> str:
        """Resolve the TCP host for ``session`` (honoring a ``host`` override)."""
        self._check_session(session)
        if self.host is not None:
            return self.host
        oe_host, md_host = _HOSTS[(self.product, self.environment)]
        return md_host if session is FixSessionType.MARKET_DATA else oe_host

    def port_for(self, session: FixSessionType) -> int:
        """Resolve the TCP port for ``session`` (honoring a ``port`` override)."""
        self._check_session(session)
        if self.port is not None:
            return self.port
        return _SESSION_PORTS[session]

    def target_comp_id(self, session: FixSessionType) -> str:
        """The wire ``TargetCompID`` (tag 56) for ``session``."""
        return session.value

    def supports_retransmission(self, session: FixSessionType) -> bool:
        """Whether ``session`` supports ResendRequest/SequenceReset recovery.

        When ``False`` the session must logon with ``ResetSeqNumFlag=Y`` and a
        forward sequence gap is unrecoverable.
        """
        return session in _RETRANSMISSION_SESSIONS

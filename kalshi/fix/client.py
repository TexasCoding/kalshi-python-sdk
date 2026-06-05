"""High-level FIX client facades.

Thin convenience over :class:`kalshi.fix.session.FixSession`: hold the signer +
config and mint a session per :class:`~kalshi.fix.config.FixSessionType`. The
prediction client is :class:`FixClient`; the margin client lives in
:mod:`kalshi.perps.fix` and reuses the shared core via :class:`_BaseFixClient`.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from typing import ClassVar, Self

from kalshi.auth import KalshiAuth
from kalshi.fix.auth import FixSigner
from kalshi.fix.config import FixConfig, FixEnvironment, FixProduct, FixSessionType
from kalshi.fix.session import FixSession, MessageHandler, StateChangeHandler


class _BaseFixClient:
    """Shared FIX client logic: holds signer + config, constructs sessions.

    Subclasses set ``_PRODUCT`` to bind the client to a product line. Concrete
    session-type helpers live on the product-specific subclasses so only the
    sessions a product actually supports are exposed.
    """

    _PRODUCT: ClassVar[FixProduct]

    def __init__(
        self,
        signer: FixSigner,
        *,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        config: FixConfig | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._signer = signer
        self._ssl_context = ssl_context
        if config is None:
            config = FixConfig(product=self._PRODUCT, environment=environment)
        elif config.product is not self._PRODUCT:
            raise ValueError(
                f"config.product {config.product.value!r} does not match this "
                f"client's product {self._PRODUCT.value!r}"
            )
        self._config = config

    @classmethod
    def from_auth(
        cls,
        auth: KalshiAuth,
        *,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        config: FixConfig | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> Self:
        """Build a client reusing an existing :class:`KalshiAuth`'s key."""
        return cls(
            FixSigner.from_auth(auth),
            environment=environment,
            config=config,
            ssl_context=ssl_context,
        )

    @property
    def signer(self) -> FixSigner:
        """The logon signer."""
        return self._signer

    @property
    def config(self) -> FixConfig:
        """The resolved connectivity config."""
        return self._config

    def session(
        self,
        session_type: FixSessionType,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """Construct (but do not start) a :class:`FixSession` for ``session_type``."""
        return FixSession(
            self._signer,
            self._config,
            session_type,
            on_message=on_message,
            on_state_change=on_state_change,
            ssl_context=self._ssl_context,
        )

    def order_entry(
        self,
        *,
        retransmission: bool = False,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """An order-entry session (KalshiNR, or KalshiRT when ``retransmission``)."""
        session_type = (
            FixSessionType.ORDER_ENTRY_RT if retransmission else FixSessionType.ORDER_ENTRY_NR
        )
        return self.session(
            session_type, on_message=on_message, on_state_change=on_state_change
        )

    def drop_copy(
        self,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """A drop-copy (KalshiDC) session for historical execution-report queries."""
        return self.session(
            FixSessionType.DROP_COPY, on_message=on_message, on_state_change=on_state_change
        )

    def market_data(
        self,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """A market-data (KalshiMD) session for order-book snapshots and updates."""
        return self.session(
            FixSessionType.MARKET_DATA, on_message=on_message, on_state_change=on_state_change
        )


class FixClient(_BaseFixClient):
    """FIX client for the prediction (event-contract) gateway.

    Supports all six session types: order entry (NR/RT), drop copy, market data,
    post trade, and RFQ. Construct from a :class:`FixSigner`, or from an existing
    :class:`KalshiAuth` via :meth:`from_auth` / the ``KALSHI_*`` env via
    :meth:`from_env`.
    """

    _PRODUCT = FixProduct.PREDICTION

    @classmethod
    def from_env(
        cls,
        *,
        environment: FixEnvironment = FixEnvironment.PRODUCTION,
        config: FixConfig | None = None,
        ssl_context: ssl.SSLContext | None = None,
        password: bytes | str | Callable[[], bytes | str] | None = None,
    ) -> FixClient:
        """Build a prediction FIX client from the ``KALSHI_*`` environment vars.

        ``password`` (or ``KALSHI_PRIVATE_KEY_PASSPHRASE``) decrypts a
        passphrase-protected private key — parity with the REST client.
        """
        return cls(
            FixSigner.from_env(password=password),
            environment=environment,
            config=config,
            ssl_context=ssl_context,
        )

    def post_trade(
        self,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """A post-trade (KalshiPT) session for market-settlement reports."""
        return self.session(
            FixSessionType.POST_TRADE, on_message=on_message, on_state_change=on_state_change
        )

    def rfq(
        self,
        *,
        on_message: MessageHandler | None = None,
        on_state_change: StateChangeHandler | None = None,
    ) -> FixSession:
        """An RFQ (KalshiRFQ) market-maker session."""
        return self.session(
            FixSessionType.RFQ, on_message=on_message, on_state_change=on_state_change
        )

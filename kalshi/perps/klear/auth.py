"""Cookie-session auth holder for the Klear (SCM) API.

Unlike :class:`kalshi.auth.KalshiAuth` (an RSA-PSS request signer), ``KlearAuth``
is a lightweight **session-state holder**: it has no private key and no
``sign_request`` method. The actual ``session`` cookie is captured and replayed
by the transport's httpx cookie jar; this class only tracks whether a session is
active (and optionally the opaque login token for caller inspection).

Security: the token is a bearer credential — it is never logged and is redacted
from ``repr()``.
"""

from __future__ import annotations


class KlearAuth:
    """Tracks Klear session state. Holds no RSA key and signs nothing."""

    def __init__(self) -> None:
        self._authenticated: bool = False
        self._token: str | None = None

    @property
    def is_authenticated(self) -> bool:
        """Whether a Klear session has been established via ``log_in``."""
        return self._authenticated

    @property
    def token(self) -> str | None:
        """The opaque login token, if the server returned one. Treat as secret."""
        return self._token

    def mark_logged_in(self, token: str | None = None) -> None:
        """Flag the session active after a successful (non-MFA-challenge) login."""
        self._authenticated = True
        self._token = token

    def reset(self) -> None:
        """Clear session state (e.g. on logout / client close)."""
        self._authenticated = False
        self._token = None

    def __repr__(self) -> str:
        # Never leak the token.
        return f"KlearAuth(authenticated={self._authenticated})"

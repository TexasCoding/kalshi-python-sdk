"""Bearer-token credential holder for the Klear (SCM) API.

Unlike :class:`kalshi.auth.KalshiAuth` (an RSA-PSS request signer), ``KlearAuth``
holds a pre-generated Klear admin access token and produces the static
``Authorization: Bearer <admin_user_id>:<access_token>`` header the Klear API
requires on every request. Generate the token and find your admin user id by
signing in at https://klearing.kalshi.com and opening the "Security" page.

Security: the access token is a bearer credential — it is never logged and is
redacted from ``repr()``.
"""

from __future__ import annotations


class KlearAuth:
    """Holds Klear Bearer credentials and builds the ``Authorization`` header."""

    def __init__(self, admin_user_id: str, access_token: str) -> None:
        # Reject whitespace-only (and None) credentials too — a blank token is
        # truthy but yields a malformed ``Bearer   :   `` header. The leading
        # falsy check short-circuits before ``.strip()`` so None can't AttributeError.
        if (
            not admin_user_id
            or not admin_user_id.strip()
            or not access_token
            or not access_token.strip()
        ):
            raise ValueError(
                "KlearAuth requires a non-empty admin_user_id and access_token."
            )
        self._admin_user_id = admin_user_id
        self._access_token = access_token

    @property
    def admin_user_id(self) -> str:
        """The Klear admin user id (not secret)."""
        return self._admin_user_id

    @property
    def access_token(self) -> str:
        """The Klear access token. Treat as secret."""
        return self._access_token

    def authorization_header(self) -> str:
        """Value for the ``Authorization`` header: ``Bearer <admin_user_id>:<access_token>``."""
        return f"Bearer {self._admin_user_id}:{self._access_token}"

    def __repr__(self) -> str:
        # access_token is a bearer credential; redact it.
        return f"KlearAuth(admin_user_id={self._admin_user_id!r}, access_token=<redacted>)"

    __str__ = __repr__

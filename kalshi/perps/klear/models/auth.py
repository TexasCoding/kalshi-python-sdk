"""Klear (SCM) login request/response models.

Security: :class:`LogInRequest` carries the ``email`` / ``password`` / ``code``
secrets. It is serialized only into the request body (never logged — the
transport logs ``METHOD path`` only) and gets no field-leaking ``repr``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LogInRequest(BaseModel):
    """Spec ``LogInRequest`` — body for ``POST /log_in`` (``extra="forbid"``).

    Two-phase: call first with ``email`` + ``password``; if the response carries
    ``required_mfa_method``, re-call with the same credentials plus ``code``.
    """

    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    code: str | None = None

    def __repr__(self) -> str:
        # Never leak credentials in repr / logs / tracebacks.
        return "LogInRequest(email=<redacted>, password=<redacted>, code=<redacted>)"

    __str__ = __repr__


class LogInResponse(BaseModel):
    """Spec ``LogInResponse`` — all fields optional.

    On success, ``token`` / ``user_id`` are present and the ``session`` cookie is
    set via ``Set-Cookie`` (captured by the transport's cookie jar). When
    ``required_mfa_method`` is non-null, MFA is required: re-call ``log_in`` with
    ``code``. The SDK does not auto-loop on MFA — it returns this response so the
    caller can supply the out-of-band code.
    """

    model_config = ConfigDict(extra="allow")

    token: str | None = None
    user_id: str | None = None
    access_level: str | None = None
    required_mfa_method: str | None = None

    def __repr__(self) -> str:
        # `token` is a bearer credential; redact it but surface the MFA signal.
        return (
            f"LogInResponse(user_id={self.user_id!r}, "
            f"access_level={self.access_level!r}, "
            f"required_mfa_method={self.required_mfa_method!r}, token=<redacted>)"
        )

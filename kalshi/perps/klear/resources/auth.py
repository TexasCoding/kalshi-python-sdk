"""Klear (SCM) authentication resource — ``POST /log_in``."""

from __future__ import annotations

from kalshi.perps.klear.models.auth import LogInRequest, LogInResponse
from kalshi.perps.klear.resources._base import KlearAsyncResource, KlearSyncResource


class AuthResource(KlearSyncResource):
    """Sync Klear auth API (``log_in``)."""

    def log_in(self, *, email: str, password: str, code: str | None = None) -> LogInResponse:
        """Log in to the Klear API (unauthenticated bootstrap; ``security: []``).

        Posts ``email`` + ``password`` (+ optional MFA ``code``). On success the
        transport's cookie jar captures the ``session`` cookie and replays it on
        subsequent requests, and the client's session is marked active. If the
        response carries ``required_mfa_method``, the session is **not** marked
        active — re-call with ``code`` (the SDK does not conjure the OOB code).

        ``POST /log_in`` is never retried (the transport enforces no-retry on
        POST), so a login is never silently replayed.

        Any prior session is invalidated **before** the attempt: the
        :class:`KlearAuth` state is reset and the stale ``session`` cookie is
        dropped, so the client is definitively unauthenticated until a clean
        (non-MFA-challenge) success — re-logging into a different account that
        returns an MFA challenge can never leave the previous account active.
        """
        self._klear_auth.reset()
        self._transport.clear_cookie("session")
        req = LogInRequest(email=email, password=password, code=code)
        data = self._post(
            "/log_in",
            json=req.model_dump(exclude_none=True, by_alias=True, mode="json"),
        )
        resp = LogInResponse.model_validate(data)
        if resp.required_mfa_method is None:
            self._klear_auth.mark_logged_in(resp.token)
        return resp


class AsyncAuthResource(KlearAsyncResource):
    """Async Klear auth API (``log_in``)."""

    async def log_in(
        self, *, email: str, password: str, code: str | None = None
    ) -> LogInResponse:
        """Async :meth:`AuthResource.log_in`."""
        self._klear_auth.reset()
        self._transport.clear_cookie("session")
        req = LogInRequest(email=email, password=password, code=code)
        data = await self._post(
            "/log_in",
            json=req.model_dump(exclude_none=True, by_alias=True, mode="json"),
        )
        resp = LogInResponse.model_validate(data)
        if resp.required_mfa_method is None:
            self._klear_auth.mark_logged_in(resp.token)
        return resp

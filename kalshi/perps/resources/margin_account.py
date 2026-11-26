"""Perps margin-account resource — balance, risk, notional risk limit, fee tiers, API limits.

Read-only GET endpoints. ``balance`` / ``risk`` / ``notional_risk_limit`` /
``fee_tiers`` / ``fee_tier_rates`` / ``api_limits`` /
``corporate_action_payment_history`` carry a spec ``security`` block, so each
of those methods calls ``_require_auth()`` first — an unauthenticated caller
gets ``AuthRequiredError`` client-side instead of a server 401.
``corporate_actions`` is public market data (no spec ``security`` block) and
does not require auth. None are paginated (no response carries a cursor), so
there are no ``list_all()`` iterators. All retry on 429/502/503/504 (GET).

``api_limits`` (``GET /account/limits/perps``) returns the Perps API tier limits
in the same shape as the prediction API's :class:`~kalshi.models.account.AccountApiLimits`,
so the SDK reuses that model rather than duplicating it.
"""

from __future__ import annotations

from datetime import date, datetime

from kalshi.models.account import AccountApiLimits
from kalshi.perps.models.margin_account import (
    GetMarginBalanceResponse,
    GetMarginCorporateActionPaymentHistoryResponse,
    GetMarginCorporateActionsResponse,
    GetMarginFeeTierRatesResponse,
    GetMarginFeeTiersResponse,
    GetMarginRiskResponse,
    NotionalRiskLimitResponse,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


def _iso_date(value: date | str) -> str:
    """Serialize a required date query param as ``YYYY-MM-DD``.

    Accepts :class:`datetime.date` or an already-formatted string. A
    :class:`datetime.datetime` is reduced to its calendar date first because
    ``datetime`` is a ``date`` subclass whose ``isoformat()`` includes time.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class MarginAccountResource(SyncResource):
    """Sync perps margin-account API (balance / risk / fee tiers / corporate actions)."""

    def balance(
        self,
        *,
        compute_available_balance: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginBalanceResponse:
        self._require_auth()
        params = _params(compute_available_balance=compute_available_balance)
        data = self._get("/margin/balance", params=params, extra_headers=extra_headers)
        return GetMarginBalanceResponse.model_validate(data)

    def risk(self, *, extra_headers: dict[str, str] | None = None) -> GetMarginRiskResponse:
        self._require_auth()
        data = self._get("/margin/risk", extra_headers=extra_headers)
        return GetMarginRiskResponse.model_validate(data)

    def notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> NotionalRiskLimitResponse:
        self._require_auth()
        data = self._get("/margin/notional_risk_limit", extra_headers=extra_headers)
        return NotionalRiskLimitResponse.model_validate(data)

    def fee_tiers(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTiersResponse:
        self._require_auth()
        data = self._get("/margin/fee_tiers", extra_headers=extra_headers)
        return GetMarginFeeTiersResponse.model_validate(data)

    def fee_tier_rates(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTierRatesResponse:
        """``GET /margin/fee_tier_rates`` — maker/taker rates by fee-schedule tier."""
        self._require_auth()
        data = self._get("/margin/fee_tier_rates", extra_headers=extra_headers)
        return GetMarginFeeTierRatesResponse.model_validate(data)

    def api_limits(self, *, extra_headers: dict[str, str] | None = None) -> AccountApiLimits:
        """Perps (margin) API tier limits for the authenticated user.

        ``GET /account/limits/perps``. Same response shape as the prediction
        API's ``GET /account/limits`` (:class:`~kalshi.models.account.AccountApiLimits`).
        """
        self._require_auth()
        data = self._get("/account/limits/perps", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)

    def corporate_actions(
        self,
        *,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginCorporateActionsResponse:
        """Scheduled notices and notices updated in the last seven days.

        ``GET /margin/corporate_actions``. Public market data — no auth.
        Optional ``ticker`` / ``market_id`` filter to one market; omit both
        for notices across all margin markets. Cancelled notices omit terms
        and ``execution_time``.
        """
        params = _params(ticker=ticker, market_id=market_id)
        data = self._get(
            "/margin/corporate_actions", params=params, extra_headers=extra_headers
        )
        return GetMarginCorporateActionsResponse.model_validate(data)

    def corporate_action_payment_history(
        self,
        *,
        start_date: date | str,
        end_date: date | str,
        ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginCorporateActionPaymentHistoryResponse:
        """Cash received or paid for corporate actions in a UTC date range.

        ``GET /margin/corporate_action_payment_history``. Auth required.
        ``start_date`` and ``end_date`` are inclusive YYYY-MM-DD (accept
        :class:`datetime.date` or ``str``). Optional ``ticker`` filters to
        one market; omit for all markets. Optional ``subaccount``; omit for
        all subaccounts. Stock split adjustments are not included.
        """
        self._require_auth()
        params = _params(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            ticker=ticker,
            subaccount=subaccount,
        )
        data = self._get(
            "/margin/corporate_action_payment_history",
            params=params,
            extra_headers=extra_headers,
        )
        return GetMarginCorporateActionPaymentHistoryResponse.model_validate(data)


class AsyncMarginAccountResource(AsyncResource):
    """Async perps margin-account API (balance / risk / fee tiers / corporate actions)."""

    async def balance(
        self,
        *,
        compute_available_balance: bool | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginBalanceResponse:
        self._require_auth()
        params = _params(compute_available_balance=compute_available_balance)
        data = await self._get("/margin/balance", params=params, extra_headers=extra_headers)
        return GetMarginBalanceResponse.model_validate(data)

    async def risk(self, *, extra_headers: dict[str, str] | None = None) -> GetMarginRiskResponse:
        self._require_auth()
        data = await self._get("/margin/risk", extra_headers=extra_headers)
        return GetMarginRiskResponse.model_validate(data)

    async def notional_risk_limit(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> NotionalRiskLimitResponse:
        self._require_auth()
        data = await self._get("/margin/notional_risk_limit", extra_headers=extra_headers)
        return NotionalRiskLimitResponse.model_validate(data)

    async def fee_tiers(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTiersResponse:
        self._require_auth()
        data = await self._get("/margin/fee_tiers", extra_headers=extra_headers)
        return GetMarginFeeTiersResponse.model_validate(data)

    async def fee_tier_rates(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginFeeTierRatesResponse:
        """Async :meth:`MarginAccountResource.fee_tier_rates`."""
        self._require_auth()
        data = await self._get("/margin/fee_tier_rates", extra_headers=extra_headers)
        return GetMarginFeeTierRatesResponse.model_validate(data)

    async def api_limits(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> AccountApiLimits:
        """Perps (margin) API tier limits for the authenticated user.

        ``GET /account/limits/perps``. Same response shape as the prediction
        API's ``GET /account/limits`` (:class:`~kalshi.models.account.AccountApiLimits`).
        """
        self._require_auth()
        data = await self._get("/account/limits/perps", extra_headers=extra_headers)
        return AccountApiLimits.model_validate(data)

    async def corporate_actions(
        self,
        *,
        ticker: str | None = None,
        market_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginCorporateActionsResponse:
        """Async :meth:`MarginAccountResource.corporate_actions`."""
        params = _params(ticker=ticker, market_id=market_id)
        data = await self._get(
            "/margin/corporate_actions", params=params, extra_headers=extra_headers
        )
        return GetMarginCorporateActionsResponse.model_validate(data)

    async def corporate_action_payment_history(
        self,
        *,
        start_date: date | str,
        end_date: date | str,
        ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginCorporateActionPaymentHistoryResponse:
        """Async :meth:`MarginAccountResource.corporate_action_payment_history`."""
        self._require_auth()
        params = _params(
            start_date=_iso_date(start_date),
            end_date=_iso_date(end_date),
            ticker=ticker,
            subaccount=subaccount,
        )
        data = await self._get(
            "/margin/corporate_action_payment_history",
            params=params,
            extra_headers=extra_headers,
        )
        return GetMarginCorporateActionPaymentHistoryResponse.model_validate(data)

"""Klear (SCM) margin resource — settlement obligations, estimates, balances (#400).

Nine Self-Clearing-Member margin endpoints on the Klear client (``klear-api/v1``),
all requiring an active **session cookie** (not RSA-PSS):

- ``margin_reports`` — ``GET /margin/reports``: flat array, required ``start_date``
  / ``end_date`` (``YYYY-MM-DD``).
- ``active_obligation`` — ``GET /margin/active_obligation``: current-cycle
  obligation (nullable).
- ``obligation_history`` / ``obligation_history_all`` — ``GET
  /margin/obligation_history``: cursor-paginated (limit max 100).
- ``settlement_estimate`` — ``GET /margin/settlement_estimate``.
- ``settlement_balance`` — ``GET /margin/settlement_balance``.
- ``guaranty_fund_balance`` — ``GET /margin/guaranty_fund_balance``.
- ``settlement_balance_history`` / ``settlement_balance_history_all`` — ``GET
  /margin/settlement_balance_history``: cursor-paginated (limit max 500).
- ``withdraw_settlement_balance`` — ``POST /margin/withdraw_settlement_balance``:
  ``WithdrawSettlementBalanceRequest`` body; NOT retried (POST).
- ``settlement_balance_withdrawal`` — ``GET /margin/settlement_balance_withdrawal``:
  withdrawal status by required ``id``.

These bind to the Klear session guard (``_require_session()`` from the Klear
resource base), NOT the RSA-specific ``_require_auth()``. Every method calls
``_require_session()`` first so an un-logged-in caller gets a clear
``AuthRequiredError`` with no wasted round trip.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.perps.klear.resources._base import KlearAsyncResource, KlearSyncResource
from kalshi.perps.models.margin import (
    GetActiveMarginObligationResponse,
    GetGuarantyFundBalanceResponse,
    GetMarginReportsResponse,
    GetSettlementBalanceResponse,
    GetSettlementBalanceWithdrawalResponse,
    GetSettlementEstimateResponse,
    ObligationEntry,
    SettlementBalanceHistoryEntry,
    WithdrawSettlementBalanceRequest,
    WithdrawSettlementBalanceResponse,
)
from kalshi.resources._base import _params, _validate_limit, _validate_max_pages
from kalshi.types import DollarDecimal, to_decimal


class MarginResource(KlearSyncResource):
    """Sync Klear (SCM) margin API — all nine endpoints + two paginators."""

    def margin_reports(
        self,
        *,
        start_date: str,
        end_date: str,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginReportsResponse:
        """``GET /margin/reports`` — reports in the ``[start_date, end_date]`` window.

        ``start_date`` / ``end_date`` are required ``YYYY-MM-DD`` strings.
        """
        self._require_session()
        params = _params(start_date=start_date, end_date=end_date)
        data = self._get("/margin/reports", params=params, extra_headers=extra_headers)
        return GetMarginReportsResponse.model_validate(data)

    def active_obligation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationResponse:
        """``GET /margin/active_obligation`` — current-cycle obligation (nullable)."""
        self._require_session()
        data = self._get("/margin/active_obligation", extra_headers=extra_headers)
        return GetActiveMarginObligationResponse.model_validate(data)

    def obligation_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[ObligationEntry]:
        """``GET /margin/obligation_history`` — one cursor-paginated page (limit max 100)."""
        self._require_session()
        params = _params(limit=_validate_limit(limit, hi=100), cursor=cursor)
        return self._list(
            "/margin/obligation_history",
            ObligationEntry,
            "obligations",
            params=params,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def obligation_history_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[ObligationEntry]:
        """Auto-paginate obligation history, yielding each ``ObligationEntry``."""
        self._require_session()
        _validate_max_pages(max_pages)
        params = _params(limit=_validate_limit(limit, hi=100), cursor=None)
        return self._list_all(
            "/margin/obligation_history",
            ObligationEntry,
            "obligations",
            params=params,
            max_pages=max_pages,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def settlement_estimate(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementEstimateResponse:
        """``GET /margin/settlement_estimate`` — next-settlement estimate + breakdowns."""
        self._require_session()
        data = self._get("/margin/settlement_estimate", extra_headers=extra_headers)
        return GetSettlementEstimateResponse.model_validate(data)

    def settlement_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceResponse:
        """``GET /margin/settlement_balance`` — settlement-buffer balance."""
        self._require_session()
        data = self._get("/margin/settlement_balance", extra_headers=extra_headers)
        return GetSettlementBalanceResponse.model_validate(data)

    def guaranty_fund_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetGuarantyFundBalanceResponse:
        """``GET /margin/guaranty_fund_balance`` — guaranty-fund contribution balance."""
        self._require_session()
        data = self._get("/margin/guaranty_fund_balance", extra_headers=extra_headers)
        return GetGuarantyFundBalanceResponse.model_validate(data)

    def settlement_balance_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[SettlementBalanceHistoryEntry]:
        """``GET /margin/settlement_balance_history`` — one page (limit max 500)."""
        self._require_session()
        params = _params(limit=_validate_limit(limit, hi=500), cursor=cursor)
        return self._list(
            "/margin/settlement_balance_history",
            SettlementBalanceHistoryEntry,
            "entries",
            params=params,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def settlement_balance_history_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[SettlementBalanceHistoryEntry]:
        """Auto-paginate settlement-balance history, yielding each entry."""
        self._require_session()
        _validate_max_pages(max_pages)
        params = _params(limit=_validate_limit(limit, hi=500), cursor=None)
        return self._list_all(
            "/margin/settlement_balance_history",
            SettlementBalanceHistoryEntry,
            "entries",
            params=params,
            max_pages=max_pages,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def withdraw_settlement_balance(
        self,
        *,
        amount: DollarDecimal | str,
        extra_headers: dict[str, str] | None = None,
    ) -> WithdrawSettlementBalanceResponse:
        """``POST /margin/withdraw_settlement_balance`` — initiate a wire withdrawal.

        ``amount`` is a fixed-point dollar string (``"500.00"``, positive). The
        request body is built from :class:`WithdrawSettlementBalanceRequest` and
        serialized to ``{"amount": "500.00"}``. POST is never retried.
        """
        self._require_session()
        req = WithdrawSettlementBalanceRequest(amount=to_decimal(amount))
        data = self._post(
            "/margin/withdraw_settlement_balance",
            json=req.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        return WithdrawSettlementBalanceResponse.model_validate(data)

    def settlement_balance_withdrawal(
        self, *, id: str, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceWithdrawalResponse:
        """``GET /margin/settlement_balance_withdrawal`` — withdrawal status by ``id``."""
        self._require_session()
        params = _params(id=id)
        data = self._get(
            "/margin/settlement_balance_withdrawal",
            params=params,
            extra_headers=extra_headers,
        )
        return GetSettlementBalanceWithdrawalResponse.model_validate(data)


class AsyncMarginResource(KlearAsyncResource):
    """Async Klear (SCM) margin API — all nine endpoints + two paginators."""

    async def margin_reports(
        self,
        *,
        start_date: str,
        end_date: str,
        extra_headers: dict[str, str] | None = None,
    ) -> GetMarginReportsResponse:
        """Async :meth:`MarginResource.margin_reports`."""
        self._require_session()
        params = _params(start_date=start_date, end_date=end_date)
        data = await self._get("/margin/reports", params=params, extra_headers=extra_headers)
        return GetMarginReportsResponse.model_validate(data)

    async def active_obligation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationResponse:
        """Async :meth:`MarginResource.active_obligation`."""
        self._require_session()
        data = await self._get("/margin/active_obligation", extra_headers=extra_headers)
        return GetActiveMarginObligationResponse.model_validate(data)

    async def obligation_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[ObligationEntry]:
        """Async :meth:`MarginResource.obligation_history`."""
        self._require_session()
        params = _params(limit=_validate_limit(limit, hi=100), cursor=cursor)
        return await self._list(
            "/margin/obligation_history",
            ObligationEntry,
            "obligations",
            params=params,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def obligation_history_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[ObligationEntry]:
        """Returns an async iterator over obligation history — use ``async for``."""
        self._require_session()
        _validate_max_pages(max_pages)
        params = _params(limit=_validate_limit(limit, hi=100), cursor=None)
        return self._list_all(
            "/margin/obligation_history",
            ObligationEntry,
            "obligations",
            params=params,
            max_pages=max_pages,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    async def settlement_estimate(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementEstimateResponse:
        """Async :meth:`MarginResource.settlement_estimate`."""
        self._require_session()
        data = await self._get("/margin/settlement_estimate", extra_headers=extra_headers)
        return GetSettlementEstimateResponse.model_validate(data)

    async def settlement_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceResponse:
        """Async :meth:`MarginResource.settlement_balance`."""
        self._require_session()
        data = await self._get("/margin/settlement_balance", extra_headers=extra_headers)
        return GetSettlementBalanceResponse.model_validate(data)

    async def guaranty_fund_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetGuarantyFundBalanceResponse:
        """Async :meth:`MarginResource.guaranty_fund_balance`."""
        self._require_session()
        data = await self._get("/margin/guaranty_fund_balance", extra_headers=extra_headers)
        return GetGuarantyFundBalanceResponse.model_validate(data)

    async def settlement_balance_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[SettlementBalanceHistoryEntry]:
        """Async :meth:`MarginResource.settlement_balance_history`."""
        self._require_session()
        params = _params(limit=_validate_limit(limit, hi=500), cursor=cursor)
        return await self._list(
            "/margin/settlement_balance_history",
            SettlementBalanceHistoryEntry,
            "entries",
            params=params,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    def settlement_balance_history_all(
        self,
        *,
        limit: int | None = None,
        max_pages: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> AsyncIterator[SettlementBalanceHistoryEntry]:
        """Returns an async iterator over settlement-balance history — use ``async for``."""
        self._require_session()
        _validate_max_pages(max_pages)
        params = _params(limit=_validate_limit(limit, hi=500), cursor=None)
        return self._list_all(
            "/margin/settlement_balance_history",
            SettlementBalanceHistoryEntry,
            "entries",
            params=params,
            max_pages=max_pages,
            cursor_key="cursor",
            extra_headers=extra_headers,
        )

    async def withdraw_settlement_balance(
        self,
        *,
        amount: DollarDecimal | str,
        extra_headers: dict[str, str] | None = None,
    ) -> WithdrawSettlementBalanceResponse:
        """Async :meth:`MarginResource.withdraw_settlement_balance`."""
        self._require_session()
        req = WithdrawSettlementBalanceRequest(amount=to_decimal(amount))
        data = await self._post(
            "/margin/withdraw_settlement_balance",
            json=req.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        return WithdrawSettlementBalanceResponse.model_validate(data)

    async def settlement_balance_withdrawal(
        self, *, id: str, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceWithdrawalResponse:
        """Async :meth:`MarginResource.settlement_balance_withdrawal`."""
        self._require_session()
        params = _params(id=id)
        data = await self._get(
            "/margin/settlement_balance_withdrawal",
            params=params,
            extra_headers=extra_headers,
        )
        return GetSettlementBalanceWithdrawalResponse.model_validate(data)

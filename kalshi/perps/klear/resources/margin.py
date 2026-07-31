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

The Klear resource base injects the ``Authorization: Bearer`` header on every
request (NOT the RSA-PSS ``KALSHI-ACCESS-*`` signing used by the trade-api
surfaces), so these methods carry no client-side auth guard — an invalid token
surfaces as a server 401 mapped to ``KalshiAuthError``.
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator, Iterator

from kalshi.models.common import Page
from kalshi.perps.klear.models.margin import (
    CreateMarginSubtraderGroupRequest,
    CreateMarginSubtraderGroupResponse,
    GetActiveMarginObligationResponse,
    GetActiveMarginObligationsResponse,
    GetGuarantyFundBalanceResponse,
    GetMarginReportsResponse,
    GetMarginSubtraderGroupsResponse,
    GetSettlementBalanceResponse,
    GetSettlementBalanceWithdrawalResponse,
    GetSettlementEstimateByAssetClassResponse,
    GetSettlementEstimateResponse,
    ObligationEntry,
    SettlementBalanceHistoryEntry,
    UpdateMarginSubtraderGroupRequest,
    WithdrawSettlementBalanceRequest,
    WithdrawSettlementBalanceResponse,
)
from kalshi.perps.klear.resources._base import KlearAsyncResource, KlearSyncResource
from kalshi.resources._base import (
    _check_request_exclusive,
    _params,
    _seg,
    _validate_limit,
    _validate_max_pages,
)
from kalshi.types import DollarDecimal, to_decimal


def _validate_date_range(start_date: str, end_date: str) -> None:
    """Validate ``YYYY-MM-DD`` ``start_date``/``end_date`` at the SDK boundary.

    The spec requires ISO ``date`` strings with ``end_date >= start_date``;
    catching a malformed or inverted range here surfaces a clear error instead
    of an opaque server 400.
    """
    try:
        start = datetime.date.fromisoformat(start_date)
        end = datetime.date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError(
            f"start_date / end_date must be YYYY-MM-DD strings (got "
            f"start_date={start_date!r}, end_date={end_date!r}): {exc}"
        ) from exc
    # ``date.fromisoformat`` (3.11+) also accepts non-canonical forms like
    # "20260605" or ISO week dates ("2026-W23-5"), which the raw string would
    # then forward to a server expecting strict YYYY-MM-DD. Require the canonical
    # form so the SDK rejects them here rather than relying on a server 400.
    for label, raw, parsed in (
        ("start_date", start_date, start),
        ("end_date", end_date, end),
    ):
        if parsed.isoformat() != raw:
            raise ValueError(
                f"{label} must be a canonical YYYY-MM-DD date, got {raw!r} "
                f"(parsed as {parsed.isoformat()})"
            )
    if end < start:
        raise ValueError(
            f"end_date ({end_date}) must be on or after start_date ({start_date})"
        )


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
        _validate_date_range(start_date, end_date)
        params = _params(start_date=start_date, end_date=end_date)
        data = self._get("/margin/reports", params=params, extra_headers=extra_headers)
        return GetMarginReportsResponse.model_validate(data)

    def active_obligation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationResponse:
        """``GET /margin/active_obligation`` — current-cycle obligation (nullable)."""
        data = self._get("/margin/active_obligation", extra_headers=extra_headers)
        return GetActiveMarginObligationResponse.model_validate(data)

    def active_obligations(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationsResponse:
        """``GET /margin/active_obligations`` — all currently-active obligations (spec v3.24.0)."""
        data = self._get("/margin/active_obligations", extra_headers=extra_headers)
        return GetActiveMarginObligationsResponse.model_validate(data)

    def obligation_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[ObligationEntry]:
        """``GET /margin/obligation_history`` — one cursor-paginated page (limit max 100)."""
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
        data = self._get("/margin/settlement_estimate", extra_headers=extra_headers)
        return GetSettlementEstimateResponse.model_validate(data)

    def settlement_estimate_by_asset_class(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementEstimateByAssetClassResponse:
        """``GET /margin/settlement_estimate_by_asset_class`` (spec v3.24.0).

        Next-settlement estimates keyed by asset class.
        """
        data = self._get(
            "/margin/settlement_estimate_by_asset_class", extra_headers=extra_headers
        )
        return GetSettlementEstimateByAssetClassResponse.model_validate(data)

    def settlement_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceResponse:
        """``GET /margin/settlement_balance`` — settlement-buffer balance."""
        data = self._get("/margin/settlement_balance", extra_headers=extra_headers)
        return GetSettlementBalanceResponse.model_validate(data)

    def guaranty_fund_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetGuarantyFundBalanceResponse:
        """``GET /margin/guaranty_fund_balance`` — guaranty-fund contribution balance."""
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
        params = _params(id=id)
        data = self._get(
            "/margin/settlement_balance_withdrawal",
            params=params,
            extra_headers=extra_headers,
        )
        return GetSettlementBalanceWithdrawalResponse.model_validate(data)

    def list_subtrader_groups(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginSubtraderGroupsResponse:
        """``GET /fcm/margin/subtrader_groups`` — list margin subtrader groups."""
        data = self._get("/fcm/margin/subtrader_groups", extra_headers=extra_headers)
        return GetMarginSubtraderGroupsResponse.model_validate(data)

    def create_subtrader_group(
        self,
        *,
        request: CreateMarginSubtraderGroupRequest | None = None,
        subtrader_ids: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginSubtraderGroupResponse:
        """``POST /fcm/margin/subtrader_groups`` — create a netted subtrader group."""
        _check_request_exclusive(request, subtrader_ids=subtrader_ids)
        if request is None:
            if subtrader_ids is None:
                raise TypeError(
                    "create_subtrader_group() requires `subtrader_ids` "
                    "(or pass `request=...`)"
                )
            request = CreateMarginSubtraderGroupRequest(subtrader_ids=subtrader_ids)
        data = self._post(
            "/fcm/margin/subtrader_groups",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        return CreateMarginSubtraderGroupResponse.model_validate(data)

    def update_subtrader_group(
        self,
        group_id: str,
        *,
        request: UpdateMarginSubtraderGroupRequest | None = None,
        subtrader_ids: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """``PUT /fcm/margin/subtrader_groups/{group_id}`` — replace group membership."""
        _check_request_exclusive(request, subtrader_ids=subtrader_ids)
        if request is None:
            if subtrader_ids is None:
                raise TypeError(
                    "update_subtrader_group() requires `subtrader_ids` "
                    "(or pass `request=...`)"
                )
            request = UpdateMarginSubtraderGroupRequest(subtrader_ids=subtrader_ids)
        self._put(
            f"/fcm/margin/subtrader_groups/{_seg(group_id, name='group_id')}",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )

    def delete_subtrader_group(
        self, group_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """``DELETE /fcm/margin/subtrader_groups/{group_id}`` — delete a group."""
        self._delete(
            f"/fcm/margin/subtrader_groups/{_seg(group_id, name='group_id')}",
            extra_headers=extra_headers,
        )


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
        _validate_date_range(start_date, end_date)
        params = _params(start_date=start_date, end_date=end_date)
        data = await self._get("/margin/reports", params=params, extra_headers=extra_headers)
        return GetMarginReportsResponse.model_validate(data)

    async def active_obligation(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationResponse:
        """Async :meth:`MarginResource.active_obligation`."""
        data = await self._get("/margin/active_obligation", extra_headers=extra_headers)
        return GetActiveMarginObligationResponse.model_validate(data)

    async def active_obligations(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetActiveMarginObligationsResponse:
        """Async :meth:`MarginResource.active_obligations` (spec v3.24.0)."""
        data = await self._get("/margin/active_obligations", extra_headers=extra_headers)
        return GetActiveMarginObligationsResponse.model_validate(data)

    async def obligation_history(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Page[ObligationEntry]:
        """Async :meth:`MarginResource.obligation_history`."""
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
        data = await self._get("/margin/settlement_estimate", extra_headers=extra_headers)
        return GetSettlementEstimateResponse.model_validate(data)

    async def settlement_estimate_by_asset_class(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementEstimateByAssetClassResponse:
        """Async :meth:`MarginResource.settlement_estimate_by_asset_class` (spec v3.24.0)."""
        data = await self._get(
            "/margin/settlement_estimate_by_asset_class", extra_headers=extra_headers
        )
        return GetSettlementEstimateByAssetClassResponse.model_validate(data)

    async def settlement_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetSettlementBalanceResponse:
        """Async :meth:`MarginResource.settlement_balance`."""
        data = await self._get("/margin/settlement_balance", extra_headers=extra_headers)
        return GetSettlementBalanceResponse.model_validate(data)

    async def guaranty_fund_balance(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetGuarantyFundBalanceResponse:
        """Async :meth:`MarginResource.guaranty_fund_balance`."""
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
        params = _params(id=id)
        data = await self._get(
            "/margin/settlement_balance_withdrawal",
            params=params,
            extra_headers=extra_headers,
        )
        return GetSettlementBalanceWithdrawalResponse.model_validate(data)

    async def list_subtrader_groups(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginSubtraderGroupsResponse:
        """Async :meth:`MarginResource.list_subtrader_groups`."""
        data = await self._get("/fcm/margin/subtrader_groups", extra_headers=extra_headers)
        return GetMarginSubtraderGroupsResponse.model_validate(data)

    async def create_subtrader_group(
        self,
        *,
        request: CreateMarginSubtraderGroupRequest | None = None,
        subtrader_ids: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> CreateMarginSubtraderGroupResponse:
        """Async :meth:`MarginResource.create_subtrader_group`."""
        _check_request_exclusive(request, subtrader_ids=subtrader_ids)
        if request is None:
            if subtrader_ids is None:
                raise TypeError(
                    "create_subtrader_group() requires `subtrader_ids` "
                    "(or pass `request=...`)"
                )
            request = CreateMarginSubtraderGroupRequest(subtrader_ids=subtrader_ids)
        data = await self._post(
            "/fcm/margin/subtrader_groups",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )
        return CreateMarginSubtraderGroupResponse.model_validate(data)

    async def update_subtrader_group(
        self,
        group_id: str,
        *,
        request: UpdateMarginSubtraderGroupRequest | None = None,
        subtrader_ids: list[str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Async :meth:`MarginResource.update_subtrader_group`."""
        _check_request_exclusive(request, subtrader_ids=subtrader_ids)
        if request is None:
            if subtrader_ids is None:
                raise TypeError(
                    "update_subtrader_group() requires `subtrader_ids` "
                    "(or pass `request=...`)"
                )
            request = UpdateMarginSubtraderGroupRequest(subtrader_ids=subtrader_ids)
        await self._put(
            f"/fcm/margin/subtrader_groups/{_seg(group_id, name='group_id')}",
            json=request.model_dump(exclude_none=True, by_alias=True, mode="json"),
            extra_headers=extra_headers,
        )

    async def delete_subtrader_group(
        self, group_id: str, *, extra_headers: dict[str, str] | None = None
    ) -> None:
        """Async :meth:`MarginResource.delete_subtrader_group`."""
        await self._delete(
            f"/fcm/margin/subtrader_groups/{_seg(group_id, name='group_id')}",
            extra_headers=extra_headers,
        )

"""Perps funding resource — rate estimate, historical rates, payment history (#395).

Three read-only GET endpoints. ``rate_estimate`` and ``historical_rates`` are
public (no spec ``security`` block); ``history`` requires RSA-PSS auth and is
guarded client-side with ``_require_auth()`` so an unauthenticated caller gets
``AuthRequiredError`` instead of a server 401. All three retry on 429/502/503/504
(GET).

None of the three funding endpoints paginate — ``GetMarginFundingHistoryResponse``
and ``GetMarginHistoricalFundingRatesResponse`` carry a single array property and
**no cursor** — so there are no ``*_all()`` / ``Iterator`` paginators here. The
two list endpoints unwrap their array key and return ``builtins.list[Model]``,
mirroring ``historical.candlesticks``.
"""

from __future__ import annotations

import builtins
from typing import Any

from kalshi.perps.models.funding import (
    MarginFundingHistoryEntry,
    MarginFundingRate,
    MarginFundingRateEstimate,
)
from kalshi.resources._base import AsyncResource, SyncResource, _params


def _funding_historical_params(
    *,
    ticker: str | None,
    start_ts: int | None,
    end_ts: int | None,
) -> dict[str, Any]:
    """Build query params for ``GET /margin/funding_rates/historical`` (None dropped)."""
    return _params(ticker=ticker, start_ts=start_ts, end_ts=end_ts)


def _funding_history_params(
    *,
    ticker: str | None,
    start_date: str,
    end_date: str,
    subaccount: int | None,
) -> dict[str, Any]:
    """Build query params for ``GET /margin/funding_history`` (None dropped)."""
    return _params(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        subaccount=subaccount,
    )


class FundingResource(SyncResource):
    """Sync perps funding API (``rate_estimate`` / ``historical_rates`` / ``history``)."""

    def rate_estimate(
        self, ticker: str, *, extra_headers: dict[str, str] | None = None
    ) -> MarginFundingRateEstimate:
        data = self._get(
            "/margin/funding_rates/estimate",
            params=_params(ticker=ticker),
            extra_headers=extra_headers,
        )
        return MarginFundingRateEstimate.model_validate(data)

    def historical_rates(
        self,
        *,
        ticker: str | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginFundingRate]:
        params = _funding_historical_params(ticker=ticker, start_ts=start_ts, end_ts=end_ts)
        data = self._get(
            "/margin/funding_rates/historical", params=params, extra_headers=extra_headers
        )
        return [MarginFundingRate.model_validate(r) for r in data.get("funding_rates", [])]

    def history(
        self,
        *,
        start_date: str,
        end_date: str,
        ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginFundingHistoryEntry]:
        self._require_auth()
        params = _funding_history_params(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            subaccount=subaccount,
        )
        data = self._get("/margin/funding_history", params=params, extra_headers=extra_headers)
        return [
            MarginFundingHistoryEntry.model_validate(e) for e in data.get("funding_history", [])
        ]


class AsyncFundingResource(AsyncResource):
    """Async perps funding API (``rate_estimate`` / ``historical_rates`` / ``history``)."""

    async def rate_estimate(
        self, ticker: str, *, extra_headers: dict[str, str] | None = None
    ) -> MarginFundingRateEstimate:
        data = await self._get(
            "/margin/funding_rates/estimate",
            params=_params(ticker=ticker),
            extra_headers=extra_headers,
        )
        return MarginFundingRateEstimate.model_validate(data)

    async def historical_rates(
        self,
        *,
        ticker: str | None = None,
        start_ts: int | None = None,
        end_ts: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginFundingRate]:
        params = _funding_historical_params(ticker=ticker, start_ts=start_ts, end_ts=end_ts)
        data = await self._get(
            "/margin/funding_rates/historical", params=params, extra_headers=extra_headers
        )
        return [MarginFundingRate.model_validate(r) for r in data.get("funding_rates", [])]

    async def history(
        self,
        *,
        start_date: str,
        end_date: str,
        ticker: str | None = None,
        subaccount: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> builtins.list[MarginFundingHistoryEntry]:
        self._require_auth()
        params = _funding_history_params(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            subaccount=subaccount,
        )
        data = await self._get(
            "/margin/funding_history", params=params, extra_headers=extra_headers
        )
        return [
            MarginFundingHistoryEntry.model_validate(e) for e in data.get("funding_history", [])
        ]

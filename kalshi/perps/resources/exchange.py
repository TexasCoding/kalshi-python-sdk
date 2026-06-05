"""Perps exchange resource — status, margin-enabled gate, risk parameters (#389).

Three read-only GET endpoints. ``status`` and ``risk_parameters`` are public
(no spec ``security`` block); ``enabled`` requires RSA-PSS auth and is guarded
client-side with ``_require_auth()`` so an unauthenticated caller gets
``AuthRequiredError`` instead of a server 401. All three retry on 429/502/503/504
(GET).
"""

from __future__ import annotations

from kalshi.perps.models.exchange import (
    ExchangeStatus,
    GetMarginRiskParametersResponse,
    MarginEnabledResponse,
)
from kalshi.resources._base import AsyncResource, SyncResource


class PerpsExchangeResource(SyncResource):
    """Sync perps exchange API."""

    def status(self, *, extra_headers: dict[str, str] | None = None) -> ExchangeStatus:
        data = self._get("/margin/exchange/status", extra_headers=extra_headers)
        return ExchangeStatus.model_validate(data)

    def enabled(self, *, extra_headers: dict[str, str] | None = None) -> MarginEnabledResponse:
        self._require_auth()
        data = self._get("/margin/enabled", extra_headers=extra_headers)
        return MarginEnabledResponse.model_validate(data)

    def risk_parameters(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginRiskParametersResponse:
        data = self._get("/margin/risk_parameters", extra_headers=extra_headers)
        return GetMarginRiskParametersResponse.model_validate(data)


class AsyncPerpsExchangeResource(AsyncResource):
    """Async perps exchange API."""

    async def status(self, *, extra_headers: dict[str, str] | None = None) -> ExchangeStatus:
        data = await self._get("/margin/exchange/status", extra_headers=extra_headers)
        return ExchangeStatus.model_validate(data)

    async def enabled(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> MarginEnabledResponse:
        self._require_auth()
        data = await self._get("/margin/enabled", extra_headers=extra_headers)
        return MarginEnabledResponse.model_validate(data)

    async def risk_parameters(
        self, *, extra_headers: dict[str, str] | None = None
    ) -> GetMarginRiskParametersResponse:
        data = await self._get("/margin/risk_parameters", extra_headers=extra_headers)
        return GetMarginRiskParametersResponse.model_validate(data)

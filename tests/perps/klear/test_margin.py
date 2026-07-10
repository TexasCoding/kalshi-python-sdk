"""Tests for the Klear (SCM) margin endpoints (#400).

Covers the nine SCM margin endpoints (plus the two ``*_all`` paginators) on both
``KlearClient`` and ``AsyncKlearClient``. The clients carry Bearer credentials
(see the conftest fixtures), so the Klear resource base injects the
``Authorization: Bearer`` header on every request — there is no client-side
un-logged-in guard; an invalid token surfaces as a server 401.

Money-typing invariants under test: ``_centicents`` fields stay plain ``int``
(never ``Decimal``), only the withdraw/withdrawal ``amount`` fields are
``DollarDecimal`` dollar-strings, and the withdraw POST body wire shape is
exactly ``{"amount": "500.00"}``. POST is never retried.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest
import respx
from pydantic import ValidationError

from kalshi.errors import (
    KalshiAuthError,
    KalshiError,
    KalshiServerError,
    KalshiValidationError,
)
from kalshi.perps.klear import AsyncKlearClient, KlearClient, KlearConfig
from kalshi.perps.klear.models.margin import (
    GetSettlementBalanceWithdrawalResponse,
    MarginReport,
    ObligationEntry,
    SettlementBalanceHistoryEntry,
    SettlementEstimate,
    WithdrawSettlementBalanceRequest,
)

BASE = "https://demo-api.kalshi.co/klear-api/v1"

ALL_REPORT_TYPES = [
    "trade_audit",
    "position_snapshot",
    "market_price_snapshot",
    "funding_periods",
    "settlement_periods",
]


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #


@pytest.fixture
def auth_klear_client(klear_client: KlearClient) -> KlearClient:
    """A ``KlearClient`` carrying Bearer credentials (from the conftest fixture)."""
    return klear_client


@pytest.fixture
def auth_async_klear_client(async_klear_client: AsyncKlearClient) -> AsyncKlearClient:
    """An ``AsyncKlearClient`` carrying Bearer credentials."""
    return async_klear_client


def _report(report_type: str = "trade_audit") -> dict[str, object]:
    return {
        "report_type": report_type,
        "url": "https://example.com/presigned/report.csv",
        "date": "2026-06-01",
        "created_ts": "2026-06-01T12:00:00Z",
        "is_end_of_day": True,
    }


def _obligation(amount: int = -12345) -> dict[str, object]:
    return {
        "id": "ob1",
        "user_id": "u1",
        "amount_centicents": amount,
        "fees_centicents": 100,
        "maintenance_margin_centicents": 50,
        "pnl_centicents": -200,
        "execution_time": "2026-06-01T00:00:00Z",
        "last_updated_ts": "2026-06-01T01:00:00Z",
        "asset_class": "Crypto",
        "receives": [
            {
                "id": "r1",
                "type": "wire",
                "amount_centicents": 5000,
                "external_reference": "EXT-1",
                "created_ts": "2026-06-01T00:30:00Z",
            }
        ],
        "settlement_details": [
            {
                "id": "sd1",
                "market_ticker": "BTC-PERP",
                "subtrader_id": "st1",
                "pnl_centicents": -200,
                "total_fees_centicents": 100,
                "total_amount_centicents": -300,
            }
        ],
        "maintenance_margin_details": [
            {
                "id": "mm1",
                "subtrader_id": "",
                "maintenance_margin_centicents": 50,
                "maintenance_margin_delta_centicents": 10,
            }
        ],
    }


def _estimate() -> dict[str, int]:
    return {
        "variation_margin_centicents": 1000,
        "total_fees_centicents": 200,
        "maintenance_margin_delta_centicents": 30,
        "maintenance_margin_required_centicents": 400,
        "total_amount_centicents": 1630,
    }


def _balance_history_entry() -> dict[str, object]:
    return {
        "balance_delta_centicents": -500,
        "locked_balance_delta_centicents": 500,
        "reason": "withdrawal_initiated",
        "business_transaction_id": "btx-1",
        "created_ts": "2026-06-01T00:00:00Z",
    }


# --------------------------------------------------------------------------- #
# margin_reports
# --------------------------------------------------------------------------- #


class TestMarginReports:
    @respx.mock
    def test_happy_one_per_report_type(self, auth_klear_client: KlearClient) -> None:
        route = respx.get(f"{BASE}/margin/reports").mock(
            return_value=httpx.Response(
                200, json={"reports": [_report(rt) for rt in ALL_REPORT_TYPES]}
            )
        )
        resp = auth_klear_client.margin.margin_reports(
            start_date="2026-05-01", end_date="2026-06-01"
        )
        assert [r.report_type for r in resp.reports] == ALL_REPORT_TYPES
        first = resp.reports[0]
        assert isinstance(first, MarginReport)
        # date is datetime.date, created_ts is an aware datetime.
        assert first.date.isoformat() == "2026-06-01"
        assert first.created_ts.tzinfo is not None
        params = route.calls.last.request.url.params
        assert params["start_date"] == "2026-05-01"
        assert params["end_date"] == "2026-06-01"
        auth_klear_client.close()

    @respx.mock
    def test_empty_reports_array(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/reports").mock(
            return_value=httpx.Response(200, json={"reports": []})
        )
        resp = auth_klear_client.margin.margin_reports(
            start_date="2026-05-01", end_date="2026-06-01"
        )
        assert resp.reports == []
        auth_klear_client.close()

    @respx.mock
    def test_null_reports_coerced_to_empty(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/reports").mock(
            return_value=httpx.Response(200, json={"reports": None})
        )
        resp = auth_klear_client.margin.margin_reports(
            start_date="2026-05-01", end_date="2026-06-01"
        )
        assert resp.reports == []
        auth_klear_client.close()

    @respx.mock
    def test_rejects_malformed_or_inverted_dates_client_side(
        self, auth_klear_client: KlearClient
    ) -> None:
        # Date-range guard rejects bad/inverted ranges at the SDK boundary,
        # before any HTTP — clearer than an opaque server 400.
        route = respx.get(f"{BASE}/margin/reports").mock(
            return_value=httpx.Response(200, json={"reports": []})
        )
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            auth_klear_client.margin.margin_reports(start_date="nope", end_date="2026-06-01")
        with pytest.raises(ValueError, match="on or after"):
            auth_klear_client.margin.margin_reports(start_date="2026-06-02", end_date="2026-06-01")
        # #409: fromisoformat is lenient — reject non-canonical forms that would
        # otherwise be forwarded raw to a server expecting strict YYYY-MM-DD.
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            auth_klear_client.margin.margin_reports(start_date="20260501", end_date="2026-06-01")
        with pytest.raises(ValueError, match="canonical YYYY-MM-DD"):
            auth_klear_client.margin.margin_reports(start_date="2026-05-01", end_date="2026-W22-1")
        assert not route.called
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/reports").mock(
            return_value=httpx.Response(200, json={"reports": [_report()]})
        )
        resp = await auth_async_klear_client.margin.margin_reports(
            start_date="2026-05-01", end_date="2026-06-01"
        )
        assert resp.reports[0].report_type == "trade_audit"
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# active_obligation
# --------------------------------------------------------------------------- #


class TestActiveObligation:
    @respx.mock
    def test_happy_full_obligation(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligation").mock(
            return_value=httpx.Response(200, json={"obligation": _obligation(amount=-99999)})
        )
        resp = auth_klear_client.margin.active_obligation()
        ob = resp.obligation
        assert isinstance(ob, ObligationEntry)
        # Negative net amount stays a plain int (not Decimal).
        assert ob.amount_centicents == -99999
        assert isinstance(ob.amount_centicents, int) and not isinstance(ob.amount_centicents, bool)
        assert not isinstance(ob.amount_centicents, Decimal)
        assert ob.receives[0].amount_centicents == 5000
        assert ob.settlement_details[0].market_ticker == "BTC-PERP"
        assert ob.maintenance_margin_details[0].subtrader_id == ""
        assert ob.execution_time.tzinfo is not None
        auth_klear_client.close()

    @respx.mock
    def test_obligation_null(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligation").mock(
            return_value=httpx.Response(200, json={"obligation": None})
        )
        resp = auth_klear_client.margin.active_obligation()
        assert resp.obligation is None
        auth_klear_client.close()

    @respx.mock
    def test_401_maps_to_auth_error(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligation").mock(
            return_value=httpx.Response(401, json={"code": "unauthorized", "message": "no"})
        )
        with pytest.raises(KalshiAuthError):
            auth_klear_client.margin.active_obligation()
        auth_klear_client.close()

    @respx.mock
    async def test_async_null(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligation").mock(
            return_value=httpx.Response(200, json={"obligation": None})
        )
        resp = await auth_async_klear_client.margin.active_obligation()
        assert resp.obligation is None
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# active_obligations (plural; spec v3.24.0)
# --------------------------------------------------------------------------- #


class TestActiveObligations:
    @respx.mock
    def test_happy_list(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligations").mock(
            return_value=httpx.Response(
                200,
                json={"obligations": [_obligation(amount=-99999), _obligation(amount=5000)]},
            )
        )
        resp = auth_klear_client.margin.active_obligations()
        assert len(resp.obligations) == 2
        assert all(isinstance(o, ObligationEntry) for o in resp.obligations)
        assert resp.obligations[0].amount_centicents == -99999
        assert resp.obligations[0].asset_class == "Crypto"
        auth_klear_client.close()

    @respx.mock
    def test_null_obligations_coerces_to_empty(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligations").mock(
            return_value=httpx.Response(200, json={"obligations": None})
        )
        resp = auth_klear_client.margin.active_obligations()
        assert resp.obligations == []
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/active_obligations").mock(
            return_value=httpx.Response(200, json={"obligations": [_obligation()]})
        )
        resp = await auth_async_klear_client.margin.active_obligations()
        assert len(resp.obligations) == 1
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# settlement_estimate_by_asset_class (spec v3.24.0)
# --------------------------------------------------------------------------- #


class TestSettlementEstimateByAssetClass:
    @respx.mock
    def test_happy(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate_by_asset_class").mock(
            return_value=httpx.Response(
                200,
                json={
                    "estimates": {
                        "Crypto": {
                            "next_runtime": "2026-06-02T00:00:00Z",
                            "user_breakdown": _estimate(),
                            "subtrader_breakdowns": {"st1": _estimate()},
                            "prev_settlement_prices": {"BTC-PERP": 5000},
                        }
                    },
                    "settlement_balance_centicents": 123456,
                },
            )
        )
        resp = auth_klear_client.margin.settlement_estimate_by_asset_class()
        assert resp.settlement_balance_centicents == 123456
        crypto = resp.estimates["Crypto"]
        assert crypto.next_runtime.tzinfo is not None
        assert crypto.user_breakdown is not None
        assert crypto.user_breakdown.total_amount_centicents == 1630
        assert crypto.subtrader_breakdowns is not None
        assert crypto.subtrader_breakdowns["st1"].variation_margin_centicents == 1000
        assert crypto.prev_settlement_prices == {"BTC-PERP": 5000}
        auth_klear_client.close()

    @respx.mock
    def test_optional_breakdowns_omitted(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate_by_asset_class").mock(
            return_value=httpx.Response(
                200,
                json={
                    "estimates": {"Crypto": {"next_runtime": "2026-06-02T00:00:00Z"}},
                    "settlement_balance_centicents": 0,
                },
            )
        )
        resp = auth_klear_client.margin.settlement_estimate_by_asset_class()
        crypto = resp.estimates["Crypto"]
        assert crypto.user_breakdown is None
        assert crypto.subtrader_breakdowns is None
        assert crypto.prev_settlement_prices is None
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate_by_asset_class").mock(
            return_value=httpx.Response(
                200,
                json={
                    "estimates": {"Crypto": {"next_runtime": "2026-06-02T00:00:00Z"}},
                    "settlement_balance_centicents": 7,
                },
            )
        )
        resp = await auth_async_klear_client.margin.settlement_estimate_by_asset_class()
        assert resp.settlement_balance_centicents == 7
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# obligation_history / obligation_history_all
# --------------------------------------------------------------------------- #


class TestObligationHistory:
    @respx.mock
    def test_happy_page_with_cursor(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/obligation_history").mock(
            return_value=httpx.Response(
                200, json={"obligations": [_obligation()], "cursor": "2026-06-01T00:00:00Z"}
            )
        )
        page = auth_klear_client.margin.obligation_history(limit=10)
        assert len(page.items) == 1
        assert page.cursor == "2026-06-01T00:00:00Z"
        assert page.has_next is True
        auth_klear_client.close()

    @respx.mock
    def test_all_paginates_two_pages(self, auth_klear_client: KlearClient) -> None:
        responses = [
            httpx.Response(
                200, json={"obligations": [_obligation(), _obligation()], "cursor": "CUR2"}
            ),
            httpx.Response(200, json={"obligations": [_obligation()], "cursor": ""}),
        ]
        route = respx.get(f"{BASE}/margin/obligation_history").mock(side_effect=responses)
        items = list(auth_klear_client.margin.obligation_history_all())
        assert len(items) == 3
        # The cursor from page 1 is forwarded as the page-2 query param.
        assert route.calls[1].request.url.params["cursor"] == "CUR2"
        auth_klear_client.close()

    def test_limit_over_max_raises_before_http(self, auth_klear_client: KlearClient) -> None:
        with pytest.raises(ValueError):
            auth_klear_client.margin.obligation_history(limit=101)
        auth_klear_client.close()

    @respx.mock
    def test_cursor_loop_guard(self, auth_klear_client: KlearClient) -> None:
        # Server keeps returning the same cursor -> the paginator loop-guard fires.
        respx.get(f"{BASE}/margin/obligation_history").mock(
            return_value=httpx.Response(
                200, json={"obligations": [_obligation()], "cursor": "STUCK"}
            )
        )
        with pytest.raises(KalshiError):
            list(auth_klear_client.margin.obligation_history_all())
        auth_klear_client.close()

    @respx.mock
    async def test_async_all_paginates(
        self, auth_async_klear_client: AsyncKlearClient
    ) -> None:
        responses = [
            httpx.Response(200, json={"obligations": [_obligation()], "cursor": "C"}),
            httpx.Response(200, json={"obligations": [_obligation()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/obligation_history").mock(side_effect=responses)
        items = [o async for o in auth_async_klear_client.margin.obligation_history_all()]
        assert len(items) == 2
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# settlement_estimate
# --------------------------------------------------------------------------- #


class TestSettlementEstimate:
    @respx.mock
    def test_happy_with_subtrader_breakdowns(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate").mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_breakdown": _estimate(),
                    "subtrader_breakdowns": {"st1": _estimate(), "st2": _estimate()},
                    "settlement_balance_centicents": 50000,
                },
            )
        )
        resp = auth_klear_client.margin.settlement_estimate()
        assert isinstance(resp.user_breakdown, SettlementEstimate)
        assert resp.settlement_balance_centicents == 50000
        assert isinstance(resp.settlement_balance_centicents, int)
        assert set(resp.subtrader_breakdowns or {}) == {"st1", "st2"}
        assert isinstance(resp.subtrader_breakdowns["st1"], SettlementEstimate)  # type: ignore[index]
        auth_klear_client.close()

    @respx.mock
    def test_subtrader_breakdowns_absent(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate").mock(
            return_value=httpx.Response(
                200,
                json={"user_breakdown": _estimate(), "settlement_balance_centicents": 1},
            )
        )
        resp = auth_klear_client.margin.settlement_estimate()
        assert resp.subtrader_breakdowns is None
        auth_klear_client.close()

    @respx.mock
    def test_500_propagates(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate").mock(
            return_value=httpx.Response(500, json={"code": "x", "message": "boom"})
        )
        with pytest.raises(KalshiServerError):
            auth_klear_client.margin.settlement_estimate()
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_estimate").mock(
            return_value=httpx.Response(
                200,
                json={"user_breakdown": _estimate(), "settlement_balance_centicents": 7},
            )
        )
        resp = await auth_async_klear_client.margin.settlement_estimate()
        assert resp.settlement_balance_centicents == 7
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# settlement_balance
# --------------------------------------------------------------------------- #


class TestSettlementBalance:
    @respx.mock
    def test_happy(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_id": "u1",
                    "balance_available_centicents": 1_000_000,
                    "locked_balance_centicents": 250_000,
                },
            )
        )
        resp = auth_klear_client.margin.settlement_balance()
        assert resp.balance_available_centicents == 1_000_000
        assert isinstance(resp.balance_available_centicents, int)
        assert not isinstance(resp.balance_available_centicents, Decimal)
        assert resp.locked_balance_centicents == 250_000
        auth_klear_client.close()

    @respx.mock
    def test_locked_balance_absent(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(
                200, json={"user_id": "u1", "balance_available_centicents": 5}
            )
        )
        resp = auth_klear_client.margin.settlement_balance()
        assert resp.locked_balance_centicents is None
        auth_klear_client.close()

    @respx.mock
    def test_403_maps_to_auth_error(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(403, json={"code": "forbidden", "message": "no"})
        )
        with pytest.raises(KalshiAuthError):
            auth_klear_client.margin.settlement_balance()
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance").mock(
            return_value=httpx.Response(
                200, json={"user_id": "u1", "balance_available_centicents": 9}
            )
        )
        resp = await auth_async_klear_client.margin.settlement_balance()
        assert resp.balance_available_centicents == 9
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# guaranty_fund_balance
# --------------------------------------------------------------------------- #


class TestGuarantyFundBalance:
    @respx.mock
    def test_happy(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/guaranty_fund_balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_id": "u1",
                    "amount_centicents": 123_456,
                    "updated_ts": "2026-06-01T00:00:00Z",
                },
            )
        )
        resp = auth_klear_client.margin.guaranty_fund_balance()
        assert resp.amount_centicents == 123_456
        assert isinstance(resp.amount_centicents, int)
        assert resp.updated_ts.tzinfo is not None
        auth_klear_client.close()

    @respx.mock
    def test_zero_balance(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/guaranty_fund_balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_id": "u1",
                    "amount_centicents": 0,
                    "updated_ts": "2026-06-01T00:00:00Z",
                },
            )
        )
        resp = auth_klear_client.margin.guaranty_fund_balance()
        assert resp.amount_centicents == 0
        auth_klear_client.close()

    @respx.mock
    async def test_async_happy(self, auth_async_klear_client: AsyncKlearClient) -> None:
        respx.get(f"{BASE}/margin/guaranty_fund_balance").mock(
            return_value=httpx.Response(
                200,
                json={
                    "user_id": "u1",
                    "amount_centicents": 1,
                    "updated_ts": "2026-06-01T00:00:00Z",
                },
            )
        )
        resp = await auth_async_klear_client.margin.guaranty_fund_balance()
        assert resp.amount_centicents == 1
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# settlement_balance_history / _all
# --------------------------------------------------------------------------- #


class TestSettlementBalanceHistory:
    @respx.mock
    def test_happy_page(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance_history").mock(
            return_value=httpx.Response(
                200, json={"entries": [_balance_history_entry()], "cursor": "C1"}
            )
        )
        page = auth_klear_client.margin.settlement_balance_history(limit=100)
        assert len(page.items) == 1
        assert isinstance(page.items[0], SettlementBalanceHistoryEntry)
        assert page.items[0].balance_delta_centicents == -500
        assert isinstance(page.items[0].balance_delta_centicents, int)
        assert page.cursor == "C1"
        auth_klear_client.close()

    @respx.mock
    def test_all_paginates(self, auth_klear_client: KlearClient) -> None:
        responses = [
            httpx.Response(
                200, json={"entries": [_balance_history_entry()], "cursor": "NEXT"}
            ),
            httpx.Response(200, json={"entries": [_balance_history_entry()], "cursor": ""}),
        ]
        route = respx.get(f"{BASE}/margin/settlement_balance_history").mock(
            side_effect=responses
        )
        items = list(auth_klear_client.margin.settlement_balance_history_all())
        assert len(items) == 2
        assert route.calls[1].request.url.params["cursor"] == "NEXT"
        auth_klear_client.close()

    def test_limit_over_max_raises_before_http(self, auth_klear_client: KlearClient) -> None:
        with pytest.raises(ValueError):
            auth_klear_client.margin.settlement_balance_history(limit=501)
        auth_klear_client.close()

    @respx.mock
    def test_empty_entries(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance_history").mock(
            return_value=httpx.Response(200, json={"entries": [], "cursor": ""})
        )
        page = auth_klear_client.margin.settlement_balance_history()
        assert page.items == []
        assert page.has_next is False
        auth_klear_client.close()

    @respx.mock
    async def test_async_all_paginates(
        self, auth_async_klear_client: AsyncKlearClient
    ) -> None:
        responses = [
            httpx.Response(200, json={"entries": [_balance_history_entry()], "cursor": "C"}),
            httpx.Response(200, json={"entries": [_balance_history_entry()], "cursor": ""}),
        ]
        respx.get(f"{BASE}/margin/settlement_balance_history").mock(side_effect=responses)
        items = [
            e async for e in auth_async_klear_client.margin.settlement_balance_history_all()
        ]
        assert len(items) == 2
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# withdraw_settlement_balance
# --------------------------------------------------------------------------- #


class TestWithdrawSettlementBalance:
    @respx.mock
    def test_happy_wire_shape(self, auth_klear_client: KlearClient) -> None:
        route = respx.post(f"{BASE}/margin/withdraw_settlement_balance").mock(
            return_value=httpx.Response(200, json={"id": "wd-1"})
        )
        resp = auth_klear_client.margin.withdraw_settlement_balance(amount="500.00")
        assert resp.id == "wd-1"
        # Body is exactly {"amount": "500.00"} — DollarDecimal dollar-string,
        # by_alias, NOT centicents.
        body = json.loads(route.calls.last.request.content)
        assert body == {"amount": "500.00"}
        auth_klear_client.close()

    def test_forbid_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            WithdrawSettlementBalanceRequest(amount="5", bogus=1)  # type: ignore[call-arg]

    @respx.mock
    def test_rejects_non_positive_amount_client_side(self, auth_klear_client: KlearClient) -> None:
        # Security: a non-positive withdrawal must be rejected at construction,
        # BEFORE any HTTP reaches the real-money endpoint (mirrors OrderPrice).
        route = respx.post(f"{BASE}/margin/withdraw_settlement_balance").mock(
            return_value=httpx.Response(200, json={"id": "should-not-happen"})
        )
        for bad in ("0.00", "-500.00"):
            with pytest.raises(ValidationError):
                auth_klear_client.margin.withdraw_settlement_balance(amount=bad)
        assert not route.called  # no request was ever issued
        auth_klear_client.close()

    @respx.mock
    def test_server_400_on_valid_amount_maps(self, auth_klear_client: KlearClient) -> None:
        # A positive amount the server rejects (e.g. insufficient funds) maps cleanly.
        respx.post(f"{BASE}/margin/withdraw_settlement_balance").mock(
            return_value=httpx.Response(400, json={"code": "bad", "message": "insufficient funds"})
        )
        with pytest.raises(KalshiValidationError):
            auth_klear_client.margin.withdraw_settlement_balance(amount="500.00")
        auth_klear_client.close()

    @respx.mock
    def test_post_not_retried(self) -> None:
        route = respx.post(f"{BASE}/margin/withdraw_settlement_balance").mock(
            return_value=httpx.Response(503, json={"code": "x", "message": "down"})
        )
        client = KlearClient(
            admin_user_id="test-admin",
            access_token="test-token",
            config=KlearConfig.demo(max_retries=3),
        )
        with pytest.raises(KalshiServerError):
            client.margin.withdraw_settlement_balance(amount="100.00")
        # POST is never retried even on a retryable 503.
        assert route.call_count == 1
        client.close()

    @respx.mock
    async def test_async_happy_wire_shape(
        self, auth_async_klear_client: AsyncKlearClient
    ) -> None:
        route = respx.post(f"{BASE}/margin/withdraw_settlement_balance").mock(
            return_value=httpx.Response(200, json={"id": "wd-2"})
        )
        resp = await auth_async_klear_client.margin.withdraw_settlement_balance(amount="12.34")
        assert resp.id == "wd-2"
        body = json.loads(route.calls.last.request.content)
        assert body == {"amount": "12.34"}
        await auth_async_klear_client.close()


# --------------------------------------------------------------------------- #
# settlement_balance_withdrawal
# --------------------------------------------------------------------------- #


class TestSettlementBalanceWithdrawal:
    @pytest.mark.parametrize("status", ["pending", "processing", "processed", "failed"])
    @respx.mock
    def test_happy_per_status(self, auth_klear_client: KlearClient, status: str) -> None:
        route = respx.get(f"{BASE}/margin/settlement_balance_withdrawal").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "wd-1",
                    "amount": "500.00",
                    "status": status,
                    "created_ts": "2026-06-01T00:00:00Z",
                },
            )
        )
        resp = auth_klear_client.margin.settlement_balance_withdrawal(id="wd-1")
        assert isinstance(resp, GetSettlementBalanceWithdrawalResponse)
        # amount is a DollarDecimal (dollar string -> Decimal), NOT centicents.
        assert resp.amount == Decimal("500.00")
        assert isinstance(resp.amount, Decimal)
        assert resp.status == status
        assert route.calls.last.request.url.params["id"] == "wd-1"
        auth_klear_client.close()

    @respx.mock
    def test_400_missing_id(self, auth_klear_client: KlearClient) -> None:
        respx.get(f"{BASE}/margin/settlement_balance_withdrawal").mock(
            return_value=httpx.Response(400, json={"code": "bad", "message": "missing id"})
        )
        with pytest.raises(KalshiValidationError):
            auth_klear_client.margin.settlement_balance_withdrawal(id="missing")
        auth_klear_client.close()

    @respx.mock
    async def test_async_failed_status(
        self, auth_async_klear_client: AsyncKlearClient
    ) -> None:
        respx.get(f"{BASE}/margin/settlement_balance_withdrawal").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "wd-9",
                    "amount": "10.00",
                    "status": "failed",
                    "created_ts": "2026-06-01T00:00:00Z",
                },
            )
        )
        resp = await auth_async_klear_client.margin.settlement_balance_withdrawal(id="wd-9")
        assert resp.status == "failed"
        await auth_async_klear_client.close()

"""Tests for `_join_tickers` validation and null-envelope paginator coercion."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiError
from kalshi.resources._base import (
    AsyncResource,
    SyncResource,
    _join_tickers,
    _validate_max_pages,
)


class _Item(BaseModel):
    id: str


class TestJoinTickersValidation:
    def test_empty_element_in_list_raises(self) -> None:
        with pytest.raises(ValueError, match=r"tickers\[1\] is empty"):
            _join_tickers(["A", "", "B"])

    def test_empty_element_in_tuple_raises(self) -> None:
        with pytest.raises(ValueError, match=r"tickers\[0\] is empty"):
            _join_tickers(("", "B"))

    def test_embedded_comma_in_list_raises(self) -> None:
        with pytest.raises(ValueError, match=r"contains a comma"):
            _join_tickers(["FOO", "BAR,EVIL"])

    def test_embedded_comma_in_tuple_raises(self) -> None:
        with pytest.raises(ValueError, match=r"contains a comma"):
            _join_tickers(("A,B", "C"))

    def test_prejoined_string_passthrough_preserved(self) -> None:
        assert _join_tickers("A,,B") == "A,,B"
        assert _join_tickers("A,B,C") == "A,B,C"

    def test_happy_path_still_works(self) -> None:
        assert _join_tickers(["A", "B", "C"]) == "A,B,C"
        assert _join_tickers(("A", "B")) == "A,B"
        assert _join_tickers("A,B,C") == "A,B,C"
        assert _join_tickers(None) is None
        assert _join_tickers([]) is None
        assert _join_tickers(()) is None
        assert _join_tickers("") is None

    def test_non_string_bool_element_raises_unhelpful_type_error(self) -> None:
        # Pins crash path: bool fails `"," in elem` check; update if validation is added.
        with pytest.raises(TypeError, match=r"argument of type 'bool' is not iterable"):
            _join_tickers([True, "A"])  # type: ignore[list-item]

    def test_non_string_int_element_raises_unhelpful_type_error(self) -> None:
        """Mirror of the bool case: int element crashes the same way."""
        with pytest.raises(TypeError, match=r"argument of type 'int' is not iterable"):
            _join_tickers((1, "A"))  # type: ignore[arg-type]

    def test_max_items_rejects_oversize_list(self) -> None:
        with pytest.raises(ValueError, match=r"too many tickers: 11 > spec max 10"):
            _join_tickers([f"T{i}" for i in range(11)], max_items=10)

    def test_max_items_allows_exact_boundary(self) -> None:
        joined = _join_tickers([f"T{i}" for i in range(10)], max_items=10)
        assert joined is not None and joined.count(",") == 9

    def test_max_items_skipped_for_prejoined_string(self) -> None:
        # Pre-joined strings are caller-owned wire format — cap does not apply.
        joined = _join_tickers(",".join(f"T{i}" for i in range(20)), max_items=10)
        assert joined is not None and joined.count(",") == 19

    def test_max_items_default_unbounded(self) -> None:
        joined = _join_tickers([f"T{i}" for i in range(50)])
        assert joined is not None and joined.count(",") == 49


class TestSyncListNullItemsCoercion:
    @respx.mock
    def test_null_items_key_returns_empty_page(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))
        page = resource._list("/things", _Item, "items")

        assert page.items == []
        assert page.has_next is False

    @respx.mock
    def test_null_items_key_stops_list_all(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))
        collected = list(resource._list_all("/things", _Item, "items"))

        assert collected == []

    @respx.mock
    def test_missing_items_key_still_returns_empty(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))
        page = resource._list("/things", _Item, "items")

        assert page.items == []


class TestAsyncListNullItemsCoercion:
    @respx.mock
    @pytest.mark.asyncio
    async def test_null_items_key_returns_empty_page(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))
        page = await resource._list("/things", _Item, "items")

        assert page.items == []
        assert page.has_next is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_null_items_key_stops_list_all(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))
        collected: list[_Item] = []
        async for item in resource._list_all("/things", _Item, "items"):
            collected.append(item)

        assert collected == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_items_key_still_returns_empty(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))
        page = await resource._list("/things", _Item, "items")

        assert page.items == []


class TestSyncListAllCursorLoopDetection:
    @respx.mock
    def test_repeated_cursor_raises(self, test_auth: KalshiAuth, test_config: KalshiConfig) -> None:
        """Server that returns the same cursor twice must bail fast on the 2nd request."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "x"}], "cursor": "loop"})
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))

        with pytest.raises(KalshiError, match=r"[Cc]ursor loop.*'loop'"):
            list(resource._list_all("/things", _Item, "items"))

        # First call (no cursor) fetches cursor="loop". Second call (cursor=loop) returns
        # cursor="loop" again → loop detected before a third request.
        assert route.call_count == 2

    @respx.mock
    def test_list_all_cursor_loop_detection_uses_last_cursor_only_o1(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """P4.1: cursor guard is O(1) — only the previous page's cursor is
        compared. A non-adjacent revisit (A → B → A) must NOT trip the guard;
        the realistic server-pagination-bug shape is the *immediate* replay
        captured by ``test_repeated_cursor_raises``. The old set-based
        guard would have raised here and consumed unbounded memory on a
        well-behaved server that legitimately reused cursor tokens across
        non-adjacent pages."""
        responses = [
            httpx.Response(200, json={"items": [{"id": "1"}], "cursor": "A"}),
            httpx.Response(200, json={"items": [{"id": "2"}], "cursor": "B"}),
            httpx.Response(200, json={"items": [{"id": "3"}], "cursor": "A"}),
            httpx.Response(200, json={"items": [{"id": "4"}], "cursor": ""}),
        ]
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(side_effect=responses)
        resource = SyncResource(SyncTransport(test_auth, test_config))

        collected = list(resource._list_all("/things", _Item, "items"))
        assert [item.id for item in collected] == ["1", "2", "3", "4"]

    @respx.mock
    def test_list_all_cursor_loop_detection_catches_adjacent_replay(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """P4.1: adjacent replay (A → A) still trips. Mirrors
        ``test_repeated_cursor_raises`` with an explicit name pinned to
        the O(1) regression boundary."""
        responses = [
            httpx.Response(200, json={"items": [{"id": "1"}], "cursor": "A"}),
            httpx.Response(200, json={"items": [{"id": "2"}], "cursor": "A"}),
        ]
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(side_effect=responses)
        resource = SyncResource(SyncTransport(test_auth, test_config))

        with pytest.raises(KalshiError, match=r"[Cc]ursor loop.*'A'"):
            list(resource._list_all("/things", _Item, "items"))

    @respx.mock
    def test_normal_pagination_does_not_trip(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """Regression guard: healthy two-page pagination must not raise."""
        responses = [
            httpx.Response(200, json={"items": [{"id": "1"}], "cursor": "A"}),
            httpx.Response(200, json={"items": [{"id": "2"}], "cursor": ""}),
        ]
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(side_effect=responses)
        resource = SyncResource(SyncTransport(test_auth, test_config))

        collected = list(resource._list_all("/things", _Item, "items"))
        assert [item.id for item in collected] == ["1", "2"]


class TestAsyncListAllCursorLoopDetection:
    @respx.mock
    @pytest.mark.asyncio
    async def test_repeated_cursor_raises(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "x"}], "cursor": "loop"})
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))

        with pytest.raises(KalshiError, match=r"[Cc]ursor loop.*'loop'"):
            async for _ in resource._list_all("/things", _Item, "items"):
                pass

        assert route.call_count == 2


def _fresh_cursor_side_effect() -> Any:
    """Return a respx side_effect that yields a fresh unique cursor per call.

    Each response has one item and a never-repeated cursor so cursor-loop
    detection never trips; only ``max_pages`` can stop the iterator.
    """
    counter = {"n": 0}

    def _make_response(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        n = counter["n"]
        return httpx.Response(
            200,
            json={"items": [{"id": f"item-{n}"}], "cursor": f"cur-{n}"},
        )

    return _make_response


class TestSyncListAllMaxPagesCap:
    """Cover the bare numeric ``max_pages`` cap in ``_list_all`` (#98)."""

    @respx.mock
    def test_cap_of_one_fetches_single_page(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=_fresh_cursor_side_effect()
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))

        collected = list(resource._list_all("/things", _Item, "items", max_pages=1))

        assert route.call_count == 1
        assert [item.id for item in collected] == ["item-1"]

    @respx.mock
    def test_cap_of_three_stops_at_three(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=_fresh_cursor_side_effect()
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))

        collected = list(resource._list_all("/things", _Item, "items", max_pages=3))

        assert route.call_count == 3
        assert [item.id for item in collected] == ["item-1", "item-2", "item-3"]

    @respx.mock
    def test_empty_cursor_stops_after_one_request(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """Regression guard (F-Q-17): empty-string cursor terminates _list_all."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "a"}], "cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))

        collected = list(resource._list_all("/things", _Item, "items"))

        assert route.call_count == 1
        assert [item.id for item in collected] == ["a"]


class TestAsyncListAllMaxPagesCap:
    """Async sibling of TestSyncListAllMaxPagesCap (#98)."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_cap_of_one_fetches_single_page(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=_fresh_cursor_side_effect()
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))

        collected: list[_Item] = []
        async for item in resource._list_all("/things", _Item, "items", max_pages=1):
            collected.append(item)

        assert route.call_count == 1
        assert [item.id for item in collected] == ["item-1"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_cap_of_three_stops_at_three(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=_fresh_cursor_side_effect()
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))

        collected: list[_Item] = []
        async for item in resource._list_all("/things", _Item, "items", max_pages=3):
            collected.append(item)

        assert route.call_count == 3
        assert [item.id for item in collected] == ["item-1", "item-2", "item-3"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_cursor_stops_after_one_request(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """Async regression guard (F-Q-17): empty-string cursor terminates."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": [{"id": "a"}], "cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))

        collected: list[_Item] = []
        async for item in resource._list_all("/things", _Item, "items"):
            collected.append(item)

        assert route.call_count == 1
        assert [item.id for item in collected] == ["a"]


class TestValidateMaxPages:
    """``_validate_max_pages`` rejects non-positive values at the public boundary."""

    def test_none_allowed(self) -> None:
        _validate_max_pages(None)  # no raise

    def test_positive_allowed(self) -> None:
        _validate_max_pages(1)
        _validate_max_pages(1000)

    def test_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            _validate_max_pages(0)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            _validate_max_pages(-3)


class TestMaxPagesEagerValidation:
    """Regression: ``_validate_max_pages`` must fire at call time, not on first iteration.

    Methods that were previously written with ``yield from``/``async for ... yield``
    silently became generators — their body didn't execute until the caller advanced
    the iterator, so `max_pages=0` got deferred. All `*_all()` methods must now use
    `return self._list_all(...)` so the validator runs eagerly.
    """

    def test_sync_milestones_list_all_validates_eagerly(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        from kalshi.resources.milestones import MilestonesResource

        resource = MilestonesResource(SyncTransport(test_auth, test_config))
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            resource.list_all(limit=10, max_pages=0)

    def test_sync_subaccounts_list_all_transfers_validates_eagerly(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        from kalshi.resources.subaccounts import SubaccountsResource

        resource = SubaccountsResource(SyncTransport(test_auth, test_config))
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            resource.list_all_transfers(max_pages=0)

    @pytest.mark.asyncio
    async def test_async_subaccounts_list_all_transfers_validates_eagerly(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        from kalshi.resources.subaccounts import AsyncSubaccountsResource

        resource = AsyncSubaccountsResource(AsyncTransport(test_auth, test_config))
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            resource.list_all_transfers(max_pages=0)

    @pytest.mark.asyncio
    async def test_async_communications_list_all_rfqs_validates_eagerly(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        from kalshi.resources.communications import AsyncCommunicationsResource

        resource = AsyncCommunicationsResource(AsyncTransport(test_auth, test_config))
        with pytest.raises(ValueError, match=r"max_pages must be positive"):
            resource.list_all_rfqs(max_pages=0)


class TestMaxPagesNoneIsUnbounded:
    """``max_pages=None`` must iterate until the server returns no cursor.

    The 1000-page default was removed: cursor-repeat guard is the real safety net.
    """

    @respx.mock
    def test_sync_iterates_past_1000_pages(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        # 1010 just exceeds the old 1000 cap — proves the cap is gone without
        # making the test 100x slower than a normal pagination test.
        total = 1010
        call_counter = {"n": 0}

        def responder(request: httpx.Request) -> httpx.Response:
            call_counter["n"] += 1
            n = call_counter["n"]
            cursor = str(n) if n < total else ""
            return httpx.Response(
                200,
                json={"items": [{"id": f"i{n}"}], "cursor": cursor},
            )

        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(side_effect=responder)
        resource = SyncResource(SyncTransport(test_auth, test_config))
        items = list(resource._list_all("/things", _Item, "items"))
        assert len(items) == total, f"Expected {total} items, got {len(items)} (cap leaked?)"

    @respx.mock
    @pytest.mark.asyncio
    async def test_async_iterates_past_1000_pages(
        self,
        test_auth: KalshiAuth,
        test_config: KalshiConfig,
    ) -> None:
        # Async counterpart — same 1010-page proof, prevents the regression
        # from silently re-appearing in only one of the two code paths.
        total = 1010
        call_counter = {"n": 0}

        def responder(request: httpx.Request) -> httpx.Response:
            call_counter["n"] += 1
            n = call_counter["n"]
            cursor = str(n) if n < total else ""
            return httpx.Response(
                200,
                json={"items": [{"id": f"i{n}"}], "cursor": cursor},
            )

        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(side_effect=responder)
        resource = AsyncResource(AsyncTransport(test_auth, test_config))
        items = [item async for item in resource._list_all("/things", _Item, "items")]
        assert len(items) == total, f"Expected {total} items, got {len(items)} (cap leaked?)"

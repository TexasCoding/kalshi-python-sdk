"""Tests for `_join_tickers` validation and null-envelope paginator coercion."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiError
from kalshi.resources._base import AsyncResource, SyncResource, _join_tickers


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
    def test_repeated_cursor_raises(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """Server that returns the same cursor twice must bail fast, not retry 1000x."""
        route = respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": "x"}], "cursor": "loop"}
            )
        )
        resource = SyncResource(SyncTransport(test_auth, test_config))

        with pytest.raises(KalshiError, match=r"[Cc]ursor loop.*'loop'"):
            list(resource._list_all("/things", _Item, "items"))

        # First call (no cursor) fetches cursor="loop". Second call (cursor=loop) returns
        # cursor="loop" again → loop detected before a third request. Total: 2 requests,
        # not 1000.
        assert route.call_count == 2

    @respx.mock
    def test_multi_page_loop_raises(
        self, test_auth: KalshiAuth, test_config: KalshiConfig
    ) -> None:
        """A → B → A revisit also trips detection."""
        responses = [
            httpx.Response(200, json={"items": [{"id": "1"}], "cursor": "A"}),
            httpx.Response(200, json={"items": [{"id": "2"}], "cursor": "B"}),
            httpx.Response(200, json={"items": [{"id": "3"}], "cursor": "A"}),
        ]
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=responses
        )
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
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            side_effect=responses
        )
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
            return_value=httpx.Response(
                200, json={"items": [{"id": "x"}], "cursor": "loop"}
            )
        )
        resource = AsyncResource(AsyncTransport(test_auth, test_config))

        with pytest.raises(KalshiError, match=r"[Cc]ursor loop.*'loop'"):
            async for _ in resource._list_all("/things", _Item, "items"):
                pass

        assert route.call_count == 2

"""Tests for `_join_tickers` validation and null-envelope paginator coercion."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
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

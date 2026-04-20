"""Tests for pure helpers and base paginator behavior in `resources/_base.py`.

Covers:
  * ``_join_tickers`` — empty-element and embedded-comma validation.
  * ``_list`` / ``_list_all`` — coerce a null envelope list field to ``[]``.

Both classes of bug are silent-data-corruption risks: the first sends
malformed ticker filters to the server; the second crashes with an
unhelpful ``TypeError: 'NoneType' object is not iterable`` when the
server sends an explicit ``null`` list on the envelope.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import BaseModel

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.resources._base import AsyncResource, SyncResource, _join_tickers


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


class _Item(BaseModel):
    """Minimal item type used to exercise the paginator."""

    id: str


# ---------------------------------------------------------------------------
# _join_tickers input validation
# ---------------------------------------------------------------------------


class TestJoinTickersValidation:
    """``_join_tickers`` must reject malformed list/tuple inputs.

    Silent data-corruption class: ``["A", "", "B"]`` used to produce
    ``"A,,B"`` and ``["FOO", "BAR,EVIL"]`` used to produce
    ``"FOO,BAR,EVIL"``. Both expand the ticker list in ways the caller
    didn't intend.
    """

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
        """Pre-joined strings bypass validation by design. The caller owns
        the format when they hand us one.
        """
        assert _join_tickers("A,,B") == "A,,B"
        assert _join_tickers("A,B,C") == "A,B,C"

    def test_happy_path_still_works(self) -> None:
        """Regression guard: valid inputs still produce the comma-joined
        result and ``None`` drops.
        """
        assert _join_tickers(["A", "B", "C"]) == "A,B,C"
        assert _join_tickers(("A", "B")) == "A,B"
        assert _join_tickers("A,B,C") == "A,B,C"
        assert _join_tickers(None) is None
        assert _join_tickers([]) is None
        assert _join_tickers(()) is None
        assert _join_tickers("") is None


# ---------------------------------------------------------------------------
# Null envelope list coercion (sync + async _list / _list_all)
# ---------------------------------------------------------------------------


class TestSyncListNullItemsCoercion:
    """Sync ``_list`` must coerce an explicit null envelope list to ``[]``."""

    @respx.mock
    def test_null_items_key_returns_empty_page(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        """Server returns ``{"items": null}``; paginator yields an empty
        Page rather than crashing with ``TypeError``.
        """
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, config))
        page = resource._list("/things", _Item, "items")

        assert page.items == []
        assert page.has_next is False

    @respx.mock
    def test_null_items_key_stops_list_all(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        """``_list_all`` must not crash when the server returns a null
        list — it should terminate cleanly with zero items yielded.
        """
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, config))
        collected = list(resource._list_all("/things", _Item, "items"))

        assert collected == []

    @respx.mock
    def test_missing_items_key_still_returns_empty(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        """Regression guard: missing key path keeps working (the original
        ``data.get(items_key, [])`` default).
        """
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"cursor": ""})
        )
        resource = SyncResource(SyncTransport(test_auth, config))
        page = resource._list("/things", _Item, "items")

        assert page.items == []


class TestAsyncListNullItemsCoercion:
    """Async ``_list`` must coerce an explicit null envelope list to ``[]``."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_null_items_key_returns_empty_page(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, config))
        page = await resource._list("/things", _Item, "items")

        assert page.items == []
        assert page.has_next is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_null_items_key_stops_list_all(
        self, test_auth: KalshiAuth, config: KalshiConfig
    ) -> None:
        respx.get("https://test.kalshi.com/trade-api/v2/things").mock(
            return_value=httpx.Response(200, json={"items": None, "cursor": ""})
        )
        resource = AsyncResource(AsyncTransport(test_auth, config))
        collected: list[_Item] = []
        async for item in resource._list_all("/things", _Item, "items"):
            collected.append(item)

        assert collected == []

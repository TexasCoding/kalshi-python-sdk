"""Tests for kalshi.models.common.Page and pagination iterators."""

from __future__ import annotations

from kalshi.models.common import Page
from kalshi.models.markets import Market


def _market(ticker: str) -> Market:
    return Market(ticker=ticker)


class TestPage:
    def test_iterate_items(self) -> None:
        page: Page[Market] = Page(items=[_market("A"), _market("B")])
        tickers = [m.ticker for m in page]
        assert tickers == ["A", "B"]

    def test_len(self) -> None:
        page: Page[Market] = Page(items=[_market("A"), _market("B"), _market("C")])
        assert len(page) == 3

    def test_cursor_access(self) -> None:
        page: Page[Market] = Page(items=[_market("A")], cursor="abc123")
        assert page.cursor == "abc123"

    def test_has_next_true(self) -> None:
        page: Page[Market] = Page(items=[_market("A")], cursor="next-page")
        assert page.has_next is True

    def test_has_next_false_none(self) -> None:
        page: Page[Market] = Page(items=[_market("A")], cursor=None)
        assert page.has_next is False

    def test_has_next_false_empty(self) -> None:
        page: Page[Market] = Page(items=[_market("A")], cursor="")
        assert page.has_next is False

    def test_empty_page(self) -> None:
        page: Page[Market] = Page(items=[], cursor=None)
        assert len(page) == 0
        assert page.has_next is False
        assert list(page) == []

    def test_items_attribute(self) -> None:
        items = [_market("X"), _market("Y")]
        page: Page[Market] = Page(items=items)
        assert page.items == items

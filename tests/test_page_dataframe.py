"""Tests for Page.to_dataframe() and Page.to_polars() DataFrame integration."""

from __future__ import annotations

import builtins
import sys
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel

from kalshi.models.common import Page


class _Row(BaseModel):
    """Tiny stub model for DataFrame conversion tests."""

    ticker: str
    price: Decimal
    volume: int


def _sample_items() -> list[_Row]:
    return [
        _Row(ticker="MKT-A", price=Decimal("0.55"), volume=100),
        _Row(ticker="MKT-B", price=Decimal("0.42"), volume=250),
        _Row(ticker="MKT-C", price=Decimal("0.91"), volume=10),
    ]


class TestToDataframe:
    def test_happy_path(self) -> None:
        pd = pytest.importorskip("pandas")
        page: Page[_Row] = Page(items=_sample_items(), cursor=None)

        df = page.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert df.shape == (3, 3)
        assert list(df.columns) == ["ticker", "price", "volume"]
        assert df["ticker"].tolist() == ["MKT-A", "MKT-B", "MKT-C"]
        assert df["volume"].tolist() == [100, 250, 10]

    def test_empty_page(self) -> None:
        pd = pytest.importorskip("pandas")
        page: Page[_Row] = Page(items=[], cursor=None)

        df = page.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert df.shape == (0, 0)

    def test_missing_pandas_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ensure no cached pandas module satisfies the import.
        monkeypatch.delitem(sys.modules, "pandas", raising=False)
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "pandas" or name.startswith("pandas."):
                raise ImportError("No module named 'pandas'")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        page: Page[_Row] = Page(items=_sample_items(), cursor=None)
        with pytest.raises(ImportError, match="pandas"):
            page.to_dataframe()


class TestToPolars:
    def test_happy_path(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_Row] = Page(items=_sample_items(), cursor=None)

        df = page.to_polars()

        assert isinstance(df, pl.DataFrame)
        assert df.shape == (3, 3)
        assert df.columns == ["ticker", "price", "volume"]
        assert df["ticker"].to_list() == ["MKT-A", "MKT-B", "MKT-C"]
        assert df["volume"].to_list() == [100, 250, 10]

    def test_empty_page(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_Row] = Page(items=[], cursor=None)

        df = page.to_polars()

        assert isinstance(df, pl.DataFrame)
        assert df.shape == (0, 0)

    def test_missing_polars_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(sys.modules, "polars", raising=False)
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> Any:
            if name == "polars" or name.startswith("polars."):
                raise ImportError("No module named 'polars'")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        page: Page[_Row] = Page(items=_sample_items(), cursor=None)
        with pytest.raises(ImportError, match="polars"):
            page.to_polars()

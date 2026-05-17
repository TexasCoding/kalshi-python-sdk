"""Tests for Page.to_dataframe() and Page.to_polars() DataFrame integration."""

from __future__ import annotations

import builtins
import sys
from collections.abc import Sequence
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
        # Pin the model_dump(mode="python") promise: Decimal stays Decimal,
        # not coerced to str (which mode="json" would have produced).
        assert df["price"].tolist() == [Decimal("0.55"), Decimal("0.42"), Decimal("0.91")]

    def test_empty_page(self) -> None:
        pd = pytest.importorskip("pandas")
        page: Page[_Row] = Page(items=[], cursor=None)

        df = page.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert df.empty

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
            fromlist: Sequence[str] = (),
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
        # polars maps Python Decimal → polars.Decimal; values round-trip
        # back to Decimal via to_list().
        assert df["price"].to_list() == [Decimal("0.55"), Decimal("0.42"), Decimal("0.91")]

    def test_empty_page(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_Row] = Page(items=[], cursor=None)

        df = page.to_polars()

        assert isinstance(df, pl.DataFrame)
        assert df.is_empty()

    def test_missing_polars_raises_importerror(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(sys.modules, "polars", raising=False)
        real_import = builtins.__import__

        def fake_import(
            name: str,
            globals: dict[str, Any] | None = None,
            locals: dict[str, Any] | None = None,
            fromlist: Sequence[str] = (),
            level: int = 0,
        ) -> Any:
            if name == "polars" or name.startswith("polars."):
                raise ImportError("No module named 'polars'")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        page: Page[_Row] = Page(items=_sample_items(), cursor=None)
        with pytest.raises(ImportError, match="polars"):
            page.to_polars()


# ---------------------------------------------------------------------------
# Issue #101: pin nested-model serialization shape for both backends.
#
# Page.to_dataframe / to_polars use model_dump(mode="python"). Real SDK pages
# carry models with nested Pydantic sub-models (Market has OrderbookLevel,
# multivariate results have list-of-dict). This pins the current shape so a
# future flip to mode="json" or a pandas/polars upgrade reds CI instead of
# silently breaking downstream .sum() / nested column access.
# ---------------------------------------------------------------------------


class _Inner(BaseModel):
    """Nested sub-model — analog of OrderbookLevel inside Market."""

    label: str
    score: Decimal


class _NestedRow(BaseModel):
    """Row with a nested model and a list[Decimal], mirroring real SDK pages."""

    ticker: str
    price: Decimal
    inner: _Inner
    prices: list[Decimal]


def _sample_nested_items() -> list[_NestedRow]:
    return [
        _NestedRow(
            ticker="MKT-A",
            price=Decimal("0.55"),
            inner=_Inner(label="x", score=Decimal("0.10")),
            prices=[Decimal("0.10"), Decimal("0.20")],
        ),
        _NestedRow(
            ticker="MKT-B",
            price=Decimal("0.42"),
            inner=_Inner(label="y", score=Decimal("0.20")),
            prices=[Decimal("0.30")],
        ),
    ]


class TestToDataframeNested:
    def test_nested_model_lands_as_dict_object_column(self) -> None:
        pd = pytest.importorskip("pandas")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert df.shape == (2, 4)
        assert list(df.columns) == ["ticker", "price", "inner", "prices"]
        # Nested column is object-dtype (not expanded into inner.* columns,
        # not stringified). Each cell is the raw dict from model_dump.
        assert df["inner"].dtype == object
        cell = df["inner"].iloc[0]
        assert isinstance(cell, dict)
        assert cell == {"label": "x", "score": Decimal("0.10")}
        # Nested Decimal survives — pins mode="python" (mode="json" would
        # have stringified this and broken Decimal arithmetic downstream).
        assert isinstance(cell["score"], Decimal)

    def test_list_decimal_column_holds_list_of_decimals(self) -> None:
        pytest.importorskip("pandas")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_dataframe()

        assert df["prices"].dtype == object
        first = df["prices"].iloc[0]
        assert isinstance(first, list)
        assert first == [Decimal("0.10"), Decimal("0.20")]
        assert all(isinstance(v, Decimal) for v in first)

    def test_top_level_decimal_preserved_alongside_nested(self) -> None:
        pytest.importorskip("pandas")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_dataframe()

        # Top-level Decimal column is object-dtype with real Decimal values,
        # even when nested columns share the frame.
        assert df["price"].tolist() == [Decimal("0.55"), Decimal("0.42")]
        assert all(isinstance(v, Decimal) for v in df["price"].tolist())


class TestToPolarsNested:
    def test_nested_model_lands_as_struct_column(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_polars()

        assert isinstance(df, pl.DataFrame)
        assert df.shape == (2, 4)
        assert df.columns == ["ticker", "price", "inner", "prices"]
        # polars infers Struct from the nested dict — pin that, since a
        # mode="json" flip would yield a String/Utf8 column instead.
        assert isinstance(df["inner"].dtype, pl.Struct)
        # Struct row round-trips back to a dict with original keys & types.
        first = df["inner"][0]
        assert first == {"label": "x", "score": Decimal("0.10")}
        assert isinstance(first["score"], Decimal)

    def test_list_decimal_column_is_list_of_decimal_dtype(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_polars()

        # List(Decimal) — not List(String), not Object.
        dtype = df["prices"].dtype
        assert isinstance(dtype, pl.List)
        assert isinstance(dtype.inner, pl.Decimal)
        assert df["prices"][0].to_list() == [Decimal("0.10"), Decimal("0.20")]

    def test_top_level_decimal_preserved_alongside_nested(self) -> None:
        pl = pytest.importorskip("polars")
        page: Page[_NestedRow] = Page(items=_sample_nested_items(), cursor=None)

        df = page.to_polars()

        assert isinstance(df["price"].dtype, pl.Decimal)
        assert df["price"].to_list() == [Decimal("0.55"), Decimal("0.42")]

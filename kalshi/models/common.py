"""Common model types shared across resources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas
    import polars

T = TypeVar("T", bound=BaseModel)


class Page(BaseModel, Generic[T]):
    """A page of results from a list endpoint.

    Iterable over items. Also exposes cursor metadata for manual pagination.

    Usage:
        page = client.markets.list(limit=50)
        for item in page:       # iterate items
            process(item)
        print(page.cursor)      # access cursor
        print(page.has_next)    # check if more pages exist
    """

    items: list[T]
    cursor: str | None = None
    model_config = {"extra": "allow"}

    @property
    def has_next(self) -> bool:
        return self.cursor is not None and self.cursor != ""

    def __iter__(self) -> Iterator[T]:  # type: ignore[override]
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def to_dataframe(self) -> pandas.DataFrame:
        """Return page items as a pandas DataFrame (requires kalshi-sdk[pandas])."""
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError(
                "pandas is required for Page.to_dataframe(). "
                "Install it with: pip install 'kalshi-sdk[pandas]'"
            ) from exc

        if not self.items:
            return pd.DataFrame()
        return pd.DataFrame(self._columns())

    def to_polars(self) -> polars.DataFrame:
        """Return page items as a polars DataFrame (requires kalshi-sdk[polars])."""
        try:
            import polars as pl
        except ImportError as exc:
            raise ImportError(
                "polars is required for Page.to_polars(). "
                "Install it with: pip install 'kalshi-sdk[polars]'"
            ) from exc

        if not self.items:
            return pl.DataFrame()
        return pl.DataFrame(self._columns())

    def _columns(self) -> dict[str, list[object]]:
        """Build a column-oriented dict[field, list[value]] over self.items.

        Avoids the per-row ``model_dump`` walk used previously (issue #264).
        Nested ``BaseModel`` cells are dumped to dicts per column so that
        polars can still infer a ``Struct`` dtype and the #225 / #190
        Decimal contract is preserved (DollarDecimal lands as ``Decimal``
        in ``mode="python"``, not as ``str``).
        """
        fields = type(self.items[0]).model_fields.keys()
        columns: dict[str, list[object]] = {}
        for field in fields:
            col: list[object] = [getattr(item, field) for item in self.items]
            if col and isinstance(col[0], BaseModel):
                col = [v.model_dump(mode="python") if isinstance(v, BaseModel) else v for v in col]
            columns[field] = col
        return columns

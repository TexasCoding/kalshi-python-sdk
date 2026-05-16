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

        records = [item.model_dump(mode="python") for item in self.items]
        return pd.DataFrame(records)

    def to_polars(self) -> polars.DataFrame:
        """Return page items as a polars DataFrame (requires kalshi-sdk[polars])."""
        try:
            import polars as pl
        except ImportError as exc:
            raise ImportError(
                "polars is required for Page.to_polars(). "
                "Install it with: pip install 'kalshi-sdk[polars]'"
            ) from exc

        records = [item.model_dump(mode="python") for item in self.items]
        return pl.DataFrame(records)

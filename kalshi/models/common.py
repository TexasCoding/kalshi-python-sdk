"""Common model types shared across resources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    import pandas
    import polars

T = TypeVar("T")


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
        """Return the page items as a pandas DataFrame.

        Each item is serialized via ``BaseModel.model_dump(mode="json")``,
        producing one row per item with columns matching the model fields.
        ``Decimal`` and ``datetime`` values are preserved as native Python
        types in object columns.

        Requires ``pandas`` to be installed::

            pip install "kalshi-sdk[pandas]"

        Usage:
            page = client.markets.list(limit=100)
            df = page.to_dataframe()
            df.head()
        """
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
            raise ImportError(
                "pandas is required for Page.to_dataframe(). "
                "Install it with: pip install 'kalshi-sdk[pandas]'"
            ) from exc

        records = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in self.items
        ]
        return pd.DataFrame(records)

    def to_polars(self) -> polars.DataFrame:
        """Return the page items as a polars DataFrame.

        Each item is serialized via ``BaseModel.model_dump(mode="json")``,
        producing one row per item with columns matching the model fields.

        Requires ``polars`` to be installed::

            pip install "kalshi-sdk[polars]"

        Usage:
            page = client.markets.list(limit=100)
            df = page.to_polars()
            df.head()
        """
        try:
            import polars as pl
        except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
            raise ImportError(
                "polars is required for Page.to_polars(). "
                "Install it with: pip install 'kalshi-sdk[polars]'"
            ) from exc

        records = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in self.items
        ]
        return pl.DataFrame(records)

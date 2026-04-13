"""Common model types shared across resources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

from pydantic import BaseModel

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

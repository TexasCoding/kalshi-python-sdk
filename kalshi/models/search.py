"""Search discovery models — tags-by-category and filters-by-sport.

These endpoints power the Kalshi UI search/filter surfaces. The shapes
are nested maps:

- ``tags_by_categories`` maps each series category (e.g., ``Sports``) to
  a list of tag strings.
- ``filters_by_sports`` maps each sport (e.g., ``basketball``) to its
  available scopes + competitions (where each competition has its own
  scope subset).
"""

from __future__ import annotations

from pydantic import BaseModel

from kalshi.types import NullableList


class ScopeList(BaseModel):
    """Scopes available for a specific competition within a sport."""

    scopes: NullableList[str] = []

    model_config = {"extra": "allow"}


class SportFilterDetails(BaseModel):
    """Filter options for a single sport.

    ``scopes`` lists sport-level scopes; ``competitions`` further scopes
    down by competition (NBA, NFL, etc.), each mapped to its own scope
    subset.
    """

    scopes: NullableList[str] = []
    competitions: dict[str, ScopeList] = {}

    model_config = {"extra": "allow"}


class GetTagsForSeriesCategoriesResponse(BaseModel):
    """Response from GET /search/tags_by_categories."""

    tags_by_categories: dict[str, list[str]] = {}

    model_config = {"extra": "allow"}


class GetFiltersBySportsResponse(BaseModel):
    """Response from GET /search/filters_by_sport.

    ``sport_ordering`` is the display order for sports (a list of sport
    keys that should also exist in ``filters_by_sports``).
    """

    filters_by_sports: dict[str, SportFilterDetails] = {}
    sport_ordering: NullableList[str] = []

    model_config = {"extra": "allow"}

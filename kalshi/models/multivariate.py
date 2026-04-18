"""Multivariate event collection models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from kalshi.models.markets import Market

# Side constants (use str, not StrEnum, for forward-compat)
SIDE_YES = "yes"
SIDE_NO = "no"


class AssociatedEvent(BaseModel):
    """An event associated with a multivariate collection."""

    ticker: str
    is_yes_only: bool = False
    size_max: int | None = None
    size_min: int | None = None
    active_quoters: list[str] = []

    model_config = {"extra": "allow"}


class MultivariateEventCollection(BaseModel):
    """A multivariate event collection (combo contract template)."""

    collection_ticker: str
    series_ticker: str = ""
    title: str = ""
    description: str = ""
    open_date: datetime | None = None
    close_date: datetime | None = None
    associated_events: list[AssociatedEvent] = []
    # Deprecated fields — still returned by API
    associated_event_tickers: list[str] = []
    is_single_market_per_event: bool = False
    is_all_yes: bool = False
    # Active fields
    is_ordered: bool = False
    size_min: int = 0
    size_max: int = 0
    functional_description: str = ""

    model_config = {"extra": "allow", "populate_by_name": True}


class TickerPair(BaseModel):
    """A market+event ticker pair with side, used in create/lookup request bodies."""

    market_ticker: str
    event_ticker: str
    side: str

    model_config = {"extra": "allow"}


class CreateMarketInMultivariateEventCollectionRequest(BaseModel):
    """Parameters for ``POST /multivariate_event_collections/{collection_ticker}``.

    Matches spec ``components.schemas.CreateMarketInMultivariateEventCollectionRequest``.
    Required: ``selected_markets``. Optional: ``with_market_payload``.

    See ``kalshi.resources.multivariate.MultivariateCollectionsResource.create_market``
    — v0.8.0 builds this model internally; method signature unchanged.
    """

    selected_markets: list[TickerPair]
    with_market_payload: bool | None = None

    model_config = {"extra": "forbid"}


class LookupTickersForMarketInMultivariateEventCollectionRequest(BaseModel):
    """Parameters for ``PUT /multivariate_event_collections/{collection_ticker}/lookup``.

    Matches spec
    ``components.schemas.LookupTickersForMarketInMultivariateEventCollectionRequest``.
    Only ``selected_markets``, required.

    See ``kalshi.resources.multivariate.MultivariateCollectionsResource.lookup_tickers``
    — v0.8.0 builds this model internally; method signature unchanged.
    """

    selected_markets: list[TickerPair]

    model_config = {"extra": "forbid"}


class CreateMarketResponse(BaseModel):
    """Response from creating a market in a multivariate collection."""

    event_ticker: str
    market_ticker: str
    market: Market | None = None

    model_config = {"extra": "allow"}


class LookupTickersResponse(BaseModel):
    """Response from looking up tickers in a multivariate collection."""

    event_ticker: str
    market_ticker: str

    model_config = {"extra": "allow"}


class LookupPoint(BaseModel):
    """A point in the lookup history of a multivariate collection."""

    event_ticker: str
    market_ticker: str
    selected_markets: list[TickerPair] = []
    last_queried_ts: datetime | None = None

    model_config = {"extra": "allow"}

"""Request-side contract support: SDK method → OpenAPI endpoint mapping and helpers.

This module is test infrastructure. It lives in ``tests/`` (not ``kalshi/``) so that
users importing the SDK don't get spec-parsing code shipped in the PyPI wheel.

The map covers ``path`` and ``query`` parameter surface. Body schemas (POST/PUT
request payloads built as inline dicts in ``orders.py::amend()`` etc.) are NOT
covered — those are audited by the separate inline-body-dict TODO.

Async siblings are derived at test time via ``Async<ClassName>`` substitution
with identical method names. Do NOT add separate async entries to the map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MethodEndpointEntry:
    """Maps one sync SDK method to its OpenAPI endpoint."""

    sdk_method: str
    http_method: str
    path_template: str


METHOD_ENDPOINT_MAP: list[MethodEndpointEntry] = [
    # ── markets ─────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.list",
        http_method="GET",
        path_template="/markets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.list_all",
        http_method="GET",
        path_template="/markets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.get",
        http_method="GET",
        path_template="/markets/{ticker}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.orderbook",
        http_method="GET",
        path_template="/markets/{ticker}/orderbook",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.candlesticks",
        http_method="GET",
        path_template="/series/{series_ticker}/markets/{ticker}/candlesticks",
    ),
    # ── events ──────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.list",
        http_method="GET",
        path_template="/events",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.list_all",
        http_method="GET",
        path_template="/events",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.list_multivariate",
        http_method="GET",
        path_template="/events/multivariate",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.list_all_multivariate",
        http_method="GET",
        path_template="/events/multivariate",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.get",
        http_method="GET",
        path_template="/events/{event_ticker}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.metadata",
        http_method="GET",
        path_template="/events/{event_ticker}/metadata",
    ),
    # ── exchange ────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.exchange.ExchangeResource.status",
        http_method="GET",
        path_template="/exchange/status",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.exchange.ExchangeResource.schedule",
        http_method="GET",
        path_template="/exchange/schedule",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.exchange.ExchangeResource.announcements",
        http_method="GET",
        path_template="/exchange/announcements",
    ),
    # ── historical ──────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.cutoff",
        http_method="GET",
        path_template="/historical/cutoff",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.markets",
        http_method="GET",
        path_template="/historical/markets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.markets_all",
        http_method="GET",
        path_template="/historical/markets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.market",
        http_method="GET",
        path_template="/historical/markets/{ticker}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.candlesticks",
        http_method="GET",
        path_template="/historical/markets/{ticker}/candlesticks",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.fills",
        http_method="GET",
        path_template="/historical/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.fills_all",
        http_method="GET",
        path_template="/historical/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.orders",
        http_method="GET",
        path_template="/historical/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.orders_all",
        http_method="GET",
        path_template="/historical/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.trades",
        http_method="GET",
        path_template="/historical/trades",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.historical.HistoricalResource.trades_all",
        http_method="GET",
        path_template="/historical/trades",
    ),
    # ── orders ──────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.create",
        http_method="POST",
        path_template="/portfolio/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.get",
        http_method="GET",
        path_template="/portfolio/orders/{order_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.cancel",
        http_method="DELETE",
        path_template="/portfolio/orders/{order_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.list",
        http_method="GET",
        path_template="/portfolio/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.list_all",
        http_method="GET",
        path_template="/portfolio/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.batch_create",
        http_method="POST",
        path_template="/portfolio/orders/batched",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.batch_cancel",
        http_method="DELETE",
        path_template="/portfolio/orders/batched",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.fills",
        http_method="GET",
        path_template="/portfolio/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.fills_all",
        http_method="GET",
        path_template="/portfolio/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.amend",
        http_method="POST",
        path_template="/portfolio/orders/{order_id}/amend",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.decrease",
        http_method="POST",
        path_template="/portfolio/orders/{order_id}/decrease",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.queue_positions",
        http_method="GET",
        path_template="/portfolio/orders/queue_positions",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.queue_position",
        http_method="GET",
        path_template="/portfolio/orders/{order_id}/queue_position",
    ),
    # ── portfolio ───────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.balance",
        http_method="GET",
        path_template="/portfolio/balance",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.positions",
        http_method="GET",
        path_template="/portfolio/positions",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.settlements",
        http_method="GET",
        path_template="/portfolio/settlements",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.settlements_all",
        http_method="GET",
        path_template="/portfolio/settlements",
    ),
    # ── series ──────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.series.SeriesResource.list",
        http_method="GET",
        path_template="/series",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.series.SeriesResource.get",
        http_method="GET",
        path_template="/series/{series_ticker}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.series.SeriesResource.fee_changes",
        http_method="GET",
        path_template="/series/fee_changes",
    ),
    # NOTE: SDK currently sends {event_ticker} but spec uses {ticker}.
    # Map stores the SPEC path (source of truth); SDK is RENAME target in AUDIT.
    MethodEndpointEntry(
        sdk_method="kalshi.resources.series.SeriesResource.event_candlesticks",
        http_method="GET",
        path_template="/series/{series_ticker}/events/{ticker}/candlesticks",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.series.SeriesResource.forecast_percentile_history"
        ),
        http_method="GET",
        path_template=(
            "/series/{series_ticker}/events/{ticker}/forecast_percentile_history"
        ),
    ),
    # ── multivariate ────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource.list"
        ),
        http_method="GET",
        path_template="/multivariate_event_collections",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource.list_all"
        ),
        http_method="GET",
        path_template="/multivariate_event_collections",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource.get"
        ),
        http_method="GET",
        path_template="/multivariate_event_collections/{collection_ticker}",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource."
            "create_market"
        ),
        http_method="POST",
        path_template="/multivariate_event_collections/{collection_ticker}",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource."
            "lookup_tickers"
        ),
        http_method="PUT",
        path_template="/multivariate_event_collections/{collection_ticker}/lookup",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource."
            "lookup_history"
        ),
        http_method="GET",
        path_template="/multivariate_event_collections/{collection_ticker}/lookup",
    ),
]


def _resolve_ref(
    spec: dict[str, Any],
    ref: str,
    *,
    depth: int = 0,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Resolve a ``$ref`` pointer. Caps recursion depth to avoid silent infinite
    loops if the spec ever introduces a circular reference."""
    if depth > max_depth:
        raise RuntimeError(
            f"_resolve_ref exceeded max_depth={max_depth} resolving {ref!r}; "
            "check spec for circular $ref"
        )
    if not ref.startswith("#/"):
        raise ValueError(
            f"_resolve_ref only supports local refs starting with '#/', got {ref!r}"
        )
    # JSON Pointer escape decoding: ~1 → /, ~0 → ~ (RFC 6901 §4).
    # Order matters: decode ~1 first, then ~0.
    # Use [2:] not lstrip("#/"): lstrip treats arg as a char set, so "#///foo"
    # would strip to "foo" instead of "//foo". Prefix already validated above.
    parts = [p.replace("~1", "/").replace("~0", "~") for p in ref[2:].split("/")]
    node: Any = spec
    for part in parts:
        node = node[part]
    if isinstance(node, dict) and "$ref" in node:
        return _resolve_ref(spec, node["$ref"], depth=depth + 1, max_depth=max_depth)
    return node  # type: ignore[no-any-return]


def _resolve_path_params(
    spec: dict[str, Any],
    path_template: str,
    http_method: str,
    *,
    max_ref_depth: int = 8,
) -> list[dict[str, Any]]:
    """Return the merged list of parameter objects for a specific operation.

    Walks BOTH path-level ``parameters`` (shared across operations on that path)
    AND operation-level ``parameters`` (specific to the given HTTP method).
    Operation-level entries override path-level by the ``(name, in)`` key —
    OpenAPI permits the same parameter name in different locations (e.g., a
    path param and a query param both named ``ticker``), so dedup must consider
    both dimensions.
    Any ``$ref`` entries are resolved via ``_resolve_ref``.

    Raises ``KeyError`` if the path does not exist in the spec, or if the
    operation (HTTP method) does not exist on that path. Fail loud: a
    mismatched ``METHOD_ENDPOINT_MAP`` entry should surface at test time, not
    silently return partial data.
    """
    paths = spec.get("paths", {})
    if path_template not in paths:
        raise KeyError(f"path {path_template!r} not found in spec")

    path_entry = paths[path_template]
    op_key = http_method.lower()

    if op_key not in path_entry:
        raise KeyError(
            f"operation {http_method!r} not defined on path {path_template!r}; "
            f"available ops: "
            f"{sorted(k for k in path_entry if k in {'get', 'post', 'put', 'delete', 'patch'})}"
        )

    def _collect(parameters_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for param in parameters_list:
            if "$ref" in param:
                resolved.append(_resolve_ref(spec, param["$ref"], max_depth=max_ref_depth))
            else:
                resolved.append(param)
        return resolved

    path_level = _collect(path_entry.get("parameters", []))
    op_entry = path_entry[op_key]
    op_level = _collect(op_entry.get("parameters", []))

    # Merge with op-level overriding path-level by (name, in) — OpenAPI allows
    # the same param name in different locations (path vs query vs header).
    merged: dict[tuple[str, str], dict[str, Any]] = {
        (p["name"], p.get("in", "")): p for p in path_level
    }
    for p in op_level:
        merged[(p["name"], p.get("in", ""))] = p
    return list(merged.values())

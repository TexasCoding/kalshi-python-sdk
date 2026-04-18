"""Request-side contract support: SDK method → OpenAPI endpoint mapping and helpers.

This module is test infrastructure. It lives in ``tests/`` (not ``kalshi/``) so that
users importing the SDK don't get spec-parsing code shipped in the PyPI wheel.

The map covers ``path``, ``query``, and ``requestBody`` surface. Body schemas
for POST/PUT endpoints are referenced via ``MethodEndpointEntry.request_body_schema``
(a spec ``$ref`` string) and resolved via ``_resolve_request_body_schema``. Drift
tests that consume this infrastructure (``TestRequestParamDrift``,
``TestRequestBodyDrift``) land in subsequent v0.8.0 tasks.

Async siblings are derived at test time via ``Async<ClassName>`` substitution
with identical method names. Do NOT add separate async entries to the map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MethodEndpointEntry:
    """Maps one sync SDK method to its OpenAPI endpoint.

    ``request_body_schema`` is the spec ref for POST/PUT request bodies
    (e.g., ``"#/components/schemas/CreateOrderRequest"``). None for
    GET/DELETE endpoints. Defaulted so existing entries don't need to be
    touched; new POST/PUT entries SHOULD populate it so ``TestRequestBodyDrift``
    has something to diff against.
    """

    sdk_method: str
    http_method: str
    path_template: str
    request_body_schema: str | None = None


@dataclass(frozen=True)
class Exclusion:
    """Intentional deviation from the OpenAPI spec, with a human-readable reason.

    Values in ``EXCLUSIONS`` carry this dataclass. The ``reason`` field is
    required — nameless deviations are a bug we refuse to ship.
    """

    reason: str


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
        request_body_schema="#/components/schemas/CreateOrderRequest",
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
        request_body_schema="#/components/schemas/BatchCreateOrdersRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.batch_cancel",
        http_method="DELETE",
        path_template="/portfolio/orders/batched",
        request_body_schema="#/components/schemas/BatchCancelOrdersRequest",
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
        request_body_schema="#/components/schemas/AmendOrderRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.decrease",
        http_method="POST",
        path_template="/portfolio/orders/{order_id}/decrease",
        request_body_schema="#/components/schemas/DecreaseOrderRequest",
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
    # ── order groups ────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.list",
        http_method="GET",
        path_template="/portfolio/order_groups",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.get",
        http_method="GET",
        path_template="/portfolio/order_groups/{order_group_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.create",
        http_method="POST",
        path_template="/portfolio/order_groups/create",
        request_body_schema="#/components/schemas/CreateOrderGroupRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.delete",
        http_method="DELETE",
        path_template="/portfolio/order_groups/{order_group_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.reset",
        http_method="PUT",
        path_template="/portfolio/order_groups/{order_group_id}/reset",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.trigger",
        http_method="PUT",
        path_template="/portfolio/order_groups/{order_group_id}/trigger",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.order_groups.OrderGroupsResource.update_limit",
        http_method="PUT",
        path_template="/portfolio/order_groups/{order_group_id}/limit",
        request_body_schema="#/components/schemas/UpdateOrderGroupLimitRequest",
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
        request_body_schema="#/components/schemas/CreateMarketInMultivariateEventCollectionRequest",
    ),
    MethodEndpointEntry(
        sdk_method=(
            "kalshi.resources.multivariate.MultivariateCollectionsResource."
            "lookup_tickers"
        ),
        http_method="PUT",
        path_template="/multivariate_event_collections/{collection_ticker}/lookup",
        request_body_schema="#/components/schemas/LookupTickersForMarketInMultivariateEventCollectionRequest",
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


# ---------------------------------------------------------------------------
# EXCLUSIONS allowlist for request-side drift tests
# ---------------------------------------------------------------------------
# Keys are ``(sdk_fqn, param_or_field_name)`` tuples. Values are ``Exclusion``
# dataclasses with a required ``reason`` string. An entry declares "this is
# not drift; here's why." Tests that fail to find the corresponding drift
# should also fail (see ``test_exclusion_map_is_current``), so stale entries
# don't accumulate.
#
# BOOTSTRAP (v0.8.0) — two classes of entries:
#   1. ``CreateOrderRequest`` spec fields the SDK deliberately omits (cent-form
#      redundant with ``_dollars`` variants; deprecated-in-spec).
#   2. ``cursor`` on every ``list_all`` method — paginator-handled internally;
#      the kwarg is absent from the method signature by design.
#
# Additional entries for ``AmendOrderRequest`` get appended in Task 3 (after
# that model is created). Do NOT preload them here — forward references to
# a model that doesn't exist yet will trip mypy on import.

EXCLUSIONS: dict[tuple[str, str], Exclusion] = {
    # --- CreateOrderRequest spec fields deliberately not on the model ---
    ("kalshi.models.orders.CreateOrderRequest", "yes_price"): Exclusion(
        reason=(
            "cent form redundant with yes_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
    ),
    ("kalshi.models.orders.CreateOrderRequest", "no_price"): Exclusion(
        reason=(
            "cent form redundant with no_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
    ),
    ("kalshi.models.orders.CreateOrderRequest", "sell_position_floor"): Exclusion(
        reason="deprecated in spec (only accepts 0); superseded by reduce_only",
    ),
    # --- cursor exclusions on list_all variants (paginator-handled) ---
    ("kalshi.resources.markets.MarketsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.events.EventsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.events.EventsResource.list_all_multivariate", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.historical.HistoricalResource.markets_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.historical.HistoricalResource.fills_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.historical.HistoricalResource.orders_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.historical.HistoricalResource.trades_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.orders.OrdersResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.orders.OrdersResource.fills_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.settlements_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    ("kalshi.resources.multivariate.MultivariateCollectionsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
    ),
    # --- batch_cancel body param (not a query/path param) ---
    ("kalshi.resources.orders.OrdersResource.batch_cancel", "orders"): Exclusion(
        reason="body param (BatchCancelOrdersRequest.orders); not query/path",
    ),
    # --- AmendOrderRequest spec fields deliberately not on the model ---
    ("kalshi.models.orders.AmendOrderRequest", "yes_price"): Exclusion(
        reason=(
            "cent form redundant with yes_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
    ),
    ("kalshi.models.orders.AmendOrderRequest", "no_price"): Exclusion(
        reason=(
            "cent form redundant with no_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
    ),
    # --- count wire normalization (v0.8.0) ---
    # Spec has both count (int) and count_fp (FixedPointCount); SDK commits to
    # emitting count_fp only (serialization_alias="count_fp"). Kalshi accepts
    # either key per spec description. Documented in CHANGELOG as "count wire
    # key normalized to count_fp".
    ("kalshi.models.orders.CreateOrderRequest", "count"): Exclusion(
        reason=(
            "SDK emits count_fp (serialization_alias) instead of count; "
            "Kalshi accepts either; normalized to count_fp per v0.8.0 wire shape decision"
        ),
    ),
    ("kalshi.models.orders.AmendOrderRequest", "count"): Exclusion(
        reason=(
            "SDK emits count_fp (serialization_alias) instead of count; "
            "Kalshi accepts either; amend() used count_fp pre-v0.8.0 already"
        ),
    ),
    # --- DecreaseOrderRequest _fp variants not implemented ---
    # Spec has reduce_by_fp and reduce_to_fp (FixedPointCount string) as
    # alternatives to reduce_by/reduce_to (int). SDK only emits the integer
    # forms. Spec says "if both provided they must match" — sending only
    # integer form is valid. v0.8.0 deferred _fp variants (fractional
    # contracts not yet relevant for decrease operations).
    ("kalshi.models.orders.DecreaseOrderRequest", "reduce_by_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of reduce_by; SDK emits integer reduce_by only; "
            "spec accepts either form; _fp variant deferred post-v0.8.0"
        ),
    ),
    ("kalshi.models.orders.DecreaseOrderRequest", "reduce_to_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of reduce_to; SDK emits integer reduce_to only; "
            "spec accepts either form; _fp variant deferred post-v0.8.0"
        ),
    ),
    # --- BatchCancelOrdersRequest deprecated ids field ---
    # Spec has ids (array of strings, marked deprecated) as an alternative to
    # the preferred orders field. SDK v0.8.0 migrated from ids to orders and
    # does not emit ids. Documented in CHANGELOG as BREAKING wire field flip.
    ("kalshi.models.orders.BatchCancelOrdersRequest", "ids"): Exclusion(
        reason=(
            "deprecated spec field; SDK v0.8.0 migrated to preferred 'orders' field; "
            "intentional REMOVE drift documented in CHANGELOG"
        ),
    ),
    # --- CreateOrderGroupRequest / UpdateOrderGroupLimitRequest _fp variants ---
    # Spec has both contracts_limit (int) and contracts_limit_fp (FixedPointCount
    # string) as mutually-compatible representations. SDK commits to the integer
    # form (contracts_limit); Kalshi accepts either. Same pattern as count_fp on
    # order requests (v0.8.0).
    ("kalshi.models.order_groups.CreateOrderGroupRequest", "contracts_limit_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of contracts_limit; SDK emits integer contracts_limit only; "
            "Kalshi accepts either form; _fp variant intentionally omitted (v0.10.0)"
        ),
    ),
    ("kalshi.models.order_groups.UpdateOrderGroupLimitRequest", "contracts_limit_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of contracts_limit; SDK emits integer contracts_limit only; "
            "Kalshi accepts either form; _fp variant intentionally omitted (v0.10.0)"
        ),
    ),
}


def _resolve_ref(
    spec: dict[str, Any],
    ref: str,
    *,
    depth: int = 0,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Resolve a ``$ref`` pointer. Caps recursion depth to avoid silent infinite
    loops if the spec ever introduces a circular reference.

    Condition is ``depth > max_depth``, so with the default ``max_depth=8``
    the function permits up to 9 total calls (depths 0-8 inclusive) before
    raising on the 10th.
    """
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


def _resolve_request_body_schema(
    spec: dict[str, Any],
    path_template: str,
    http_method: str,
    *,
    max_ref_depth: int = 8,
) -> dict[str, Any] | None:
    """Return the resolved request body schema for any operation with a
    ``requestBody`` (HTTP method-agnostic: POST/PUT/PATCH — and DELETE, which
    the Kalshi spec uses for ``batch_cancel``). Follows ``$ref`` pointers in
    ``content['application/json'].schema`` and resolves them via ``_resolve_ref``.

    Only ``application/json`` content is considered — Kalshi's spec doesn't use
    other media types for request bodies. If that changes, extend this function.

    Returns ``None`` when the operation has no ``requestBody`` key at all, or
    when the body has no ``application/json`` content or no ``schema`` under
    it. Returns the resolved schema dict otherwise (with any top-level ``$ref``
    already chased).
    """
    paths = spec.get("paths", {})
    if path_template not in paths:
        raise KeyError(f"path {path_template!r} not found in spec")

    op_key = http_method.lower()
    path_entry = paths[path_template]
    if op_key not in path_entry:
        raise KeyError(
            f"operation {http_method!r} not defined on path {path_template!r}"
        )

    op_entry = path_entry[op_key]
    request_body = op_entry.get("requestBody")
    if not request_body:
        return None

    content = request_body.get("content", {})
    json_content = content.get("application/json")
    if not json_content:
        return None

    schema = json_content.get("schema")
    if not schema:
        return None

    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"], max_depth=max_ref_depth)

    return schema  # type: ignore[no-any-return]

"""Contract test infrastructure: SDK ↔ spec mapping + the EXCLUSIONS allowlist.

This module is test infrastructure. It lives in ``tests/`` (not ``kalshi/``) so
that users importing the SDK don't get spec-parsing code shipped in the PyPI
wheel.

``METHOD_ENDPOINT_MAP`` covers the request side: ``path``, ``query``, and
``requestBody`` surface. Body schemas for POST/PUT/DELETE-with-body endpoints
are referenced via ``MethodEndpointEntry.request_body_schema`` (a spec ``$ref``
string) and resolved via ``_resolve_request_body_schema``.

``EXCLUSIONS`` is consulted by FOUR drift checks:

  - ``TestRequestParamDrift``  — query/path kwargs vs. spec parameters
  - ``TestRequestBodyDrift``   — request body model properties vs. spec
  - ``TestSpecDrift``          — REST response model fields vs. OpenAPI
                                 (``test_additive_drift`` + ``test_required_drift``)
  - ``TestWsSpecDrift``        — WS payload model fields vs. AsyncAPI
                                 (``test_ws_additive_drift`` + ``test_ws_required_drift``)

A single ``(sdk_fqn, field_name)`` key may serve more than one check — e.g.
``CreateOrderRequest`` and ``CreateRFQRequest`` are both request bodies AND
response schemas in the spec, so a field exclusion is reused by both sides.
Add a new entry once at the model+field coordinate; do NOT duplicate it.

Async siblings are derived at test time via ``Async<ClassName>`` substitution
with identical method names. Do NOT add separate async entries to the map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExclusionKind = Literal[
    "body_param",
    "spec_deprecated",
    "paginator_handled",
    "wire_normalization",
    "kwarg_rename",
    "client_only",
    "server_omits_despite_required",
]


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
    """Intentional deviation from the OpenAPI spec, with a typed category and reason.

    Values in ``EXCLUSIONS`` carry this dataclass. ``reason`` is a free-text
    human note. ``kind`` is the machine-readable category used by the
    drift-classifier in ``test_exclusion_map_is_current`` — classifying by
    substring-match on ``reason`` is fragile, so the kind is explicit.

    Categories (see issue #51):
      - ``body_param``: kwarg is a body field, not a query/path param.
      - ``spec_deprecated``: spec field marked deprecated; SDK omits it.
      - ``paginator_handled``: ``cursor`` on a ``list_all`` method,
        handled internally by the paginator (not a caller kwarg).
      - ``wire_normalization``: SDK emits a different wire shape than the
        spec field (e.g., ``count`` → ``count_fp``, cent form vs ``_dollars``,
        integer vs ``_fp`` variant).
      - ``kwarg_rename``: SDK kwarg renamed from the spec field to avoid
        shadowing a Python built-in (e.g., spec's ``type`` becomes
        ``milestone_type`` / ``target_type`` / ``incentive_type``). The wire
        value is unchanged; only the Python signature differs.
      - ``client_only``: SDK kwarg with no wire counterpart — purely a
        client-side knob (e.g., ``max_pages`` cap on ``*_all`` paginators).
        Legitimately present in the signature; not drift.
      - ``server_omits_despite_required``: spec marks the field
        ``required: true`` but the live server omits it in practice.
        Added in #172 for response-side fields that would otherwise force
        the SDK to raise ``ValidationError`` on real responses. Each entry
        MUST cite at least one verified server observation (demo nightly
        run ID, or a prod-traffic capture date) in ``reason``. Prod
        confirmation is preferred but not always achievable from CI.
    """

    reason: str
    kind: ExclusionKind


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
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.list_trades",
        http_method="GET",
        path_template="/markets/trades",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.list_trades_all",
        http_method="GET",
        path_template="/markets/trades",
    ),
    # v3.0.0 standardization on ``list_all_<noun>`` (#349); old
    # ``list_trades_all`` is a deprecated forwarder.
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.list_all_trades",
        http_method="GET",
        path_template="/markets/trades",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.bulk_candlesticks",
        http_method="GET",
        path_template="/markets/candlesticks",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.markets.MarketsResource.bulk_orderbooks",
        http_method="GET",
        path_template="/markets/orderbooks",
    ),
    # ── account ─────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.account.AccountResource.limits",
        http_method="GET",
        path_template="/account/limits",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.account.AccountResource.endpoint_costs",
        http_method="GET",
        path_template="/account/endpoint_costs",
    ),
    # ── api keys ────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.api_keys.ApiKeysResource.list",
        http_method="GET",
        path_template="/api_keys",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.api_keys.ApiKeysResource.create",
        http_method="POST",
        path_template="/api_keys",
        request_body_schema="#/components/schemas/CreateApiKeyRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.api_keys.ApiKeysResource.generate",
        http_method="POST",
        path_template="/api_keys/generate",
        request_body_schema="#/components/schemas/GenerateApiKeyRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.api_keys.ApiKeysResource.delete",
        http_method="DELETE",
        path_template="/api_keys/{api_key}",
    ),
    # ── milestones ──────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.milestones.MilestonesResource.list",
        http_method="GET",
        path_template="/milestones",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.milestones.MilestonesResource.list_all",
        http_method="GET",
        path_template="/milestones",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.milestones.MilestonesResource.get",
        http_method="GET",
        path_template="/milestones/{milestone_id}",
    ),
    # ── live data ───────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.live_data.LiveDataResource.get",
        http_method="GET",
        path_template="/live_data/milestone/{milestone_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.live_data.LiveDataResource.get_typed",
        http_method="GET",
        path_template="/live_data/{type}/milestone/{milestone_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.live_data.LiveDataResource.batch",
        http_method="GET",
        path_template="/live_data/batch",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.live_data.LiveDataResource.game_stats",
        http_method="GET",
        path_template="/live_data/milestone/{milestone_id}/game_stats",
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
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.fee_changes",
        http_method="GET",
        path_template="/events/fee_changes",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.events.EventsResource.fee_changes_all",
        http_method="GET",
        path_template="/events/fee_changes",
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
    MethodEndpointEntry(
        sdk_method="kalshi.resources.exchange.ExchangeResource.user_data_timestamp",
        http_method="GET",
        path_template="/exchange/user_data_timestamp",
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
    # ── orders v2 (event-market, spec v3.18.0) ──────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.create_v2",
        http_method="POST",
        path_template="/portfolio/events/orders",
        request_body_schema="#/components/schemas/CreateOrderV2Request",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.cancel_v2",
        http_method="DELETE",
        path_template="/portfolio/events/orders/{order_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.amend_v2",
        http_method="POST",
        path_template="/portfolio/events/orders/{order_id}/amend",
        request_body_schema="#/components/schemas/AmendOrderV2Request",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.decrease_v2",
        http_method="POST",
        path_template="/portfolio/events/orders/{order_id}/decrease",
        request_body_schema="#/components/schemas/DecreaseOrderV2Request",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.batch_create_v2",
        http_method="POST",
        path_template="/portfolio/events/orders/batched",
        request_body_schema="#/components/schemas/BatchCreateOrdersV2Request",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.orders.OrdersResource.batch_cancel_v2",
        http_method="DELETE",
        path_template="/portfolio/events/orders/batched",
        request_body_schema="#/components/schemas/BatchCancelOrdersV2Request",
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
    # ── communications / RFQ ────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.get_id",
        http_method="GET",
        path_template="/communications/id",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.list_rfqs",
        http_method="GET",
        path_template="/communications/rfqs",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.list_all_rfqs",
        http_method="GET",
        path_template="/communications/rfqs",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.create_rfq",
        http_method="POST",
        path_template="/communications/rfqs",
        request_body_schema="#/components/schemas/CreateRFQRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.get_rfq",
        http_method="GET",
        path_template="/communications/rfqs/{rfq_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.delete_rfq",
        http_method="DELETE",
        path_template="/communications/rfqs/{rfq_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.list_quotes",
        http_method="GET",
        path_template="/communications/quotes",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.list_all_quotes",
        http_method="GET",
        path_template="/communications/quotes",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.create_quote",
        http_method="POST",
        path_template="/communications/quotes",
        request_body_schema="#/components/schemas/CreateQuoteRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.get_quote",
        http_method="GET",
        path_template="/communications/quotes/{quote_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.delete_quote",
        http_method="DELETE",
        path_template="/communications/quotes/{quote_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.accept_quote",
        http_method="PUT",
        path_template="/communications/quotes/{quote_id}/accept",
        request_body_schema="#/components/schemas/AcceptQuoteRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.CommunicationsResource.confirm_quote",
        http_method="PUT",
        path_template="/communications/quotes/{quote_id}/confirm",
    ),
    # v3.0.0 sub-namespaces (#348) — same endpoints, new shape.
    # ``CommunicationsResource.{rfqs,quotes}.<verb>`` is canonical; the flat
    # forwarders above are kept as deprecated aliases for one release.
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.RFQsResource.list",
        http_method="GET",
        path_template="/communications/rfqs",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.RFQsResource.list_all",
        http_method="GET",
        path_template="/communications/rfqs",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.RFQsResource.create",
        http_method="POST",
        path_template="/communications/rfqs",
        request_body_schema="#/components/schemas/CreateRFQRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.RFQsResource.get",
        http_method="GET",
        path_template="/communications/rfqs/{rfq_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.RFQsResource.delete",
        http_method="DELETE",
        path_template="/communications/rfqs/{rfq_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.list",
        http_method="GET",
        path_template="/communications/quotes",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.list_all",
        http_method="GET",
        path_template="/communications/quotes",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.create",
        http_method="POST",
        path_template="/communications/quotes",
        request_body_schema="#/components/schemas/CreateQuoteRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.get",
        http_method="GET",
        path_template="/communications/quotes/{quote_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.delete",
        http_method="DELETE",
        path_template="/communications/quotes/{quote_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.accept",
        http_method="PUT",
        path_template="/communications/quotes/{quote_id}/accept",
        request_body_schema="#/components/schemas/AcceptQuoteRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.communications.QuotesResource.confirm",
        http_method="PUT",
        path_template="/communications/quotes/{quote_id}/confirm",
    ),
    # ── subaccounts ─────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.create",
        http_method="POST",
        path_template="/portfolio/subaccounts",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.transfer",
        http_method="POST",
        path_template="/portfolio/subaccounts/transfer",
        request_body_schema="#/components/schemas/ApplySubaccountTransferRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.list_balances",
        http_method="GET",
        path_template="/portfolio/subaccounts/balances",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.list_transfers",
        http_method="GET",
        path_template="/portfolio/subaccounts/transfers",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.list_all_transfers",
        http_method="GET",
        path_template="/portfolio/subaccounts/transfers",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.update_netting",
        http_method="PUT",
        path_template="/portfolio/subaccounts/netting",
        request_body_schema="#/components/schemas/UpdateSubaccountNettingRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.subaccounts.SubaccountsResource.get_netting",
        http_method="GET",
        path_template="/portfolio/subaccounts/netting",
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
        sdk_method="kalshi.resources.portfolio.PortfolioResource.positions_all",
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
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.total_resting_order_value",
        http_method="GET",
        path_template="/portfolio/summary/total_resting_order_value",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.deposits",
        http_method="GET",
        path_template="/portfolio/deposits",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.deposits_all",
        http_method="GET",
        path_template="/portfolio/deposits",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.withdrawals",
        http_method="GET",
        path_template="/portfolio/withdrawals",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.withdrawals_all",
        http_method="GET",
        path_template="/portfolio/withdrawals",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.fills",
        http_method="GET",
        path_template="/portfolio/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.portfolio.PortfolioResource.fills_all",
        http_method="GET",
        path_template="/portfolio/fills",
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
    MethodEndpointEntry(
        sdk_method="kalshi.resources.series.SeriesResource.event_candlesticks",
        http_method="GET",
        path_template="/series/{series_ticker}/events/{ticker}/candlesticks",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.series.SeriesResource.forecast_percentile_history"),
        http_method="GET",
        path_template=("/series/{series_ticker}/events/{ticker}/forecast_percentile_history"),
    ),
    # ── fcm ─────────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.fcm.FcmResource.orders",
        http_method="GET",
        path_template="/fcm/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.fcm.FcmResource.orders_all",
        http_method="GET",
        path_template="/fcm/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.fcm.FcmResource.positions",
        http_method="GET",
        path_template="/fcm/positions",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.fcm.FcmResource.positions_all",
        http_method="GET",
        path_template="/fcm/positions",
    ),
    # ── incentive programs ──────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.incentive_programs.IncentiveProgramsResource.list",
        http_method="GET",
        path_template="/incentive_programs",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all",
        http_method="GET",
        path_template="/incentive_programs",
    ),
    # ── search ──────────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.search.SearchResource.tags_by_categories",
        http_method="GET",
        path_template="/search/tags_by_categories",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.search.SearchResource.filters_by_sport",
        http_method="GET",
        path_template="/search/filters_by_sport",
    ),
    # ── structured targets ──────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.resources.structured_targets.StructuredTargetsResource.list",
        http_method="GET",
        path_template="/structured_targets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.structured_targets.StructuredTargetsResource.list_all",
        http_method="GET",
        path_template="/structured_targets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.resources.structured_targets.StructuredTargetsResource.get",
        http_method="GET",
        path_template="/structured_targets/{structured_target_id}",
    ),
    # ── multivariate ────────────────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.list"),
        http_method="GET",
        path_template="/multivariate_event_collections",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.list_all"),
        http_method="GET",
        path_template="/multivariate_event_collections",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.get"),
        http_method="GET",
        path_template="/multivariate_event_collections/{collection_ticker}",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.create_market"),
        http_method="POST",
        path_template="/multivariate_event_collections/{collection_ticker}",
        request_body_schema="#/components/schemas/CreateMarketInMultivariateEventCollectionRequest",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.lookup_tickers"),
        http_method="PUT",
        path_template="/multivariate_event_collections/{collection_ticker}/lookup",
        request_body_schema="#/components/schemas/LookupTickersForMarketInMultivariateEventCollectionRequest",
    ),
    MethodEndpointEntry(
        sdk_method=("kalshi.resources.multivariate.MultivariateCollectionsResource.lookup_history"),
        http_method="GET",
        path_template="/multivariate_event_collections/{collection_ticker}/lookup",
    ),
]


# ---------------------------------------------------------------------------
# EXCLUSIONS allowlist for drift tests (request + response)
# ---------------------------------------------------------------------------
# Keys are ``(sdk_fqn, param_or_field_name)`` tuples. Values are ``Exclusion``
# dataclasses with required ``reason`` and ``kind`` fields. An entry declares
# "this is not drift; here's why."
#
# Consumers (see this module's docstring for full coverage):
#   - request side : ``TestRequestParamDrift``, ``TestRequestBodyDrift``
#   - response side: ``TestSpecDrift`` (additive + required),
#                    ``TestWsSpecDrift`` (additive + required)
#
# A single key may serve more than one check — e.g. ``CreateOrderRequest`` is
# both a request body and a response schema in the spec, so a field-level
# exclusion is reused by both sides. Add a new entry once at the model+field
# coordinate; do NOT duplicate it per drift test.
#
# Tests that fail to find the corresponding drift should also fail (see
# ``test_exclusion_map_is_current``), so stale entries can't silently
# accumulate.
EXCLUSIONS: dict[tuple[str, str], Exclusion] = {
    # --- CreateOrderRequest spec fields deliberately not on the model ---
    ("kalshi.models.orders.CreateOrderRequest", "yes_price"): Exclusion(
        reason=(
            "cent form redundant with yes_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
        kind="wire_normalization",
    ),
    ("kalshi.models.orders.CreateOrderRequest", "no_price"): Exclusion(
        reason=(
            "cent form redundant with no_price_dollars; caller passes dollars, wire carries dollars"
        ),
        kind="wire_normalization",
    ),
    ("kalshi.models.orders.CreateOrderRequest", "sell_position_floor"): Exclusion(
        reason="deprecated in spec (only accepts 0); superseded by reduce_only",
        kind="spec_deprecated",
    ),
    # --- cursor exclusions on list_all variants (paginator-handled) ---
    ("kalshi.resources.markets.MarketsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.events.EventsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.events.EventsResource.list_all_multivariate", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.events.EventsResource.fee_changes_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on fee_changes_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.historical.HistoricalResource.markets_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.historical.HistoricalResource.fills_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.historical.HistoricalResource.orders_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.historical.HistoricalResource.trades_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.orders.OrdersResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.orders.OrdersResource.fills_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.settlements_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.multivariate.MultivariateCollectionsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.deposits_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.positions_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.fcm.FcmResource.positions_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.withdrawals_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.portfolio.PortfolioResource.fills_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- batch_cancel body param (not a query/path param) ---
    ("kalshi.resources.orders.OrdersResource.batch_cancel", "orders"): Exclusion(
        reason="body param (BatchCancelOrdersRequest.orders); not query/path",
        kind="body_param",
    ),
    # --- model-first overload kwarg (#56) ---
    # batch_cancel is the only POST/PUT/DELETE-with-body endpoint covered by
    # TestRequestParamDrift (DELETE with requestBody). The `request` kwarg is
    # an SDK-side ergonomic overload, not a spec field. See #56.
    # No matching AsyncOrdersResource.batch_cancel entry needed: the drift
    # test indexes EXCLUSIONS by the sync FQN and reuses it for the async
    # sibling (test_contracts.py: "EXCLUSIONS is indexed by the SYNC method
    # fqn; async tests reuse the same allowlist entries").
    ("kalshi.resources.orders.OrdersResource.batch_cancel", "request"): Exclusion(
        reason="Optional request-model overload; not a spec field. See #56.",
        kind="body_param",
    ),
    ("kalshi.resources.orders.OrdersResource.batch_cancel_v2", "request"): Exclusion(
        reason=(
            "Required request-model kwarg for the model-only V2 surface; "
            "not a spec field. Mirrors batch_cancel."
        ),
        kind="body_param",
    ),
    # --- AmendOrderRequest spec fields deliberately not on the model ---
    ("kalshi.models.orders.AmendOrderRequest", "yes_price"): Exclusion(
        reason=(
            "cent form redundant with yes_price_dollars; caller passes dollars, "
            "wire carries dollars"
        ),
        kind="wire_normalization",
    ),
    ("kalshi.models.orders.AmendOrderRequest", "no_price"): Exclusion(
        reason=(
            "cent form redundant with no_price_dollars; caller passes dollars, wire carries dollars"
        ),
        kind="wire_normalization",
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
        kind="wire_normalization",
    ),
    ("kalshi.models.orders.AmendOrderRequest", "count"): Exclusion(
        reason=(
            "SDK emits count_fp (serialization_alias) instead of count; "
            "Kalshi accepts either; amend() used count_fp pre-v0.8.0 already"
        ),
        kind="wire_normalization",
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
        kind="wire_normalization",
    ),
    ("kalshi.models.orders.DecreaseOrderRequest", "reduce_to_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of reduce_to; SDK emits integer reduce_to only; "
            "spec accepts either form; _fp variant deferred post-v0.8.0"
        ),
        kind="wire_normalization",
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
        kind="spec_deprecated",
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
        kind="wire_normalization",
    ),
    ("kalshi.models.order_groups.UpdateOrderGroupLimitRequest", "contracts_limit_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of contracts_limit; SDK emits integer contracts_limit only; "
            "Kalshi accepts either form; _fp variant intentionally omitted (v0.10.0)"
        ),
        kind="wire_normalization",
    ),
    # --- list_all cursor exclusions for communications paginators ---
    ("kalshi.resources.communications.CommunicationsResource.list_all_rfqs", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.communications.CommunicationsResource.list_all_quotes", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- CreateRFQRequest deviations (v0.11.0) ---
    # Same count / count_fp precedent as order_groups: SDK commits to integer form.
    ("kalshi.models.communications.CreateRFQRequest", "contracts_fp"): Exclusion(
        reason=(
            "FixedPointCount variant of contracts; SDK emits integer contracts only; "
            "Kalshi accepts either form; _fp variant intentionally omitted (v0.11.0)"
        ),
        kind="wire_normalization",
    ),
    ("kalshi.models.communications.CreateRFQRequest", "target_cost_centi_cents"): Exclusion(
        reason=(
            "deprecated in spec; superseded by target_cost_dollars which SDK ships as "
            "target_cost (serialization_alias='target_cost_dollars')"
        ),
        kind="spec_deprecated",
    ),
    # --- list_all cursor exclusions for subaccounts paginator ---
    ("kalshi.resources.subaccounts.SubaccountsResource.list_all_transfers", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- list_all cursor exclusions for markets/milestones paginators ---
    ("kalshi.resources.markets.MarketsResource.list_trades_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.communications.RFQsResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.communications.QuotesResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.markets.MarketsResource.list_all_trades", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.resources.milestones.MilestonesResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- live_data.get_typed: `type` path param renamed to `milestone_type` ---
    # SDK exposes `milestone_type` (not `type`) to avoid shadowing the Python
    # built-in; the value still populates the spec's `{type}` path segment.
    ("kalshi.resources.live_data.LiveDataResource.get_typed", "type"): Exclusion(
        reason="SDK kwarg named milestone_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    ("kalshi.resources.live_data.LiveDataResource.get_typed", "milestone_type"): Exclusion(
        reason=(
            "SDK renamed from spec's `{type}` path segment to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same value, "
            "different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    # --- milestones.list/list_all: `type` query param renamed to `milestone_type` ---
    # Same rationale as get_typed above. Wire still sends `?type=...`.
    ("kalshi.resources.milestones.MilestonesResource.list", "type"): Exclusion(
        reason="SDK kwarg named milestone_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    ("kalshi.resources.milestones.MilestonesResource.list", "milestone_type"): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    ("kalshi.resources.milestones.MilestonesResource.list_all", "type"): Exclusion(
        reason="SDK kwarg named milestone_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    ("kalshi.resources.milestones.MilestonesResource.list_all", "milestone_type"): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    # --- structured_targets.list/list_all: `type` query param renamed to `target_type` ---
    # Same shadow-avoidance rationale as milestones + live_data. Wire still sends `?type=...`.
    (
        "kalshi.resources.structured_targets.StructuredTargetsResource.list",
        "type",
    ): Exclusion(
        reason="SDK kwarg named target_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.structured_targets.StructuredTargetsResource.list",
        "target_type",
    ): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.structured_targets.StructuredTargetsResource.list_all",
        "type",
    ): Exclusion(
        reason="SDK kwarg named target_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.structured_targets.StructuredTargetsResource.list_all",
        "target_type",
    ): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.structured_targets.StructuredTargetsResource.list_all",
        "cursor",
    ): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- fcm.orders_all: cursor paginator-handled ---
    ("kalshi.resources.fcm.FcmResource.orders_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- incentive_programs: `type` query param renamed to `incentive_type` ---
    # Same shadow-avoidance rationale as milestones / structured_targets.
    (
        "kalshi.resources.incentive_programs.IncentiveProgramsResource.list",
        "type",
    ): Exclusion(
        reason="SDK kwarg named incentive_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.incentive_programs.IncentiveProgramsResource.list",
        "incentive_type",
    ): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all",
        "type",
    ): Exclusion(
        reason="SDK kwarg named incentive_type (not type) to avoid built-in shadow",
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all",
        "incentive_type",
    ): Exclusion(
        reason=(
            "SDK renamed from spec's `type` query param to avoid shadowing "
            "the Python built-in; not query/path parity with spec (same wire "
            "key, different kwarg name)"
        ),
        kind="kwarg_rename",
    ),
    (
        "kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all",
        "cursor",
    ): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    # --- Response-side additive drift: spec fields the SDK intentionally omits ---
    # Consumed by TestSpecDrift / TestWsSpecDrift in addition to any request-side
    # body/param checks above that happen to share the same model+field key.
    # Each entry is a spec-documented deviation; flipping it to a hard fail
    # would surface as a real bug (see issue #157 stack for the v2.1.0
    # ``Balance.balance_dollars`` regression that motivated this PR).
    ("kalshi.models.markets.Market", "response_price_units"): Exclusion(
        reason="spec marks DEPRECATED; superseded by price_level_structure / price_ranges",
        kind="spec_deprecated",
    ),
    ("kalshi.models.orders.Order", "action"): Exclusion(
        reason="spec marks Deprecated; superseded by outcome_side / book_side",
        kind="spec_deprecated",
    ),
    ("kalshi.models.markets.Orderbook", "orderbook_fp"): Exclusion(
        reason=(
            "SDK reshapes the orderbook_fp nested object into yes/no level lists "
            "at the resource layer; the model itself holds the unwrapped lists"
        ),
        kind="wire_normalization",
    ),
    ("kalshi.ws.models.ticker.TickerPayload", "time"): Exclusion(
        reason="spec marks deprecated; superseded by ts_ms",
        kind="spec_deprecated",
    ),
    # --- server_omits_despite_required (#183, post-#172 nightly findings) ---
    # Fields the OpenAPI spec marks `required: true` but the live demo server
    # omits in practice. Each entry MUST cite a demo+prod observation in
    # `reason`. Until the spec is fixed upstream, the SDK keeps the field
    # optional so real-world responses parse cleanly.
    #
    # (`Event.product_metadata` lived here until v3.20.0 (#385) relaxed
    # `EventData.product_metadata` to optional upstream. Spec and SDK now
    # agree it is optional, so there is no deviation left to record — the
    # field stays `dict | None` and `test_parses_when_server_omits_product_metadata`
    # still guards the server-omission behavior.)
}


# --- max_pages: client-side cap on every public *_all() method (#98) ---
# Not a wire param — pure paginator safety knob. Every public *_all()
# accepts it; the kwarg legitimately exists in the signature.
_MAX_PAGES_FQNS: tuple[str, ...] = (
    "kalshi.resources.markets.MarketsResource.list_all",
    "kalshi.resources.markets.MarketsResource.list_trades_all",
    "kalshi.resources.markets.MarketsResource.list_all_trades",
    "kalshi.resources.communications.RFQsResource.list_all",
    "kalshi.resources.communications.QuotesResource.list_all",
    "kalshi.resources.milestones.MilestonesResource.list_all",
    "kalshi.resources.events.EventsResource.list_all",
    "kalshi.resources.events.EventsResource.list_all_multivariate",
    "kalshi.resources.events.EventsResource.fee_changes_all",
    "kalshi.resources.historical.HistoricalResource.markets_all",
    "kalshi.resources.historical.HistoricalResource.fills_all",
    "kalshi.resources.historical.HistoricalResource.orders_all",
    "kalshi.resources.historical.HistoricalResource.trades_all",
    "kalshi.resources.orders.OrdersResource.list_all",
    "kalshi.resources.orders.OrdersResource.fills_all",
    "kalshi.resources.communications.CommunicationsResource.list_all_rfqs",
    "kalshi.resources.communications.CommunicationsResource.list_all_quotes",
    "kalshi.resources.subaccounts.SubaccountsResource.list_all_transfers",
    "kalshi.resources.portfolio.PortfolioResource.settlements_all",
    "kalshi.resources.portfolio.PortfolioResource.deposits_all",
    "kalshi.resources.portfolio.PortfolioResource.withdrawals_all",
    "kalshi.resources.portfolio.PortfolioResource.positions_all",
    "kalshi.resources.portfolio.PortfolioResource.fills_all",
    "kalshi.resources.fcm.FcmResource.orders_all",
    "kalshi.resources.fcm.FcmResource.positions_all",
    "kalshi.resources.incentive_programs.IncentiveProgramsResource.list_all",
    "kalshi.resources.structured_targets.StructuredTargetsResource.list_all",
    "kalshi.resources.multivariate.MultivariateCollectionsResource.list_all",
    # Async counterparts — same kwarg, same client-only semantics.
    "kalshi.resources.markets.AsyncMarketsResource.list_all",
    "kalshi.resources.markets.AsyncMarketsResource.list_trades_all",
    "kalshi.resources.markets.AsyncMarketsResource.list_all_trades",
    "kalshi.resources.communications.AsyncRFQsResource.list_all",
    "kalshi.resources.communications.AsyncQuotesResource.list_all",
    "kalshi.resources.milestones.AsyncMilestonesResource.list_all",
    "kalshi.resources.events.AsyncEventsResource.list_all",
    "kalshi.resources.events.AsyncEventsResource.list_all_multivariate",
    "kalshi.resources.events.AsyncEventsResource.fee_changes_all",
    "kalshi.resources.historical.AsyncHistoricalResource.markets_all",
    "kalshi.resources.historical.AsyncHistoricalResource.fills_all",
    "kalshi.resources.historical.AsyncHistoricalResource.orders_all",
    "kalshi.resources.historical.AsyncHistoricalResource.trades_all",
    "kalshi.resources.orders.AsyncOrdersResource.list_all",
    "kalshi.resources.orders.AsyncOrdersResource.fills_all",
    "kalshi.resources.communications.AsyncCommunicationsResource.list_all_rfqs",
    "kalshi.resources.communications.AsyncCommunicationsResource.list_all_quotes",
    "kalshi.resources.subaccounts.AsyncSubaccountsResource.list_all_transfers",
    "kalshi.resources.portfolio.AsyncPortfolioResource.settlements_all",
    "kalshi.resources.portfolio.AsyncPortfolioResource.deposits_all",
    "kalshi.resources.portfolio.AsyncPortfolioResource.withdrawals_all",
    "kalshi.resources.portfolio.AsyncPortfolioResource.positions_all",
    "kalshi.resources.portfolio.AsyncPortfolioResource.fills_all",
    "kalshi.resources.fcm.AsyncFcmResource.orders_all",
    "kalshi.resources.fcm.AsyncFcmResource.positions_all",
    "kalshi.resources.incentive_programs.AsyncIncentiveProgramsResource.list_all",
    "kalshi.resources.structured_targets.AsyncStructuredTargetsResource.list_all",
    "kalshi.resources.multivariate.AsyncMultivariateCollectionsResource.list_all",
)
for _fqn in _MAX_PAGES_FQNS:
    EXCLUSIONS[(_fqn, "max_pages")] = Exclusion(
        reason="client-side max_pages cap on *_all() paginator; not a wire param (#98)",
        kind="client_only",
    )


# ════════════════════════════════════════════════════════════════════════════
# Perps (margin) API contract maps
#
# The perps API uses its own spec files: ``specs/perps_openapi.yaml`` (REST) and
# ``specs/perps_scm_openapi.yaml`` (the Self-Clearing-Member "Klear" surface).
# These parallel maps are consumed by the ``TestPerps*Drift`` classes in
# ``test_contracts.py`` and resolved against those specs instead of the
# prediction-API ``specs/openapi.yaml``. Keying each map to its own spec file
# sidesteps the schema-ref name collisions across specs (e.g. perps and core
# both define ``ApplySubaccountTransferRequest``).
#
# The foundation issue (#388) ships these empty-but-defined; each per-resource
# perps issue appends its entries.
# ════════════════════════════════════════════════════════════════════════════

# Perps REST endpoints — validated against ``specs/perps_openapi.yaml``.
PERPS_METHOD_ENDPOINT_MAP: list[MethodEndpointEntry] = [
    # ── perps exchange (#389) ────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.exchange.PerpsExchangeResource.status",
        http_method="GET",
        path_template="/margin/exchange/status",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.exchange.PerpsExchangeResource.enabled",
        http_method="GET",
        path_template="/margin/enabled",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.exchange.PerpsExchangeResource.risk_parameters",
        http_method="GET",
        path_template="/margin/risk_parameters",
    ),
    # ── perps markets (#390) ───────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.markets.PerpsMarketsResource.list",
        http_method="GET",
        path_template="/margin/markets",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.markets.PerpsMarketsResource.get",
        http_method="GET",
        path_template="/margin/markets/{ticker}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.markets.PerpsMarketsResource.orderbook",
        http_method="GET",
        path_template="/margin/markets/{ticker}/orderbook",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.markets.PerpsMarketsResource.candlesticks",
        http_method="GET",
        path_template="/margin/markets/{ticker}/candlesticks",
    ),
    # ── perps orders (#391) ────────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.create",
        http_method="POST",
        path_template="/margin/orders",
        request_body_schema="#/components/schemas/CreateMarginOrderRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.list",
        http_method="GET",
        path_template="/margin/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.list_all",
        http_method="GET",
        path_template="/margin/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.get",
        http_method="GET",
        path_template="/margin/orders/{order_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.cancel",
        http_method="DELETE",
        path_template="/margin/orders/{order_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.decrease",
        http_method="POST",
        path_template="/margin/orders/{order_id}/decrease",
        request_body_schema="#/components/schemas/DecreaseMarginOrderRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.amend",
        http_method="POST",
        path_template="/margin/orders/{order_id}/amend",
        request_body_schema="#/components/schemas/AmendMarginOrderRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.list_fcm",
        http_method="GET",
        path_template="/margin/fcm/orders",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.orders.MarginOrdersResource.list_all_fcm",
        http_method="GET",
        path_template="/margin/fcm/orders",
    ),
    # ── perps order_groups (#392) ──────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.list",
        http_method="GET",
        path_template="/margin/order_groups",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.create",
        http_method="POST",
        path_template="/margin/order_groups/create",
        request_body_schema="#/components/schemas/CreateOrderGroupRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.get",
        http_method="GET",
        path_template="/margin/order_groups/{order_group_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.delete",
        http_method="DELETE",
        path_template="/margin/order_groups/{order_group_id}",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.reset",
        http_method="PUT",
        path_template="/margin/order_groups/{order_group_id}/reset",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.trigger",
        http_method="PUT",
        path_template="/margin/order_groups/{order_group_id}/trigger",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.order_groups.OrderGroupsResource.update_limit",
        http_method="PUT",
        path_template="/margin/order_groups/{order_group_id}/limit",
        request_body_schema="#/components/schemas/UpdateOrderGroupLimitRequest",
    ),
    # ── perps portfolio (#393) ─────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.portfolio.PerpsPortfolioResource.positions",
        http_method="GET",
        path_template="/margin/positions",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.portfolio.PerpsPortfolioResource.fills",
        http_method="GET",
        path_template="/margin/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.portfolio.PerpsPortfolioResource.fills_all",
        http_method="GET",
        path_template="/margin/fills",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.portfolio.PerpsPortfolioResource.trades",
        http_method="GET",
        path_template="/margin/trades",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.portfolio.PerpsPortfolioResource.trades_all",
        http_method="GET",
        path_template="/margin/trades",
    ),
    # ── perps margin_account (#394) ────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.margin_account.MarginAccountResource.balance",
        http_method="GET",
        path_template="/margin/balance",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.margin_account.MarginAccountResource.risk",
        http_method="GET",
        path_template="/margin/risk",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.margin_account.MarginAccountResource.notional_risk_limit",
        http_method="GET",
        path_template="/margin/notional_risk_limit",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.margin_account.MarginAccountResource.fee_tiers",
        http_method="GET",
        path_template="/margin/fee_tiers",
    ),
    # ── perps funding (#395) ───────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.funding.FundingResource.rate_estimate",
        http_method="GET",
        path_template="/margin/funding_rates/estimate",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.funding.FundingResource.historical_rates",
        http_method="GET",
        path_template="/margin/funding_rates/historical",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.funding.FundingResource.history",
        http_method="GET",
        path_template="/margin/funding_history",
    ),
    # ── perps transfers (#396) ─────────────────────────────────────────
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.transfers.TransfersResource.transfer_instance",
        http_method="POST",
        path_template="/portfolio/intra_exchange_instance_transfer",
        request_body_schema="#/components/schemas/IntraExchangeInstanceTransferRequest",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.transfers.TransfersResource.create_subaccount",
        http_method="POST",
        path_template="/portfolio/margin/subaccounts",
    ),
    MethodEndpointEntry(
        sdk_method="kalshi.perps.resources.transfers.TransfersResource.transfer_subaccount",
        http_method="POST",
        path_template="/portfolio/margin/subaccounts/transfer",
        request_body_schema="#/components/schemas/ApplySubaccountTransferRequest",
    ),
]

# SCM/Klear endpoints — validated against ``specs/perps_scm_openapi.yaml``.
PERPS_SCM_METHOD_ENDPOINT_MAP: list[MethodEndpointEntry] = [
    # The SCM/Klear issues (#399/#400) append entries here, e.g.:
    # MethodEndpointEntry(
    #     sdk_method="kalshi.perps.klear.resources.auth.AuthResource.log_in",
    #     http_method="POST",
    #     path_template="/log_in",
    #     request_body_schema="#/components/schemas/LogInRequest",
    # ),
]

# Shared perps exclusion allowlist (same ``(sdk_fqn, field) → Exclusion`` shape
# as ``EXCLUSIONS``). Covers both the perps REST and SCM drift checks — FQNs are
# globally unique, so one map serves both. Dependent issues add their
# ``paginator_handled`` / ``client_only`` / ``wire_normalization`` entries here
# with a required ``reason``.
PERPS_EXCLUSIONS: dict[tuple[str, str], Exclusion] = {
    # ── perps orders (#391) ──
    ("kalshi.perps.resources.orders.MarginOrdersResource.list_all", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all",
        kind="paginator_handled",
    ),
    ("kalshi.perps.resources.orders.MarginOrdersResource.list_all_fcm", "cursor"): Exclusion(
        reason="paginator-handled; not a caller-facing kwarg on list_all_fcm",
        kind="paginator_handled",
    ),
    ("kalshi.perps.resources.orders.MarginOrdersResource.list_all", "max_pages"): Exclusion(
        reason="client-side paginator safety cap (#98); not a wire param",
        kind="client_only",
    ),
    ("kalshi.perps.resources.orders.MarginOrdersResource.list_all_fcm", "max_pages"): Exclusion(
        reason="client-side paginator safety cap (#98); not a wire param",
        kind="client_only",
    ),
    # ── perps order_groups (#392) ──
    ("kalshi.perps.models.order_groups.CreateOrderGroupRequest", "contracts_limit_fp"): Exclusion(
        reason=(
            "spec body offers a contracts_limit_fp FixedPointCount-string variant; "
            "the SDK emits the integer contracts_limit only (Kalshi accepts either). "
            "Mirrors the portfolio order-groups handling (#392)."
        ),
        kind="wire_normalization",
    ),
    (
        "kalshi.perps.models.order_groups.UpdateOrderGroupLimitRequest",
        "contracts_limit_fp",
    ): Exclusion(
        reason=(
            "contracts_limit_fp FixedPointCount-string variant on PUT /limit; "
            "the SDK emits the integer contracts_limit only (#392)."
        ),
        kind="wire_normalization",
    ),
    # ── perps portfolio (#393) ──
    ("kalshi.perps.resources.portfolio.PerpsPortfolioResource.fills_all", "cursor"): Exclusion(
        reason="cursor consumed by _list_all paginator, not a caller kwarg",
        kind="paginator_handled",
    ),
    ("kalshi.perps.resources.portfolio.PerpsPortfolioResource.fills_all", "max_pages"): Exclusion(
        reason="client-side page cap, no wire counterpart",
        kind="client_only",
    ),
    ("kalshi.perps.resources.portfolio.PerpsPortfolioResource.trades_all", "cursor"): Exclusion(
        reason="cursor consumed by _list_all paginator, not a caller kwarg",
        kind="paginator_handled",
    ),
    ("kalshi.perps.resources.portfolio.PerpsPortfolioResource.trades_all", "max_pages"): Exclusion(
        reason="client-side page cap, no wire counterpart",
        kind="client_only",
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
        raise ValueError(f"_resolve_ref only supports local refs starting with '#/', got {ref!r}")
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
        raise KeyError(f"operation {http_method!r} not defined on path {path_template!r}")

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

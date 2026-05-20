"""Builder helpers for response-model wire-shape dicts.

After #172 dropped the ``None`` defaults on ~226 spec-required fields, raw
inline dicts like ``{"ticker": "MKT-A"}`` no longer parse into ``Market`` /
``Order`` / ``Fill`` etc. without a long list of placeholder fields. These
builders return complete spec-shaped dicts that pass strict validation, with
``**overrides`` for callers that want to customize specific fields.

Each builder returns the **wire shape** (the JSON the server sends), not the
post-parse model. Pass the returned dict to ``Model.model_validate(...)``,
``respx``'s ``json=...``, ``RecordingTransport``, or test mock responses.

Usage:

    from tests._model_fixtures import market_dict, order_dict

    body = {"markets": [market_dict(ticker="A"), market_dict(ticker="B")]}
    json = order_dict(order_id="o1", yes_price_dollars="0.65")
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# REST response models
# ---------------------------------------------------------------------------


def market_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Market response dict with all required fields populated."""
    base: dict[str, Any] = {
        "ticker": "MKT-A",
        "event_ticker": "EVT-A",
        "market_type": "binary",
        "yes_sub_title": "Yes",
        "no_sub_title": "No",
        "status": "open",
        "yes_bid_dollars": "0.5000",
        "yes_ask_dollars": "0.5100",
        "no_bid_dollars": "0.4900",
        "no_ask_dollars": "0.5000",
        "last_price_dollars": "0.5000",
        "previous_yes_bid_dollars": "0.5000",
        "previous_yes_ask_dollars": "0.5100",
        "previous_price_dollars": "0.5000",
        "notional_value_dollars": "1.0000",
        "liquidity_dollars": "100.0000",
        "yes_bid_size_fp": "0.00",
        "yes_ask_size_fp": "0.00",
        "volume_fp": "0.00",
        "volume_24h_fp": "0.00",
        "open_interest_fp": "0.00",
        "created_time": "2026-01-01T00:00:00Z",
        "updated_time": "2026-01-01T00:00:00Z",
        "open_time": "2026-01-01T00:00:00Z",
        "close_time": "2026-12-31T23:59:59Z",
        "latest_expiration_time": "2026-12-31T23:59:59Z",
        "settlement_timer_seconds": 0,
        "result": "",
        "can_close_early": False,
        "fractional_trading_enabled": False,
        "expiration_value": "",
        "rules_primary": "Rules.",
        "rules_secondary": "",
        "price_level_structure": "binary",
        "price_ranges": [],
    }
    base.update(overrides)
    return base


def order_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Order response dict."""
    base: dict[str, Any] = {
        "order_id": "ord-1",
        "ticker": "MKT-A",
        "user_id": "user-1",
        "status": "resting",
        "side": "yes",
        "type": "limit",
        "yes_price_dollars": "0.5000",
        "no_price_dollars": "0.5000",
        "initial_count_fp": "10.00",
        "remaining_count_fp": "10.00",
        "fill_count_fp": "0.00",
        "taker_fill_cost_dollars": "0.0000",
        "maker_fill_cost_dollars": "0.0000",
        "taker_fees_dollars": "0.0000",
        "maker_fees_dollars": "0.0000",
        "client_order_id": "cli-1",
        "outcome_side": "yes",
        "book_side": "bid",
    }
    base.update(overrides)
    return base


def fill_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Fill response dict."""
    base: dict[str, Any] = {
        "trade_id": "trd-1",
        "fill_id": "fil-1",
        "order_id": "ord-1",
        "ticker": "MKT-A",
        "market_ticker": "MKT-A",
        "side": "yes",
        "action": "buy",
        "is_taker": True,
        "count_fp": "10.00",
        "yes_price_dollars": "0.5000",
        "no_price_dollars": "0.5000",
        "fee_cost_dollars": "0.0050",
        "outcome_side": "yes",
        "book_side": "bid",
    }
    base.update(overrides)
    return base


def trade_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Trade response dict (historical channel)."""
    base: dict[str, Any] = {
        "trade_id": "trd-1",
        "ticker": "MKT-A",
        "count_fp": "10.00",
        "yes_price_dollars": "0.5000",
        "no_price_dollars": "0.5000",
        "created_time": "2026-01-01T00:00:00Z",
        "taker_side": "yes",
        "taker_book_side": "bid",
        "taker_outcome_side": "yes",
    }
    base.update(overrides)
    return base


def event_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Event response dict."""
    base: dict[str, Any] = {
        "event_ticker": "EVT-A",
        "series_ticker": "SER-A",
        "title": "Event Title",
        "sub_title": "Event subtitle",
        "mutually_exclusive": False,
        "collateral_return_type": "self_collateralized",
        "available_on_brokers": False,
        "product_metadata": {},
    }
    base.update(overrides)
    return base


def event_metadata_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped EventMetadata dict."""
    base: dict[str, Any] = {
        "image_url": "",
        "market_details": [],
        "settlement_sources": [],
    }
    base.update(overrides)
    return base


def series_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Series response dict."""
    base: dict[str, Any] = {
        "ticker": "SER-A",
        "frequency": "weekly",
        "title": "Series title",
        "category": "Politics",
        "tags": [],
        "contract_url": "",
        "contract_terms_url": "",
        "fee_type": "quadratic",
        "fee_multiplier": 0.0,
        "additional_prohibitions": [],
        "settlement_sources": [],
    }
    base.update(overrides)
    return base


def settlement_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Settlement response dict."""
    base: dict[str, Any] = {
        "ticker": "MKT-A",
        "event_ticker": "EVT-A",
        "yes_count_fp": "0.00",
        "no_count_fp": "0.00",
        "yes_total_cost_dollars": "0.0000",
        "no_total_cost_dollars": "0.0000",
        "revenue": 0,
        "settled_time": "2026-01-01T00:00:00Z",
        "fee_cost_dollars": "0.0000",
        "market_result": "no",
    }
    base.update(overrides)
    return base


def market_position_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped MarketPosition response dict."""
    base: dict[str, Any] = {
        "ticker": "MKT-A",
        "total_traded_dollars": "0.0000",
        "position_fp": "0.00",
        "market_exposure_dollars": "0.0000",
        "realized_pnl_dollars": "0.0000",
        "resting_orders_count": 0,
        "fees_paid_dollars": "0.0000",
        "last_updated_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def event_position_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped EventPosition response dict."""
    base: dict[str, Any] = {
        "event_ticker": "EVT-A",
        "event_exposure_dollars": "0.0000",
        "total_cost_dollars": "0.0000",
        "realized_pnl_dollars": "0.0000",
        "total_cost_shares_fp": "0.00",
        "fees_paid_dollars": "0.0000",
    }
    base.update(overrides)
    return base


def multivariate_event_collection_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped MultivariateEventCollection response dict."""
    base: dict[str, Any] = {
        "collection_ticker": "COLL-A",
        "series_ticker": "SER-A",
        "title": "Collection title",
        "description": "Description.",
        "open_date": "2026-01-01T00:00:00Z",
        "close_date": "2026-12-31T23:59:59Z",
        "associated_events": [],
        "associated_event_tickers": [],
        "is_single_market_per_event": False,
        "is_all_yes": False,
        "is_ordered": False,
        "size_min": 0,
        "size_max": 0,
        "functional_description": "",
    }
    base.update(overrides)
    return base


def milestone_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Milestone response dict."""
    base: dict[str, Any] = {
        "id": "mile-1",
        "category": "sports",
        "type": "football_game",
        "start_date": "2026-01-01T00:00:00Z",
        "title": "Milestone title",
        "notification_message": "",
        "related_event_tickers": [],
        "details": {},
        "primary_event_tickers": [],
        "last_updated_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def incentive_program_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped IncentiveProgram response dict."""
    base: dict[str, Any] = {
        "id": "ip-1",
        "market_id": "mkt-1",
        "market_ticker": "MKT-A",
        "incentive_type": "liquidity",
        "start_date": "2026-01-01T00:00:00Z",
        "end_date": "2026-12-31T23:59:59Z",
        "period_reward": 0,
        "paid_out": False,
        "incentive_description": "",
    }
    base.update(overrides)
    return base


def api_key_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped ApiKey response dict."""
    base: dict[str, Any] = {
        "api_key_id": "key-1",
        "name": "My Key",
        "scopes": ["read"],
    }
    base.update(overrides)
    return base


def get_order_group_response_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped GetOrderGroupResponse dict."""
    base: dict[str, Any] = {
        "is_auto_cancel_enabled": False,
        "orders": [],
    }
    base.update(overrides)
    return base


def create_order_group_response_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped CreateOrderGroupResponse dict."""
    base: dict[str, Any] = {
        "order_group_id": "og-1",
        "subaccount": 0,
    }
    base.update(overrides)
    return base


def sport_filter_details_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped SportFilterDetails dict."""
    base: dict[str, Any] = {
        "competitions": {},
        "scopes": [],
    }
    base.update(overrides)
    return base


def scope_list_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped ScopeList dict."""
    base: dict[str, Any] = {
        "scopes": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


def create_order_request_kwargs(**overrides: Any) -> dict[str, Any]:
    """Kwargs for ``CreateOrderRequest(**)`` with all required fields.

    Pre-#172 ``action`` defaulted to ``"buy"``; tests now must pass it.
    """
    base: dict[str, Any] = {
        "ticker": "MKT-A",
        "side": "yes",
        "action": "buy",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# WebSocket payloads
# ---------------------------------------------------------------------------


def user_orders_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped UserOrdersPayload msg dict."""
    base: dict[str, Any] = {
        "order_id": "ord-1",
        "user_id": "user-1",
        "ticker": "MKT-A",
        "status": "resting",
        "side": "yes",
        "is_yes": True,
        "yes_price_dollars": "0.5000",
        "initial_count_fp": "10.00",
        "remaining_count_fp": "10.00",
        "fill_count_fp": "0.00",
        "taker_fill_cost_dollars": "0.0000",
        "maker_fill_cost_dollars": "0.0000",
        "taker_fees_dollars": "0.0000",
        "maker_fees_dollars": "0.0000",
        "client_order_id": "cli-1",
        "created_time": "2026-01-01T00:00:00Z",
        "outcome_side": "yes",
        "book_side": "bid",
        "created_ts_ms": 1735689600000,
    }
    base.update(overrides)
    return base


def fill_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped FillPayload msg dict."""
    base: dict[str, Any] = {
        "trade_id": "trd-1",
        "order_id": "ord-1",
        "market_ticker": "MKT-A",
        "is_taker": True,
        "side": "yes",
        "action": "buy",
        "count_fp": "10.00",
        "yes_price_dollars": "0.5000",
        "fee_cost": "0.0000",
        "ts": 1735689600,
        "ts_ms": 1735689600000,
        "post_position_fp": "10.00",
        "outcome_side": "yes",
        "book_side": "bid",
        "purchased_side": "yes",
    }
    base.update(overrides)
    return base


def ticker_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped TickerPayload msg dict."""
    base: dict[str, Any] = {
        "market_ticker": "MKT-A",
        "market_id": "mkt-1",
        "yes_bid_dollars": "0.5000",
        "yes_ask_dollars": "0.5100",
        "yes_bid_size_fp": "100.00",
        "yes_ask_size_fp": "100.00",
        "volume_fp": "0.00",
        "dollar_volume": "0",
        "open_interest_fp": "0.00",
        "dollar_open_interest": "0",
        "last_trade_size_fp": "0.00",
        "price_dollars": "0.5000",
        "ts": 1735689600,
        "ts_ms": 1735689600000,
    }
    base.update(overrides)
    return base


def trade_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped TradePayload msg dict."""
    base: dict[str, Any] = {
        "trade_id": "trd-1",
        "market_ticker": "MKT-A",
        "count_fp": "10.00",
        "yes_price_dollars": "0.5000",
        "no_price_dollars": "0.5000",
        "taker_side": "yes",
        "taker_book_side": "bid",
        "taker_outcome_side": "yes",
        "ts": 1735689600,
        "ts_ms": 1735689600000,
    }
    base.update(overrides)
    return base


def market_positions_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped MarketPositionsPayload msg dict."""
    base: dict[str, Any] = {
        "user_id": "user-1",
        "market_ticker": "MKT-A",
        "position_fp": "0.00",
        "volume_fp": "0.00",
        "realized_pnl_dollars": "0.0000",
        "fees_paid_dollars": "0.0000",
        "position_cost_dollars": "0.0000",
        "position_fee_cost_dollars": "0.0000",
    }
    base.update(overrides)
    return base


def rfq_created_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped RfqCreatedPayload msg dict."""
    base: dict[str, Any] = {
        "id": "rfq-1",
        "creator_id": "user-1",
        "market_ticker": "MKT-A",
        "created_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def rfq_deleted_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped RfqDeletedPayload msg dict."""
    base: dict[str, Any] = {
        "id": "rfq-1",
        "creator_id": "user-1",
        "market_ticker": "MKT-A",
        "deleted_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def quote_created_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped QuoteCreatedPayload msg dict."""
    base: dict[str, Any] = {
        "quote_id": "q-1",
        "rfq_id": "rfq-1",
        "quote_creator_id": "user-1",
        "market_ticker": "MKT-A",
        "yes_bid_dollars": "0.5000",
        "no_bid_dollars": "0.5000",
        "created_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def quote_accepted_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped QuoteAcceptedPayload msg dict."""
    base: dict[str, Any] = {
        "quote_id": "q-1",
        "rfq_id": "rfq-1",
        "quote_creator_id": "user-1",
        "market_ticker": "MKT-A",
        "yes_bid_dollars": "0.5000",
        "no_bid_dollars": "0.5000",
    }
    base.update(overrides)
    return base


def quote_executed_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped QuoteExecutedPayload msg dict."""
    base: dict[str, Any] = {
        "quote_id": "q-1",
        "rfq_id": "rfq-1",
        "quote_creator_id": "user-1",
        "rfq_creator_id": "user-2",
        "order_id": "ord-1",
        "client_order_id": "cli-1",
        "market_ticker": "MKT-A",
        "executed_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def multivariate_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped MultivariatePayload msg dict."""
    base: dict[str, Any] = {
        "collection_ticker": "COLL-A",
        "selected_markets": [],
        "market_ticker": "MKT-A",
        "event_ticker": "EVT-A",
    }
    base.update(overrides)
    return base


def market_lifecycle_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped MarketLifecyclePayload msg dict.

    `event_type` and `market_ticker` are required; all per-event_type
    conditional fields are left out (override per test).
    """
    base: dict[str, Any] = {
        "event_type": "created",
        "market_ticker": "MKT-A",
    }
    base.update(overrides)
    return base


def order_group_payload_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped OrderGroupPayload msg dict."""
    base: dict[str, Any] = {
        "event_type": "created",
        "order_group_id": "og-1",
        "ts_ms": 1735689600000,
    }
    base.update(overrides)
    return base


def series_fee_change_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped SeriesFeeChange response dict."""
    base: dict[str, Any] = {
        "id": "sfc-1",
        "series_ticker": "SER-A",
        "fee_type": "quadratic",
        "fee_multiplier": 0.0,
        "scheduled_ts": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def bid_ask_distribution_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped BidAskDistribution dict (Candlestick.yes_bid / .yes_ask)."""
    base: dict[str, Any] = {
        "open_dollars": "0.5000",
        "high_dollars": "0.5100",
        "low_dollars": "0.4900",
        "close_dollars": "0.5000",
    }
    base.update(overrides)
    return base


def price_distribution_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped PriceDistribution dict (Candlestick.price).

    All fields are optional per spec — the OHLC window may contain no
    trades — so the default base is intentionally ``{}``. Pass overrides
    when the test exercises specific fields.
    """
    base: dict[str, Any] = {}
    base.update(overrides)
    return base


def candlestick_dict(**overrides: Any) -> dict[str, Any]:
    """Spec-shaped Candlestick dict (#171)."""
    base: dict[str, Any] = {
        "end_period_ts": 1700000000,
        "yes_bid": bid_ask_distribution_dict(),
        "yes_ask": bid_ask_distribution_dict(),
        "price": price_distribution_dict(),
        "volume_fp": "0.00",
        "open_interest_fp": "0.00",
    }
    base.update(overrides)
    return base

"""Regression tests for the multi-LLM review fixes on the perps branch.

Covers the confirmed-real findings fixed in one pass:

- ``GetMarginOrdersResponse.cursor`` optional (final-page pagination crash).
- ``count`` / ``reduce_by`` positive constraints (``reduce_to`` allows 0).
- ``transfer_instance`` shard-kwarg exclusivity (silently-ignored routing arg).
- Partial-credential fail-fast on ``PerpsClient`` / ``AsyncPerpsClient``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kalshi.perps import AsyncPerpsClient, PerpsClient, PerpsConfig
from kalshi.perps.models.orders import (
    AmendMarginOrderRequest,
    CreateMarginOrderRequest,
    DecreaseMarginOrderRequest,
    GetMarginOrdersResponse,
)
from kalshi.perps.models.transfers import IntraExchangeInstanceTransferRequest
from kalshi.perps.resources.transfers import _build_instance_transfer_body

# ── GetMarginOrdersResponse.cursor optional ──────────────────────────────────


class TestCursorOptional:
    def test_parses_when_server_omits_cursor_on_final_page(self) -> None:
        # Kalshi drops the cursor key on the last page; a bare ``str`` would crash.
        resp = GetMarginOrdersResponse.model_validate({"orders": []})
        assert resp.cursor is None

    def test_parses_present_cursor(self) -> None:
        resp = GetMarginOrdersResponse.model_validate({"orders": [], "cursor": "abc"})
        assert resp.cursor == "abc"


# ── positive-size constraints ────────────────────────────────────────────────


class TestOrderSizeConstraints:
    def test_create_rejects_zero_count(self) -> None:
        with pytest.raises(ValidationError):
            CreateMarginOrderRequest(
                ticker="BTC-PERP",
                client_order_id="c1",
                side="bid",
                count=0,
                price="0.50",
                time_in_force="good_till_canceled",
                self_trade_prevention_type="maker",
            )

    def test_amend_rejects_zero_count(self) -> None:
        with pytest.raises(ValidationError):
            AmendMarginOrderRequest(ticker="BTC-PERP", side="bid", price="0.50", count=0)

    def test_decrease_rejects_zero_reduce_by(self) -> None:
        with pytest.raises(ValidationError):
            DecreaseMarginOrderRequest(reduce_by=0)

    def test_decrease_rejects_negative_reduce_by(self) -> None:
        with pytest.raises(ValidationError):
            DecreaseMarginOrderRequest(reduce_by=-1)

    def test_decrease_rejects_negative_reduce_to(self) -> None:
        with pytest.raises(ValidationError):
            DecreaseMarginOrderRequest(reduce_to=-1)

    def test_decrease_allows_zero_reduce_to(self) -> None:
        # reduce_to is a target remaining count — 0 (decrease to nothing) is valid.
        req = DecreaseMarginOrderRequest(reduce_to=0)
        assert req.reduce_to == 0


# ── transfer_instance shard-kwarg exclusivity ────────────────────────────────


class TestTransferShardExclusivity:
    def _req(self) -> IntraExchangeInstanceTransferRequest:
        return IntraExchangeInstanceTransferRequest(
            source="event_contract", destination="margined", amount=100
        )

    def test_request_plus_source_shard_raises(self) -> None:
        with pytest.raises(TypeError):
            _build_instance_transfer_body(
                self._req(),
                source=None,
                destination=None,
                amount=None,
                source_exchange_shard=5,
                destination_exchange_shard=None,
            )

    def test_request_plus_destination_shard_raises(self) -> None:
        with pytest.raises(TypeError):
            _build_instance_transfer_body(
                self._req(),
                source=None,
                destination=None,
                amount=None,
                source_exchange_shard=None,
                destination_exchange_shard=2,
            )

    def test_kwargs_path_defaults_shards_to_zero(self) -> None:
        body = _build_instance_transfer_body(
            None,
            source="event_contract",
            destination="margined",
            amount=100,
            source_exchange_shard=None,
            destination_exchange_shard=None,
        )
        assert body["source_exchange_shard"] == 0
        assert body["destination_exchange_shard"] == 0


# ── partial-credential fail-fast ─────────────────────────────────────────────


class TestPartialAuthFailFast:
    def test_sync_key_id_without_key_material_raises(self) -> None:
        with pytest.raises(ValueError, match="Incomplete credentials"):
            PerpsClient(key_id="k", config=PerpsConfig.demo())

    def test_sync_private_key_without_key_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Incomplete credentials"):
            PerpsClient(private_key="pem", config=PerpsConfig.demo())

    def test_sync_private_key_path_without_key_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Incomplete credentials"):
            PerpsClient(private_key_path="/tmp/x.pem", config=PerpsConfig.demo())

    def test_async_key_id_without_key_material_raises(self) -> None:
        with pytest.raises(ValueError, match="Incomplete credentials"):
            AsyncPerpsClient(key_id="k", config=PerpsConfig.demo())

    def test_async_private_key_without_key_id_raises(self) -> None:
        with pytest.raises(ValueError, match="Incomplete credentials"):
            AsyncPerpsClient(private_key="pem", config=PerpsConfig.demo())

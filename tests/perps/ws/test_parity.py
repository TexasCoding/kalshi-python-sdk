"""AsyncAPI WS command/response parity test for the perps margin WebSocket.

The WS analog of the REST drift test: loads ``specs/perps_asyncapi.yaml`` and
asserts every command/response message has a corresponding model in
``kalshi/perps/ws/models/control.py`` whose ``cmd`` (commands) / ``type``
(responses) ``Literal`` matches the spec const.

The ``listSubscriptionsResponsePayload`` / ``okResponsePayload`` collision
(both ``type: "ok"``) is NOT excluded — it is disambiguated by ``msg`` shape
(array vs object), which the test verifies directly via
``PerpsMessageDispatcher.classify_ok`` rather than skipping.
"""

from __future__ import annotations

import typing
from pathlib import Path
from typing import Literal

import yaml

from kalshi.perps.ws.dispatch import classify_ok
from kalshi.perps.ws.models.control import (
    ListSubscriptionsCommand,
    ListSubscriptionsResponse,
    OkResponse,
    PerpsErrorResponse,
    SubscribeCommand,
    SubscribedResponse,
    UnsubscribeCommand,
    UnsubscribedResponse,
    UpdateSubscriptionCommand,
)

_SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "perps_asyncapi.yaml"


def _load_spec() -> dict:
    with _SPEC_PATH.open() as f:
        return yaml.safe_load(f)


def _const_of(spec: dict, schema_name: str, field: str) -> str:
    """Return the ``const`` declared on ``schema_name.properties[field]``."""
    schema = spec["components"]["schemas"][schema_name]
    return schema["properties"][field]["const"]


def _literal_value(model: type, field: str) -> str:
    """Return the single allowed value of a ``Literal`` field on a model."""
    hints = typing.get_type_hints(model)
    ann = hints[field]
    args = typing.get_args(ann)
    assert args, f"{model.__name__}.{field} is not a Literal"
    assert len(args) == 1, f"{model.__name__}.{field} Literal must be single-valued"
    return args[0]


# Map spec payload schema -> (SDK model, const-field, command-or-response).
# updateSubscription{,Delete,SingleSid}Command all share updateSubscriptionCommandPayload.
_COMMAND_MAP = {
    "subscribeCommandPayload": (SubscribeCommand, "cmd"),
    "unsubscribeCommandPayload": (UnsubscribeCommand, "cmd"),
    "updateSubscriptionCommandPayload": (UpdateSubscriptionCommand, "cmd"),
    "listSubscriptionsCommandPayload": (ListSubscriptionsCommand, "cmd"),
}
_RESPONSE_MAP = {
    "subscribedResponsePayload": (SubscribedResponse, "type"),
    "unsubscribedResponsePayload": (UnsubscribedResponse, "type"),
    "okResponsePayload": (OkResponse, "type"),
    "listSubscriptionsResponsePayload": (ListSubscriptionsResponse, "type"),
    "errorResponsePayload": (PerpsErrorResponse, "type"),
}


class TestCommandParity:
    def test_every_command_schema_has_a_model(self) -> None:
        spec = _load_spec()
        schemas = spec["components"]["schemas"]
        command_schemas = {
            name for name in schemas if name.endswith("CommandPayload")
        }
        assert command_schemas == set(_COMMAND_MAP), (
            "Command payload schemas in the spec do not match the mapped models: "
            f"spec={sorted(command_schemas)} mapped={sorted(_COMMAND_MAP)}"
        )

    def test_command_cmd_consts_match(self) -> None:
        spec = _load_spec()
        for schema_name, (model, field) in _COMMAND_MAP.items():
            spec_const = _const_of(spec, schema_name, field)
            model_const = _literal_value(model, field)
            assert model_const == spec_const, (
                f"{model.__name__}.{field}={model_const!r} != "
                f"spec {schema_name}.{field}={spec_const!r}"
            )


class TestResponseParity:
    def test_every_response_schema_has_a_model(self) -> None:
        spec = _load_spec()
        schemas = spec["components"]["schemas"]
        response_schemas = {
            name for name in schemas if name.endswith("ResponsePayload")
        }
        assert response_schemas == set(_RESPONSE_MAP), (
            "Response payload schemas in the spec do not match the mapped models: "
            f"spec={sorted(response_schemas)} mapped={sorted(_RESPONSE_MAP)}"
        )

    def test_response_type_consts_match(self) -> None:
        spec = _load_spec()
        for schema_name, (model, field) in _RESPONSE_MAP.items():
            spec_const = _const_of(spec, schema_name, field)
            model_const = _literal_value(model, field)
            assert model_const == spec_const, (
                f"{model.__name__}.{field}={model_const!r} != "
                f"spec {schema_name}.{field}={spec_const!r}"
            )

    def test_ok_collision_disambiguated_by_msg_shape(self) -> None:
        """Both okResponsePayload and listSubscriptionsResponsePayload are type:"ok".

        The spec disambiguates by ``msg`` being an object (update ack) vs an
        array (list_subscriptions). Assert both share the const AND that the
        framing layer branches on ``msg`` shape.
        """
        spec = _load_spec()
        assert _const_of(spec, "okResponsePayload", "type") == "ok"
        assert _const_of(spec, "listSubscriptionsResponsePayload", "type") == "ok"
        # update ack -> object msg
        assert classify_ok({"type": "ok", "id": 1, "msg": {"market_tickers": []}}) == "update_ack"
        assert classify_ok({"type": "ok", "id": 1}) == "update_ack"
        # list_subscriptions -> array msg
        assert classify_ok({"type": "ok", "id": 1, "msg": []}) == "list_subscriptions"
        assert classify_ok(
            {"type": "ok", "id": 1, "msg": [{"channel": "ticker", "sid": 3}]}
        ) == "list_subscriptions"


class TestEnumParity:
    def test_channels_enum_matches_spec(self) -> None:
        from kalshi.perps.ws.models.control import PerpsChannel

        spec = _load_spec()
        spec_channels = set(
            spec["components"]["schemas"]["subscribeCommandPayload"]["properties"][
                "params"
            ]["properties"]["channels"]["items"]["enum"]
        )
        assert {c.value for c in PerpsChannel} == spec_channels

    def test_action_enum_matches_spec(self) -> None:
        from kalshi.perps.ws.models.control import UpdateSubscriptionAction

        spec = _load_spec()
        spec_actions = set(
            spec["components"]["schemas"]["updateSubscriptionCommandPayload"][
                "properties"
            ]["params"]["properties"]["action"]["enum"]
        )
        assert {a.value for a in UpdateSubscriptionAction} == spec_actions

    def test_book_side_enum_matches_spec(self) -> None:
        from kalshi.perps.ws.models.control import PerpsBookSide

        spec = _load_spec()
        spec_sides = set(spec["components"]["schemas"]["bookSide"]["enum"])
        assert {s.value for s in PerpsBookSide} == spec_sides


class TestSequencedChannels:
    def test_perps_sequenced_channels(self) -> None:
        from kalshi.perps.ws.sequence import PERPS_SEQUENCED_CHANNELS

        assert {
            "orderbook_delta",
            "orderbook_snapshot",
            "order_group_updates",
        } == PERPS_SEQUENCED_CHANNELS


def test_literal_imported_for_type_hints() -> None:
    # Guard: get_type_hints needs Literal in scope. Importing it here ensures
    # the parity helpers resolve forward refs even under `from __future__`.
    assert Literal is not None

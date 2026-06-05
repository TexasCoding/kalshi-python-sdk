"""Tests for perps WS control models — forbid on commands, envelope round-trips."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kalshi.perps.ws.models.control import (
    ListSubscriptionsResponse,
    OkResponse,
    PerpsErrorResponse,
    SubscribeCommand,
    SubscribedResponse,
    SubscribeParams,
    SubscriptionEntry,
    UnsubscribedResponse,
    UnsubscribeParams,
    UpdateSubscriptionAction,
    UpdateSubscriptionParams,
)


class TestCommandForbid:
    def test_subscribe_params_rejects_unknown_key(self) -> None:
        with pytest.raises(ValidationError):
            SubscribeParams(channels=["ticker"], bogus=1)  # type: ignore[call-arg]

    def test_unsubscribe_params_rejects_unknown_key(self) -> None:
        with pytest.raises(ValidationError):
            UnsubscribeParams(sids=[1], extra=2)  # type: ignore[call-arg]

    def test_update_params_rejects_unknown_key(self) -> None:
        with pytest.raises(ValidationError):
            UpdateSubscriptionParams(  # type: ignore[call-arg]
                action=UpdateSubscriptionAction.ADD_MARKETS, bogus=1
            )

    def test_subscribe_command_serializes_with_aliases(self) -> None:
        cmd = SubscribeCommand(
            id=1, params=SubscribeParams(channels=["ticker"], market_tickers=["X"])
        )
        out = cmd.model_dump(exclude_none=True, by_alias=True, mode="json")
        assert out == {
            "id": 1,
            "cmd": "subscribe",
            "params": {"channels": ["ticker"], "market_tickers": ["X"]},
        }


class TestResponseRoundTrip:
    def test_subscribed_response(self) -> None:
        m = SubscribedResponse.model_validate(
            {"id": 1, "type": "subscribed", "msg": {"channel": "ticker", "sid": 5}}
        )
        assert m.msg.channel == "ticker"
        assert m.msg.sid == 5

    def test_unsubscribed_response_top_level_sid_seq(self) -> None:
        m = UnsubscribedResponse.model_validate(
            {"id": 1, "sid": 5, "seq": 9, "type": "unsubscribed"}
        )
        assert m.sid == 5 and m.seq == 9

    def test_ok_response_object_msg(self) -> None:
        m = OkResponse.model_validate(
            {"id": 1, "sid": 5, "type": "ok", "msg": {"market_tickers": ["X", "Y"]}}
        )
        assert m.msg is not None
        assert m.msg.market_tickers == ["X", "Y"]

    def test_ok_response_without_msg(self) -> None:
        m = OkResponse.model_validate({"id": 1, "type": "ok"})
        assert m.msg is None

    def test_list_subscriptions_response_array_msg(self) -> None:
        m = ListSubscriptionsResponse.model_validate(
            {
                "id": 1,
                "type": "ok",
                "msg": [
                    {"channel": "ticker", "sid": 3},
                    {"channel": "trade", "sid": 4},
                ],
            }
        )
        assert [e.sid for e in m.msg] == [3, 4]
        assert all(isinstance(e, SubscriptionEntry) for e in m.msg)

    def test_error_response(self) -> None:
        m = PerpsErrorResponse.model_validate(
            {"id": 1, "type": "error", "msg": {"code": 6, "msg": "nope"}}
        )
        assert m.msg.code == 6
        assert m.msg.msg == "nope"

    def test_ok_array_vs_object_disambiguation(self) -> None:
        # Same type:"ok" frame validates against the right model based on msg shape.
        array_frame = {"id": 1, "type": "ok", "msg": [{"channel": "t", "sid": 1}]}
        object_frame = {"id": 1, "type": "ok", "msg": {"market_tickers": []}}
        # Array msg parses as ListSubscriptionsResponse, object as OkResponse.
        assert ListSubscriptionsResponse.model_validate(array_frame).msg[0].sid == 1
        assert OkResponse.model_validate(object_frame).msg is not None

"""Tests for kalshi.resources.live_data."""

from __future__ import annotations

import httpx
import pytest
import respx

from kalshi._base_client import AsyncTransport, SyncTransport
from kalshi.auth import KalshiAuth
from kalshi.config import KalshiConfig
from kalshi.errors import KalshiNotFoundError
from kalshi.models.live_data import (
    GetGameStatsResponse,
    LiveData,
)
from kalshi.resources.live_data import AsyncLiveDataResource, LiveDataResource


@pytest.fixture
def config() -> KalshiConfig:
    return KalshiConfig(
        base_url="https://test.kalshi.com/trade-api/v2",
        timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def live_data(test_auth: KalshiAuth, config: KalshiConfig) -> LiveDataResource:
    return LiveDataResource(SyncTransport(test_auth, config))


@pytest.fixture
def async_live_data(
    test_auth: KalshiAuth, config: KalshiConfig,
) -> AsyncLiveDataResource:
    return AsyncLiveDataResource(AsyncTransport(test_auth, config))


_LD_JSON = {
    "type": "football_game",
    "milestone_id": "ms-1",
    "details": {
        "score": {"home": 14, "away": 7},
        "clock": "10:32",
        "period": "Q2",
    },
}


class TestLiveDataModels:
    def test_live_data_parses(self) -> None:
        ld = LiveData.model_validate(_LD_JSON)
        assert ld.type == "football_game"
        assert ld.milestone_id == "ms-1"
        assert ld.details["score"]["home"] == 14

    def test_game_stats_response_handles_null_pbp(self) -> None:
        resp = GetGameStatsResponse.model_validate({"pbp": None})
        assert resp.pbp is None

    def test_game_stats_response_handles_missing_pbp(self) -> None:
        resp = GetGameStatsResponse.model_validate({})
        assert resp.pbp is None

    def test_game_stats_response_parses_periods(self) -> None:
        resp = GetGameStatsResponse.model_validate({
            "pbp": {"periods": [{"events": [{"kind": "touchdown"}]}]},
        })
        assert resp.pbp is not None
        assert len(resp.pbp.periods) == 1
        assert resp.pbp.periods[0].events[0]["kind"] == "touchdown"


class TestLiveDataGet:
    @respx.mock
    def test_get_unwraps(self, live_data: LiveDataResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1",
        ).mock(return_value=httpx.Response(200, json={"live_data": _LD_JSON}))
        ld = live_data.get("ms-1")
        assert isinstance(ld, LiveData)
        assert ld.milestone_id == "ms-1"

    @respx.mock
    def test_get_with_player_stats_flag(
        self, live_data: LiveDataResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1",
        ).mock(return_value=httpx.Response(200, json={"live_data": _LD_JSON}))
        live_data.get("ms-1", include_player_stats=True)
        q = dict(route.calls[0].request.url.params)
        assert q["include_player_stats"] == "true"

    @respx.mock
    def test_get_omits_flag_when_false(
        self, live_data: LiveDataResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1",
        ).mock(return_value=httpx.Response(200, json={"live_data": _LD_JSON}))
        live_data.get("ms-1", include_player_stats=False)
        # False and None both drop the kwarg — spec default is false so omitting is OK.
        assert "include_player_stats" not in dict(route.calls[0].request.url.params)

    @respx.mock
    def test_get_404_maps(self, live_data: LiveDataResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/nope",
        ).mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(KalshiNotFoundError):
            live_data.get("nope")


class TestLiveDataGetTyped:
    @respx.mock
    def test_get_typed_sends_type_path(
        self, live_data: LiveDataResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/football_game/milestone/ms-1",
        ).mock(return_value=httpx.Response(200, json={"live_data": _LD_JSON}))
        ld = live_data.get_typed("football_game", "ms-1")
        assert ld.milestone_id == "ms-1"
        assert route.called


class TestLiveDataBatch:
    @respx.mock
    def test_batch_explodes_milestone_ids(
        self, live_data: LiveDataResource,
    ) -> None:
        route = respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/batch",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"live_datas": [
                    _LD_JSON,
                    {**_LD_JSON, "milestone_id": "ms-2"},
                ]},
            ),
        )
        items = live_data.batch(milestone_ids=["ms-1", "ms-2"])
        assert len(items) == 2
        assert items[1].milestone_id == "ms-2"
        # httpx explodes list values — each id sent as a separate param.
        raw_query = str(route.calls[0].request.url.query)
        assert "milestone_ids=ms-1" in raw_query
        assert "milestone_ids=ms-2" in raw_query

    @respx.mock
    def test_batch_empty_result(self, live_data: LiveDataResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/batch",
        ).mock(return_value=httpx.Response(200, json={"live_datas": []}))
        items = live_data.batch(milestone_ids=["nope"])
        assert items == []


class TestLiveDataGameStats:
    @respx.mock
    def test_game_stats_unsupported_returns_none_pbp(
        self, live_data: LiveDataResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1/game_stats",
        ).mock(return_value=httpx.Response(200, json={"pbp": None}))
        resp = live_data.game_stats("ms-1")
        assert resp.pbp is None

    @respx.mock
    def test_game_stats_with_data(self, live_data: LiveDataResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1/game_stats",
        ).mock(
            return_value=httpx.Response(
                200,
                json={"pbp": {"periods": [{"events": [{"kind": "fg"}]}]}},
            ),
        )
        resp = live_data.game_stats("ms-1")
        assert resp.pbp is not None
        assert resp.pbp.periods[0].events[0]["kind"] == "fg"


class TestAsyncLiveData:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get(self, async_live_data: AsyncLiveDataResource) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1",
        ).mock(return_value=httpx.Response(200, json={"live_data": _LD_JSON}))
        ld = await async_live_data.get("ms-1")
        assert ld.milestone_id == "ms-1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_batch(
        self, async_live_data: AsyncLiveDataResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/batch",
        ).mock(
            return_value=httpx.Response(
                200, json={"live_datas": [_LD_JSON]},
            ),
        )
        items = await async_live_data.batch(milestone_ids=["ms-1"])
        assert len(items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_game_stats(
        self, async_live_data: AsyncLiveDataResource,
    ) -> None:
        respx.get(
            "https://test.kalshi.com/trade-api/v2/live_data/milestone/ms-1/game_stats",
        ).mock(return_value=httpx.Response(200, json={"pbp": None}))
        resp = await async_live_data.game_stats("ms-1")
        assert resp.pbp is None

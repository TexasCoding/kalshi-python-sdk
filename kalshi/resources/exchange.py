"""Exchange resource — status, schedule, announcements."""

from __future__ import annotations

import builtins

from kalshi.models.exchange import Announcement, ExchangeStatus, Schedule
from kalshi.resources._base import AsyncResource, SyncResource


class ExchangeResource(SyncResource):
    """Sync exchange API."""

    def status(self) -> ExchangeStatus:
        data = self._get("/exchange/status")
        return ExchangeStatus.model_validate(data)

    def schedule(self) -> Schedule:
        data = self._get("/exchange/schedule")
        raw = data.get("schedule", data)
        return Schedule.model_validate(raw)

    def announcements(self) -> builtins.list[Announcement]:
        data = self._get("/exchange/announcements")
        raw = data.get("announcements", [])
        return [Announcement.model_validate(a) for a in raw]


class AsyncExchangeResource(AsyncResource):
    """Async exchange API."""

    async def status(self) -> ExchangeStatus:
        data = await self._get("/exchange/status")
        return ExchangeStatus.model_validate(data)

    async def schedule(self) -> Schedule:
        data = await self._get("/exchange/schedule")
        raw = data.get("schedule", data)
        return Schedule.model_validate(raw)

    async def announcements(self) -> builtins.list[Announcement]:
        data = await self._get("/exchange/announcements")
        raw = data.get("announcements", [])
        return [Announcement.model_validate(a) for a in raw]

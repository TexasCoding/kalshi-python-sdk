"""Exchange-related models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from kalshi.types import NullableList


class ExchangeStatus(BaseModel):
    """Current exchange operational status."""

    exchange_active: bool
    trading_active: bool
    exchange_estimated_resume_time: datetime | None = None

    model_config = {"extra": "allow"}


class DailySchedule(BaseModel):
    """A single trading session within a day."""

    open_time: str  # "HH:MM" in ET
    close_time: str  # "HH:MM" in ET

    model_config = {"extra": "allow"}


class WeeklySchedule(BaseModel):
    """Weekly trading hours with per-day sessions."""

    start_time: datetime
    end_time: datetime
    monday: NullableList[DailySchedule] = []
    tuesday: NullableList[DailySchedule] = []
    wednesday: NullableList[DailySchedule] = []
    thursday: NullableList[DailySchedule] = []
    friday: NullableList[DailySchedule] = []
    saturday: NullableList[DailySchedule] = []
    sunday: NullableList[DailySchedule] = []

    model_config = {"extra": "allow"}


class MaintenanceWindow(BaseModel):
    """A scheduled maintenance window."""

    start_datetime: datetime
    end_datetime: datetime

    model_config = {"extra": "allow"}


class Schedule(BaseModel):
    """Exchange operating schedule."""

    standard_hours: NullableList[WeeklySchedule] = []
    maintenance_windows: NullableList[MaintenanceWindow] = []

    model_config = {"extra": "allow"}


class Announcement(BaseModel):
    """An exchange-wide announcement."""

    type: str  # "info" | "warning" | "error"
    message: str
    delivery_time: datetime
    status: str  # "active" | "inactive"

    model_config = {"extra": "allow"}

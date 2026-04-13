"""Exchange-related models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
    monday: list[DailySchedule] = []
    tuesday: list[DailySchedule] = []
    wednesday: list[DailySchedule] = []
    thursday: list[DailySchedule] = []
    friday: list[DailySchedule] = []
    saturday: list[DailySchedule] = []
    sunday: list[DailySchedule] = []

    model_config = {"extra": "allow"}


class MaintenanceWindow(BaseModel):
    """A scheduled maintenance window."""

    start_datetime: datetime
    end_datetime: datetime

    model_config = {"extra": "allow"}


class Schedule(BaseModel):
    """Exchange operating schedule."""

    standard_hours: list[WeeklySchedule] = []
    maintenance_windows: list[MaintenanceWindow] = []

    model_config = {"extra": "allow"}


class Announcement(BaseModel):
    """An exchange-wide announcement."""

    type: str  # "info" | "warning" | "error"
    message: str
    delivery_time: datetime
    status: str  # "active" | "inactive"

    model_config = {"extra": "allow"}

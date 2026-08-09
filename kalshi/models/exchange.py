"""Exchange-related models."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel

from kalshi.types import NullableList


class ExchangeIndexStatus(BaseModel):
    """Operational status of a single exchange index (shard)."""

    exchange_index: int
    description: str
    exchange_active: bool
    trading_active: bool
    intra_exchange_transfers_active: bool

    model_config = {"extra": "allow"}


class ExchangeStatus(BaseModel):
    """Current exchange operational status."""

    exchange_active: bool
    trading_active: bool
    intra_exchange_transfers_active: bool | None = None
    exchange_estimated_resume_time: AwareDatetime | None = None
    exchange_index_statuses: NullableList[ExchangeIndexStatus] = []

    model_config = {"extra": "allow"}


class DailySchedule(BaseModel):
    """A single trading session within a day."""

    open_time: str  # "HH:MM" in ET
    close_time: str  # "HH:MM" in ET

    model_config = {"extra": "allow"}


class WeeklySchedule(BaseModel):
    """Weekly trading hours with per-day sessions."""

    start_time: AwareDatetime
    end_time: AwareDatetime
    monday: NullableList[DailySchedule]
    tuesday: NullableList[DailySchedule]
    wednesday: NullableList[DailySchedule]
    thursday: NullableList[DailySchedule]
    friday: NullableList[DailySchedule]
    saturday: NullableList[DailySchedule]
    sunday: NullableList[DailySchedule]

    model_config = {"extra": "allow"}


class MaintenanceWindow(BaseModel):
    """A scheduled maintenance window."""

    start_datetime: AwareDatetime
    end_datetime: AwareDatetime

    model_config = {"extra": "allow"}


class Schedule(BaseModel):
    """Exchange operating schedule."""

    standard_hours: NullableList[WeeklySchedule]
    maintenance_windows: NullableList[MaintenanceWindow]

    model_config = {"extra": "allow"}


class Announcement(BaseModel):
    """An exchange-wide announcement."""

    type: str  # "info" | "warning" | "error"
    message: str
    delivery_time: AwareDatetime
    status: str  # "active" | "inactive"

    model_config = {"extra": "allow"}


class UserDataTimestamp(BaseModel):
    """Timestamp when user-scoped exchange data was last validated.

    Combine with WebSocket feeds for a live view — REST endpoints like
    GetBalance/GetOrders/GetFills/GetPositions may lag the exchange by
    a short delay; ``as_of_time`` is the upper bound on that lag.
    """

    as_of_time: AwareDatetime

    model_config = {"extra": "allow"}

"""CF Benchmarks value channel message models (``cfbenchmarks_value``).

The auth-required ``cfbenchmarks_value`` channel streams CF Benchmarks reference
index values (e.g. ``BRTI``) keyed by ``index_id``, each carrying the raw upstream
frame plus a trailing 60-second average and — only in the final minute before a
quarter-hour close — a quarter-hour windowed average. The ``indexlist`` action
yields a separate ``cfbenchmarks_value_indexlist`` message listing available IDs.

Two inbound message types arrive on the same subscription (both carry ``sid``):
``cfbenchmarks_value`` (data) and ``cfbenchmarks_value_indexlist`` (the response
to an ``indexlist`` ``update_subscription`` action).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from kalshi.types import DollarDecimal


class CFBenchmarksAvgData(BaseModel):
    """Windowed-average metadata for a CF Benchmarks index value.

    ``value`` is an exact decimal string (8 dp); ``window_size`` counts the ticks
    in the window; ``window_start_ts_ms``/``window_end_ts_exclusive`` bound the
    window in Unix milliseconds (end-exclusive).
    """

    value: DollarDecimal
    window_size: int
    window_start_ts_ms: int
    window_end_ts_exclusive: int
    model_config = {"extra": "allow", "populate_by_name": True}


class CFBenchmarksValuePayload(BaseModel):
    """``cfbenchmarks_value.msg`` — one index value with trailing averages.

    ``data`` is the raw CF Benchmarks JSON frame as a string. ``avg_60s_data`` is
    always present (trailing 60-second average). ``last_60s_windowed_average_15min``
    is present only in the final minute before a quarter-hour close (``:00``/``:15``/
    ``:30``/``:45``), so it is optional.
    """

    index_id: str
    received_at: int
    data: str
    avg_60s_data: CFBenchmarksAvgData
    last_60s_windowed_average_15min: CFBenchmarksAvgData | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class CFBenchmarksValueMessage(BaseModel):
    """``cfbenchmarks_value`` data message envelope."""

    type: Literal["cfbenchmarks_value"] = "cfbenchmarks_value"
    sid: int
    seq: int | None = None
    msg: CFBenchmarksValuePayload
    model_config = {"extra": "allow", "populate_by_name": True}


class CFBenchmarksIndexListPayload(BaseModel):
    """``cfbenchmarks_value_indexlist.msg`` — the available index IDs."""

    index_ids: list[str]
    model_config = {"extra": "allow", "populate_by_name": True}


class CFBenchmarksIndexListMessage(BaseModel):
    """``cfbenchmarks_value_indexlist`` message — response to the ``indexlist`` action.

    ``id`` echoes the command id that requested the list; it is absent on
    unsolicited frames, so it is optional.
    """

    type: Literal["cfbenchmarks_value_indexlist"] = "cfbenchmarks_value_indexlist"
    id: int | None = None
    sid: int
    seq: int | None = None
    msg: CFBenchmarksIndexListPayload
    model_config = {"extra": "allow", "populate_by_name": True}

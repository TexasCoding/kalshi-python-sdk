"""FIX UTCTimestamp formatting/parsing (millisecond precision).

Shared by the message codec (UTCTIMESTAMP fields, :mod:`kalshi.fix.messages.base`)
and the session layer (``SendingTime``, :mod:`kalshi.fix.session`). Lives in its
own small internal module so neither importer reaches across into the other's
private helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime


def format_utc_timestamp(dt: datetime) -> str:
    """FIX UTCTimestamp with millisecond precision: ``YYYYMMDD-HH:MM:SS.sss``.

    Milliseconds are floor-truncated from microseconds (not rounded) so the
    value is byte-stable — the logon pre-hash must match tag 52 exactly.
    """
    return dt.strftime("%Y%m%d-%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def parse_utc_timestamp(value: str) -> datetime:
    """Parse a FIX UTCTimestamp (with or without fractional seconds) as UTC-aware."""
    fmt = "%Y%m%d-%H:%M:%S.%f" if "." in value else "%Y%m%d-%H:%M:%S"
    return datetime.strptime(value, fmt).replace(tzinfo=UTC)

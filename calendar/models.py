"""Data models for Calendar Primary events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Mapping, Optional

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback on older Python envs
    ZoneInfo = None  # type: ignore


def _row_get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """Access dict-like rows (including sqlite3.Row) safely."""
    if hasattr(row, "get"):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Best-effort datetime parser for DB rows and migration data."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, time.min)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None

        tzid: str | None = None
        if "|TZID=" in raw:
            raw, tzid = raw.split("|TZID=", 1)
            raw = raw.strip()
            tzid = tzid.strip() or None

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        # datetime.fromisoformat accepts both 'T' and ' ' separators.
        try:
            parsed = datetime.fromisoformat(raw)
            if tzid and ZoneInfo is not None:
                try:
                    zone = ZoneInfo(tzid)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=zone)
                    else:
                        parsed = parsed.astimezone(zone)
                except Exception:
                    pass
            return parsed
        except ValueError:
            pass

        # Handle date-only values.
        try:
            date_only = date.fromisoformat(raw)
            return datetime.combine(date_only, time.min)
        except ValueError:
            return None

    return None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


@dataclass
class Event:
    id: str
    title: str
    start_time: datetime
    description: Optional[str] = None
    end_time: Optional[datetime] = None
    category: str = "Work"
    rrule: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_recurring: bool = False
    parent_event_id: Optional[str] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Event":
        """Create an Event (or RecurringEvent) from a sqlite row/dict."""
        start_time = _parse_datetime(_row_get(row, "start_time"))
        if start_time is None:
            raise ValueError("start_time is required and must be parseable")

        created_at = _parse_datetime(_row_get(row, "created_at")) or datetime.now()
        updated_at = _parse_datetime(_row_get(row, "updated_at")) or created_at
        is_recurring = _parse_bool(_row_get(row, "is_recurring", False))

        payload = {
            "id": str(_row_get(row, "id", "")),
            "title": str(_row_get(row, "title", "")).strip(),
            "description": _row_get(row, "description"),
            "start_time": start_time,
            "end_time": _parse_datetime(_row_get(row, "end_time")),
            "category": str(_row_get(row, "category", "Work")) or "Work",
            "rrule": _row_get(row, "rrule"),
            "created_at": created_at,
            "updated_at": updated_at,
            "is_recurring": is_recurring,
            "parent_event_id": _row_get(row, "parent_event_id"),
        }

        if cls is Event and is_recurring:
            return RecurringEvent(**payload)

        return cls(**payload)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "category": self.category,
            "rrule": self.rrule,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_recurring": self.is_recurring,
            "parent_event_id": self.parent_event_id,
        }


@dataclass
class RecurringEvent(Event):
    """Event subtype for entries carrying recurrence rules."""

    is_recurring: bool = True

    def __post_init__(self) -> None:
        self.is_recurring = True

"""Recurring event expansion utilities (Wave 3a).

This module provides:
- RRULE generation/parsing helpers
- Recurring instance expansion (single event + event collections)
- Lightweight caching to avoid repeated expensive expansions

It is intentionally storage-agnostic; lifecycle persistence lives in
``calendar.recurring_manager``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterable

from dateutil import parser as date_parser
from dateutil.rrule import (
    DAILY,
    MONTHLY,
    WEEKLY,
    YEARLY,
    MO,
    TU,
    WE,
    TH,
    FR,
    SA,
    SU,
    rrulestr,
)

try:
    from .models import Event
except ImportError:  # Support direct/script-style loading
    from models import Event  # type: ignore


FREQUENCY_MAP = {
    "DAILY": DAILY,
    "WEEKLY": WEEKLY,
    "MONTHLY": MONTHLY,
    "YEARLY": YEARLY,
}

WEEKDAY_MAP = {
    "MO": MO,
    "TU": TU,
    "WE": WE,
    "TH": TH,
    "FR": FR,
    "SA": SA,
    "SU": SU,
}

WEEKDAY_INDEX = {
    0: "MO",
    1: "TU",
    2: "WE",
    3: "TH",
    4: "FR",
    5: "SA",
    6: "SU",
}

INSTANCE_PREFIX = "inst"
OVERRIDE_PREFIX = "ovr"
DELETED_PREFIX = "del"
DELETED_INSTANCE_TITLE = "__deleted_instance__"

DEFAULT_EXPANSION_LOOKAHEAD_DAYS = 365
DEFAULT_EXPANSION_LOOKBACK_DAYS = 30
MAX_EXPANDED_INSTANCES = 5000


def _normalize_datetime_input(
    value: datetime | date | str | None,
    *,
    default_end: bool,
    tz_hint: Any,
) -> datetime | None:
    if value is None:
        return None

    dt: datetime
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.max if default_end else time.min)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime string: {value!r}") from exc
    else:
        raise TypeError(f"Unsupported datetime input type: {type(value).__name__}")

    # Align timezone-awareness for safe comparisons.
    if tz_hint is not None and getattr(tz_hint, "utcoffset", None) is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_hint)
    else:
        # Parent event is naive. Convert aware boundaries to naive UTC for consistent comparison.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    return dt


def _resolve_range(
    event: Event,
    start_date: datetime | date | str | None,
    end_date: datetime | date | str | None,
) -> tuple[datetime, datetime]:
    tz_hint = event.start_time.tzinfo
    start = _normalize_datetime_input(start_date, default_end=False, tz_hint=tz_hint)
    end = _normalize_datetime_input(end_date, default_end=True, tz_hint=tz_hint)

    now = datetime.now(tz=tz_hint) if tz_hint else datetime.now()

    if start is None and end is None:
        start = now - timedelta(days=DEFAULT_EXPANSION_LOOKBACK_DAYS)
        end = now + timedelta(days=DEFAULT_EXPANSION_LOOKAHEAD_DAYS)
    elif start is None and end is not None:
        start = event.start_time
    elif start is not None and end is None:
        end = start + timedelta(days=DEFAULT_EXPANSION_LOOKAHEAD_DAYS)

    if end < start:  # Defensive guard, return empty range by collapsing.
        end = start

    return start, end


def occurrence_key(dt: datetime) -> str:
    """Stable, timezone-safe key for a recurrence occurrence."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    return dt.strftime("%Y%m%dT%H%M%S")


def occurrence_datetime(key: str, *, tz_hint: Any = None) -> datetime:
    """Inverse of ``occurrence_key``.

    If key is UTC (``...Z``) and ``tz_hint`` is provided, convert to that timezone.
    """
    normalized = str(key or "").strip()
    if not normalized:
        raise ValueError("occurrence key cannot be empty")

    if normalized.endswith("Z"):
        dt = datetime.strptime(normalized, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if tz_hint is not None and getattr(tz_hint, "utcoffset", None) is not None:
            return dt.astimezone(tz_hint)
        return dt

    dt = datetime.strptime(normalized, "%Y%m%dT%H%M%S")
    if tz_hint is not None and getattr(tz_hint, "utcoffset", None) is not None:
        dt = dt.replace(tzinfo=tz_hint)
    return dt


def build_instance_id(parent_event_id: str, occurrence_start: datetime) -> str:
    return f"{INSTANCE_PREFIX}__{parent_event_id}__{occurrence_key(occurrence_start)}"


def build_override_id(parent_event_id: str, occurrence_start: datetime) -> str:
    return f"{OVERRIDE_PREFIX}__{parent_event_id}__{occurrence_key(occurrence_start)}"


def build_deleted_id(parent_event_id: str, occurrence_start: datetime) -> str:
    return f"{DELETED_PREFIX}__{parent_event_id}__{occurrence_key(occurrence_start)}"


def parse_instance_id(instance_id: str) -> dict[str, str] | None:
    raw = str(instance_id or "").strip()
    parts = raw.split("__", 2)
    if len(parts) != 3:
        return None

    kind, parent_event_id, key = parts
    if kind not in {INSTANCE_PREFIX, OVERRIDE_PREFIX, DELETED_PREFIX}:
        return None
    if not parent_event_id or not key:
        return None

    return {
        "kind": kind,
        "parent_event_id": parent_event_id,
        "occurrence_key": key,
    }


def _normalize_rrule_for_parse(rrule_str: str) -> str:
    lines = [line.strip() for line in rrule_str.splitlines() if line.strip()]
    for line in lines:
        if line.upper().startswith("RRULE:"):
            return line.split(":", 1)[1].strip()
    # If no RRULE: prefix exists, assume the whole string is the RRULE payload.
    return (rrule_str or "").strip()


def _until_to_rrule(until: datetime | date | str) -> str:
    if isinstance(until, str):
        raw = until.strip()
        if not raw:
            raise ValueError("until cannot be empty")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            until_dt = datetime.fromisoformat(raw)
        except ValueError:
            until_date = date.fromisoformat(raw)
            until_dt = datetime.combine(until_date, time.max)
    elif isinstance(until, datetime):
        until_dt = until
    elif isinstance(until, date):
        until_dt = datetime.combine(until, time.max)
    else:
        raise TypeError("until must be datetime/date/ISO string")

    if until_dt.tzinfo is not None:
        return until_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return until_dt.strftime("%Y%m%dT%H%M%S")


def _normalize_byweekday(byweekday: Any) -> list[str] | None:
    if byweekday is None:
        return None

    if isinstance(byweekday, (str, int)):
        values = [byweekday]
    else:
        values = list(byweekday)

    normalized: list[str] = []
    for value in values:
        if isinstance(value, int):
            if value not in WEEKDAY_INDEX:
                raise ValueError("byweekday integer values must be in 0..6")
            normalized.append(WEEKDAY_INDEX[value])
            continue

        token = str(value).strip().upper()
        if not token:
            continue

        # Handle dateutil weekday reprs like "MO" or "MO(+1)".
        token = token.replace("(", "").replace(")", "")
        if len(token) >= 2 and token[-2:] in WEEKDAY_MAP:
            normalized.append(token)
            continue

        if token in WEEKDAY_MAP:
            normalized.append(token)
            continue

        raise ValueError(f"Unsupported weekday token: {value!r}")

    return normalized or None


def _normalize_bymonthday(bymonthday: Any) -> list[int] | None:
    if bymonthday is None:
        return None

    if isinstance(bymonthday, int):
        values = [bymonthday]
    else:
        values = list(bymonthday)

    normalized: list[int] = []
    for value in values:
        day = int(value)
        if day == 0 or day < -31 or day > 31:
            raise ValueError("bymonthday values must be between -31 and 31, excluding 0")
        normalized.append(day)

    return normalized or None


def generate_rrule(
    frequency: str,
    interval: int = 1,
    count: int | None = None,
    until: datetime | date | str | None = None,
    byweekday: list[Any] | tuple[Any, ...] | str | int | None = None,
    bymonthday: list[int] | tuple[int, ...] | int | None = None,
) -> str:
    """Build an RFC5545 RRULE string.

    Supported frequencies: daily, weekly, monthly, yearly.
    """
    if not isinstance(frequency, str) or not frequency.strip():
        raise ValueError("frequency is required")

    freq_token = frequency.strip().upper()
    if freq_token not in FREQUENCY_MAP:
        raise ValueError("frequency must be one of: daily, weekly, monthly, yearly")

    if interval < 1:
        raise ValueError("interval must be >= 1")

    if count is not None and count < 1:
        raise ValueError("count must be >= 1")

    rule_parts = [f"FREQ={freq_token}", f"INTERVAL={int(interval)}"]

    if count is not None:
        rule_parts.append(f"COUNT={int(count)}")

    if until is not None:
        rule_parts.append(f"UNTIL={_until_to_rrule(until)}")

    weekday_tokens = _normalize_byweekday(byweekday)
    if weekday_tokens:
        rule_parts.append(f"BYDAY={','.join(weekday_tokens)}")

    monthday_tokens = _normalize_bymonthday(bymonthday)
    if monthday_tokens:
        rule_parts.append(f"BYMONTHDAY={','.join(str(v) for v in monthday_tokens)}")

    return ";".join(rule_parts)


def parse_rrule(rrule_str: str) -> dict[str, Any]:
    """Parse an RRULE string to a friendly component dictionary."""
    if not isinstance(rrule_str, str) or not rrule_str.strip():
        raise ValueError("rrule_str must be a non-empty string")

    normalized = _normalize_rrule_for_parse(rrule_str)
    if not normalized:
        raise ValueError("No RRULE payload found")

    parts: dict[str, str] = {}
    for token in normalized.split(";"):
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        parts[key.strip().upper()] = value.strip()

    freq = parts.get("FREQ")
    if not freq:
        raise ValueError("RRULE is missing FREQ")

    interval = int(parts.get("INTERVAL", "1"))
    count = int(parts["COUNT"]) if parts.get("COUNT") else None

    until_value = None
    raw_until = parts.get("UNTIL")
    if raw_until:
        until_value = date_parser.parse(raw_until)

    byday_tokens = parts.get("BYDAY")
    byweekday = byday_tokens.split(",") if byday_tokens else None

    bymonthday_tokens = parts.get("BYMONTHDAY")
    bymonthday = [int(v) for v in bymonthday_tokens.split(",")] if bymonthday_tokens else None

    return {
        "frequency": freq.lower(),
        "interval": interval,
        "count": count,
        "until": until_value,
        "byweekday": byweekday,
        "bymonthday": bymonthday,
    }


def _event_signature(event: Event) -> tuple[Any, ...]:
    return (
        event.id,
        event.title,
        event.description,
        event.start_time,
        event.end_time,
        event.category,
        event.rrule,
        event.created_at,
        event.updated_at,
        int(bool(event.is_recurring)),
        event.parent_event_id,
    )


def _event_from_signature(signature: tuple[Any, ...]) -> Event:
    (
        event_id,
        title,
        description,
        start_time,
        end_time,
        category,
        rrule,
        created_at,
        updated_at,
        is_recurring,
        parent_event_id,
    ) = signature

    return Event(
        id=str(event_id),
        title=str(title),
        description=description,
        start_time=start_time,
        end_time=end_time,
        category=str(category or "Work"),
        rrule=rrule,
        created_at=created_at or datetime.now(),
        updated_at=updated_at or datetime.now(),
        is_recurring=bool(is_recurring),
        parent_event_id=parent_event_id,
    )


def _expand_event_uncached(
    event: Event,
    start_date: datetime | date | str | None,
    end_date: datetime | date | str | None,
) -> list[Event]:
    if not event.rrule or not event.is_recurring:
        start, end = _resolve_range(event, start_date, end_date)
        if _event_overlaps(event, start, end):
            return [replace(event)]
        return []

    start, end = _resolve_range(event, start_date, end_date)
    rule = rrulestr(event.rrule, dtstart=event.start_time, forceset=True)
    occurrences = rule.between(start, end, inc=True)

    if len(occurrences) > MAX_EXPANDED_INSTANCES:
        occurrences = occurrences[:MAX_EXPANDED_INSTANCES]

    duration = None
    if event.end_time is not None:
        duration = event.end_time - event.start_time

    expanded: list[Event] = []
    for occurrence_start in occurrences:
        occurrence_end = occurrence_start + duration if duration is not None else None

        expanded.append(
            Event(
                id=build_instance_id(event.id, occurrence_start),
                title=event.title,
                description=event.description,
                start_time=occurrence_start,
                end_time=occurrence_end,
                category=event.category,
                rrule=None,
                created_at=event.created_at,
                updated_at=event.updated_at,
                is_recurring=False,
                parent_event_id=event.id,
            )
        )

    return expanded


@lru_cache(maxsize=1024)
def _expand_event_cached(
    event_signature: tuple[Any, ...],
    start_key: datetime | None,
    end_key: datetime | None,
) -> tuple[Event, ...]:
    event = _event_from_signature(event_signature)
    expanded = _expand_event_uncached(event, start_key, end_key)
    return tuple(expanded)


def expand_event(
    event: Event,
    start_date: datetime | date | str | None,
    end_date: datetime | date | str | None,
) -> list[Event]:
    """Expand a recurring event into concrete instances within a range."""
    # Unbounded expansion uses a dynamic "now" window; avoid caching stale ranges.
    if start_date is None and end_date is None:
        return _expand_event_uncached(event, None, None)

    start_dt = _normalize_datetime_input(start_date, default_end=False, tz_hint=event.start_time.tzinfo)
    end_dt = _normalize_datetime_input(end_date, default_end=True, tz_hint=event.start_time.tzinfo)
    instances = _expand_event_cached(_event_signature(event), start_dt, end_dt)
    return [replace(item) for item in instances]


def _event_overlaps(event: Event, start: datetime, end: datetime) -> bool:
    event_end = event.end_time or event.start_time
    return event.start_time <= end and event_end >= start


def _event_in_requested_range(
    event: Event,
    start_date: datetime | date | str | None,
    end_date: datetime | date | str | None,
) -> bool:
    if start_date is None and end_date is None:
        return True

    tz_hint = event.start_time.tzinfo
    start = _normalize_datetime_input(start_date, default_end=False, tz_hint=tz_hint)
    end = _normalize_datetime_input(end_date, default_end=True, tz_hint=tz_hint)

    if start is None:
        start = datetime.min.replace(tzinfo=tz_hint) if tz_hint else datetime.min
    if end is None:
        end = datetime.max.replace(tzinfo=tz_hint) if tz_hint else datetime.max

    if end < start:
        return False

    return _event_overlaps(event, start, end)


def _group_child_events(children: list[Event], parent_id: str) -> tuple[dict[str, Event], set[str], list[Event]]:
    overrides: dict[str, Event] = {}
    deleted: set[str] = set()
    passthrough: list[Event] = []

    for child in children:
        metadata = parse_instance_id(child.id)

        if child.title == DELETED_INSTANCE_TITLE:
            if metadata and metadata.get("parent_event_id") == parent_id:
                deleted.add(metadata["occurrence_key"])
            else:
                deleted.add(occurrence_key(child.start_time))
            continue

        if metadata and metadata.get("parent_event_id") == parent_id:
            if metadata["kind"] == DELETED_PREFIX:
                deleted.add(metadata["occurrence_key"])
                continue
            if metadata["kind"] == OVERRIDE_PREFIX:
                overrides[metadata["occurrence_key"]] = child
                deleted.add(metadata["occurrence_key"])
                continue

        passthrough.append(child)

    return overrides, deleted, passthrough


def expand_events(
    events: Iterable[Event],
    start: datetime | date | str | None = None,
    end: datetime | date | str | None = None,
) -> list[Event]:
    """Expand recurring events and merge in override/deleted occurrence markers."""
    event_list = list(events)
    if not event_list:
        return []

    recurring_parents: list[Event] = []
    standalone_events: list[Event] = []
    child_events_by_parent: dict[str, list[Event]] = {}

    for event in event_list:
        if event.parent_event_id:
            child_events_by_parent.setdefault(event.parent_event_id, []).append(event)
            continue

        if event.is_recurring and event.rrule:
            recurring_parents.append(event)
            continue

        if _event_in_requested_range(event, start, end):
            standalone_events.append(event)

    expanded: list[Event] = list(standalone_events)

    for parent in recurring_parents:
        children = child_events_by_parent.pop(parent.id, [])
        overrides, deleted, passthrough_children = _group_child_events(children, parent.id)

        for base_instance in expand_event(parent, start, end):
            key = occurrence_key(base_instance.start_time)
            if key in deleted:
                continue
            expanded.append(base_instance)

        for _, override_event in overrides.items():
            if _event_in_requested_range(override_event, start, end):
                expanded.append(
                    replace(
                        override_event,
                        rrule=None,
                        is_recurring=False,
                        parent_event_id=parent.id,
                    )
                )

        for child in passthrough_children:
            if _event_in_requested_range(child, start, end):
                expanded.append(child)

    # If parent series was filtered out upstream but child rows are present,
    # pass them through so explicit overrides are still visible in results.
    for orphans in child_events_by_parent.values():
        for child in orphans:
            if child.title == DELETED_INSTANCE_TITLE:
                continue
            if _event_in_requested_range(child, start, end):
                expanded.append(child)

    return expanded


__all__ = [
    "expand_event",
    "expand_events",
    "generate_rrule",
    "parse_rrule",
    "occurrence_key",
    "occurrence_datetime",
    "build_instance_id",
    "build_override_id",
    "build_deleted_id",
    "parse_instance_id",
    "DELETED_INSTANCE_TITLE",
    "INSTANCE_PREFIX",
    "OVERRIDE_PREFIX",
    "DELETED_PREFIX",
]

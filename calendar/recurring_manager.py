"""Recurring event lifecycle management (Wave 3a).

This module persists recurring-series behavior on top of the base `events` table:
- Series rows are `is_recurring=1` with `rrule` set and `parent_event_id=NULL`
- Per-instance overrides are child rows with IDs prefixed by `ovr__`
- Per-instance deletions are tombstone child rows with IDs prefixed by `del__`

It integrates with `calendar.recurrence` for expansion semantics.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Any

try:
    from . import query_builder, recurrence, schema
    from .db import get_db, init_db
    from .exceptions import EventNotFoundError, ValidationError
    from .models import Event, RecurringEvent
except ImportError:  # Support direct/script-style loading
    import query_builder  # type: ignore
    import recurrence  # type: ignore
    import schema  # type: ignore
    from db import get_db, init_db  # type: ignore
    from exceptions import EventNotFoundError, ValidationError  # type: ignore
    from models import Event, RecurringEvent  # type: ignore


def _sql_datetime(value: datetime) -> str:
    rendered = value.isoformat(sep=" ", timespec="seconds")
    tz_key = getattr(value.tzinfo, "key", None)
    if tz_key:
        rendered = f"{rendered}|TZID={tz_key}"
    return rendered


def _parse_datetime(value: Any, *, field_name: str, tz_hint: Any = None) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValidationError(f"{field_name} cannot be empty")

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(f"{field_name} must be an ISO datetime string") from exc
    else:
        raise ValidationError(
            f"{field_name} must be datetime/date/ISO string (got {type(value).__name__})"
        )

    if tz_hint is not None and getattr(tz_hint, "utcoffset", None) is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz_hint)

    return dt


def _parse_optional_datetime(
    value: Any,
    *,
    field_name: str,
    tz_hint: Any = None,
) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, field_name=field_name, tz_hint=tz_hint)


def _validate_title(value: Any) -> str:
    if value is None:
        raise ValidationError("title is required")
    if not isinstance(value, str):
        raise ValidationError("title must be a string")
    title = value.strip()
    if not title:
        raise ValidationError("title cannot be empty")
    return title


def _normalize_text(value: Any, *, field_name: str, allow_none: bool = True) -> str | None:
    if value is None:
        if allow_none:
            return None
        raise ValidationError(f"{field_name} cannot be null")

    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")

    text = value.strip()
    return text or (None if allow_none else "")


def _normalize_category(value: Any) -> str:
    if value is None:
        return schema.DEFAULT_CATEGORY
    if not isinstance(value, str):
        raise ValidationError("category must be a string")
    category = value.strip()
    return category or schema.DEFAULT_CATEGORY


def _normalize_rrule(value: Any) -> str:
    if value is None:
        raise ValidationError("rrule is required for recurring series")
    if not isinstance(value, str):
        raise ValidationError("rrule must be a string")
    rule = value.strip()
    if not rule:
        raise ValidationError("rrule cannot be empty")

    # Validate parseability.
    recurrence.parse_rrule(rule)
    return rule


def _validate_time_order(start_time: datetime, end_time: datetime | None) -> None:
    if end_time is not None and end_time < start_time:
        raise ValidationError("end_time cannot be earlier than start_time")


def _fetch_event(event_id: str) -> Event:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {', '.join(schema.EVENT_FIELDS)} FROM {schema.EVENTS_TABLE} "
            f"WHERE {schema.FIELD_ID} = ? LIMIT 1",
            (event_id,),
        ).fetchone()

    if row is None:
        raise EventNotFoundError(f"Event not found: {event_id}")

    return Event.from_row(row)


def _fetch_children(parent_event_id: str) -> list[Event]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(schema.EVENT_FIELDS)} FROM {schema.EVENTS_TABLE} "
            f"WHERE {schema.FIELD_PARENT_EVENT_ID} = ?",
            (parent_event_id,),
        ).fetchall()

    return [Event.from_row(row) for row in rows]


def _ensure_recurring_series(event_id: str) -> RecurringEvent:
    event = _fetch_event(event_id)
    if event.parent_event_id:
        raise ValidationError(f"{event_id} is an instance override, not a series")
    if not event.is_recurring or not event.rrule:
        raise ValidationError(f"{event_id} is not a recurring series")

    if isinstance(event, RecurringEvent):
        return event

    return RecurringEvent(**event.__dict__)


def _resolve_series_id(event_id: str) -> str:
    metadata = recurrence.parse_instance_id(event_id)
    if metadata:
        return metadata["parent_event_id"]

    event = _fetch_event(event_id)
    if event.parent_event_id:
        return event.parent_event_id
    return event.id


def _resolve_occurrence(
    instance_id: str,
) -> tuple[RecurringEvent, datetime, dict[str, str] | None]:
    metadata = recurrence.parse_instance_id(instance_id)
    if metadata:
        parent = _ensure_recurring_series(metadata["parent_event_id"])
        occurrence_start = recurrence.occurrence_datetime(
            metadata["occurrence_key"],
            tz_hint=parent.start_time.tzinfo,
        )
        return parent, occurrence_start, metadata

    event = _fetch_event(instance_id)
    if not event.parent_event_id:
        raise ValidationError("instance_id must reference a recurring occurrence")

    parent = _ensure_recurring_series(event.parent_event_id)

    # Best effort: if the row ID encodes original occurrence, use it.
    event_meta = recurrence.parse_instance_id(event.id)
    if event_meta and event_meta.get("occurrence_key"):
        occurrence_start = recurrence.occurrence_datetime(
            event_meta["occurrence_key"],
            tz_hint=parent.start_time.tzinfo,
        )
    else:
        occurrence_start = event.start_time

    return parent, occurrence_start, event_meta


def _expand_single_occurrence(parent: RecurringEvent, occurrence_start: datetime) -> Event:
    candidates = recurrence.expand_event(parent, occurrence_start, occurrence_start)
    key = recurrence.occurrence_key(occurrence_start)
    for item in candidates:
        if recurrence.occurrence_key(item.start_time) == key:
            return item

    raise EventNotFoundError(
        f"Occurrence not found in series {parent.id} at {occurrence_start.isoformat()}"
    )


def _upsert_event(event: Event) -> Event:
    with get_db() as conn:
        exists = conn.execute(
            f"SELECT 1 FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ? LIMIT 1",
            (event.id,),
        ).fetchone()

        now = datetime.now(tz=event.start_time.tzinfo) if event.start_time.tzinfo else datetime.now()

        if exists:
            conn.execute(
                f"UPDATE {schema.EVENTS_TABLE} SET "
                f"{schema.FIELD_TITLE} = ?, "
                f"{schema.FIELD_DESCRIPTION} = ?, "
                f"{schema.FIELD_START_TIME} = ?, "
                f"{schema.FIELD_END_TIME} = ?, "
                f"{schema.FIELD_CATEGORY} = ?, "
                f"{schema.FIELD_RRULE} = ?, "
                f"{schema.FIELD_IS_RECURRING} = ?, "
                f"{schema.FIELD_PARENT_EVENT_ID} = ?, "
                f"{schema.FIELD_UPDATED_AT} = ? "
                f"WHERE {schema.FIELD_ID} = ?",
                (
                    event.title,
                    event.description,
                    _sql_datetime(event.start_time),
                    _sql_datetime(event.end_time) if event.end_time else None,
                    event.category,
                    event.rrule,
                    int(bool(event.is_recurring)),
                    event.parent_event_id,
                    _sql_datetime(now),
                    event.id,
                ),
            )
        else:
            conn.execute(
                f"INSERT INTO {schema.EVENTS_TABLE} ("
                f"{schema.FIELD_ID}, {schema.FIELD_TITLE}, {schema.FIELD_DESCRIPTION}, "
                f"{schema.FIELD_START_TIME}, {schema.FIELD_END_TIME}, {schema.FIELD_CATEGORY}, "
                f"{schema.FIELD_RRULE}, {schema.FIELD_CREATED_AT}, {schema.FIELD_UPDATED_AT}, "
                f"{schema.FIELD_IS_RECURRING}, {schema.FIELD_PARENT_EVENT_ID}"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.title,
                    event.description,
                    _sql_datetime(event.start_time),
                    _sql_datetime(event.end_time) if event.end_time else None,
                    event.category,
                    event.rrule,
                    _sql_datetime(event.created_at),
                    _sql_datetime(now),
                    int(bool(event.is_recurring)),
                    event.parent_event_id,
                ),
            )

        conn.commit()

    return _fetch_event(event.id)


def create_recurring_event(base_event: Event, rrule: str) -> RecurringEvent:
    """Create or convert an event into a recurring series with an RRULE."""
    init_db()

    if not isinstance(base_event, Event):
        raise ValidationError("base_event must be an Event")

    normalized_rrule = _normalize_rrule(rrule)

    series_id = base_event.id or f"evt_{uuid.uuid4().hex}"
    title = _validate_title(base_event.title)
    category = _normalize_category(base_event.category)
    description = base_event.description
    start_time = base_event.start_time
    end_time = base_event.end_time

    _validate_time_order(start_time, end_time)

    now = datetime.now(tz=start_time.tzinfo) if start_time.tzinfo else datetime.now()
    series = RecurringEvent(
        id=series_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        category=category,
        rrule=normalized_rrule,
        created_at=base_event.created_at or now,
        updated_at=now,
        is_recurring=True,
        parent_event_id=None,
    )

    saved = _upsert_event(series)
    if isinstance(saved, RecurringEvent):
        return saved

    return RecurringEvent(**saved.__dict__)


def get_instances(event_id: str, start: Any, end: Any) -> list[Event]:
    """Return all concrete instances for a recurring series in a range."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    series = _ensure_recurring_series(event_id.strip())
    start_dt = _parse_datetime(start, field_name="start", tz_hint=series.start_time.tzinfo)
    end_dt = _parse_datetime(end, field_name="end", tz_hint=series.start_time.tzinfo)
    if end_dt < start_dt:
        raise ValidationError("end must be greater than or equal to start")

    children = _fetch_children(series.id)
    expanded = recurrence.expand_events([series, *children], start=start_dt, end=end_dt)
    return query_builder.sort_events(expanded, ascending=True)


def update_instance(instance_id: str, **fields: Any) -> Event:
    """Modify a single occurrence by creating/updating an override row."""
    init_db()

    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValidationError("instance_id must be a non-empty string")

    allowed_fields = {
        schema.FIELD_TITLE,
        schema.FIELD_START_TIME,
        schema.FIELD_END_TIME,
        schema.FIELD_CATEGORY,
        schema.FIELD_DESCRIPTION,
    }

    unknown = sorted(set(fields) - allowed_fields)
    if unknown:
        raise ValidationError(f"Unknown update fields: {', '.join(unknown)}")

    parent, occurrence_start, _ = _resolve_occurrence(instance_id.strip())
    override_id = recurrence.build_override_id(parent.id, occurrence_start)

    try:
        current = _fetch_event(override_id)
    except EventNotFoundError:
        current = _expand_single_occurrence(parent, occurrence_start)
        current = Event(
            id=override_id,
            title=current.title,
            description=current.description,
            start_time=current.start_time,
            end_time=current.end_time,
            category=current.category,
            rrule=None,
            created_at=datetime.now(tz=current.start_time.tzinfo)
            if current.start_time.tzinfo
            else datetime.now(),
            updated_at=datetime.now(tz=current.start_time.tzinfo)
            if current.start_time.tzinfo
            else datetime.now(),
            is_recurring=False,
            parent_event_id=parent.id,
        )

    tz_hint = parent.start_time.tzinfo
    next_title = _validate_title(fields[schema.FIELD_TITLE]) if schema.FIELD_TITLE in fields else current.title
    next_start = (
        _parse_datetime(fields[schema.FIELD_START_TIME], field_name=schema.FIELD_START_TIME, tz_hint=tz_hint)
        if schema.FIELD_START_TIME in fields
        else current.start_time
    )
    next_end = (
        _parse_optional_datetime(fields[schema.FIELD_END_TIME], field_name=schema.FIELD_END_TIME, tz_hint=tz_hint)
        if schema.FIELD_END_TIME in fields
        else current.end_time
    )
    if schema.FIELD_START_TIME in fields and schema.FIELD_END_TIME not in fields and current.end_time is not None:
        delta = next_start - current.start_time
        next_end = current.end_time + delta

    next_category = (
        _normalize_category(fields[schema.FIELD_CATEGORY])
        if schema.FIELD_CATEGORY in fields
        else current.category
    )
    next_description = (
        _normalize_text(fields[schema.FIELD_DESCRIPTION], field_name=schema.FIELD_DESCRIPTION, allow_none=True)
        if schema.FIELD_DESCRIPTION in fields
        else current.description
    )

    _validate_time_order(next_start, next_end)

    override_event = Event(
        id=override_id,
        title=next_title,
        description=next_description,
        start_time=next_start,
        end_time=next_end,
        category=next_category,
        rrule=None,
        created_at=current.created_at,
        updated_at=datetime.now(tz=next_start.tzinfo) if next_start.tzinfo else datetime.now(),
        is_recurring=False,
        parent_event_id=parent.id,
    )

    saved = _upsert_event(override_event)

    # If this instance was previously tombstoned, clear the tombstone now.
    deleted_id = recurrence.build_deleted_id(parent.id, occurrence_start)
    with get_db() as conn:
        conn.execute(
            f"DELETE FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ?",
            (deleted_id,),
        )
        conn.commit()

    return saved


def update_series(event_id: str, **fields: Any) -> RecurringEvent:
    """Update recurring series metadata/rule (applies to all generated occurrences)."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    series_id = _resolve_series_id(event_id.strip())
    current = _ensure_recurring_series(series_id)

    allowed_fields = {
        schema.FIELD_TITLE,
        schema.FIELD_DESCRIPTION,
        schema.FIELD_START_TIME,
        schema.FIELD_END_TIME,
        schema.FIELD_CATEGORY,
        schema.FIELD_RRULE,
    }
    unknown = sorted(set(fields) - allowed_fields)
    if unknown:
        raise ValidationError(f"Unknown update fields: {', '.join(unknown)}")

    if not fields:
        return current

    tz_hint = current.start_time.tzinfo
    next_title = _validate_title(fields[schema.FIELD_TITLE]) if schema.FIELD_TITLE in fields else current.title
    next_description = (
        _normalize_text(fields[schema.FIELD_DESCRIPTION], field_name=schema.FIELD_DESCRIPTION, allow_none=True)
        if schema.FIELD_DESCRIPTION in fields
        else current.description
    )
    next_start = (
        _parse_datetime(fields[schema.FIELD_START_TIME], field_name=schema.FIELD_START_TIME, tz_hint=tz_hint)
        if schema.FIELD_START_TIME in fields
        else current.start_time
    )
    next_end = (
        _parse_optional_datetime(fields[schema.FIELD_END_TIME], field_name=schema.FIELD_END_TIME, tz_hint=tz_hint)
        if schema.FIELD_END_TIME in fields
        else current.end_time
    )
    if schema.FIELD_START_TIME in fields and schema.FIELD_END_TIME not in fields and current.end_time is not None:
        delta = next_start - current.start_time
        next_end = current.end_time + delta

    next_category = (
        _normalize_category(fields[schema.FIELD_CATEGORY])
        if schema.FIELD_CATEGORY in fields
        else current.category
    )
    next_rrule = (
        _normalize_rrule(fields[schema.FIELD_RRULE]) if schema.FIELD_RRULE in fields else current.rrule
    )

    _validate_time_order(next_start, next_end)

    updated = RecurringEvent(
        id=current.id,
        title=next_title,
        description=next_description,
        start_time=next_start,
        end_time=next_end,
        category=next_category,
        rrule=next_rrule,
        created_at=current.created_at,
        updated_at=datetime.now(tz=next_start.tzinfo) if next_start.tzinfo else datetime.now(),
        is_recurring=True,
        parent_event_id=None,
    )

    saved = _upsert_event(updated)
    if isinstance(saved, RecurringEvent):
        return saved
    return RecurringEvent(**saved.__dict__)


def delete_instance(instance_id: str) -> None:
    """Delete one occurrence by creating a tombstone marker for the base slot."""
    init_db()

    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValidationError("instance_id must be a non-empty string")

    parent, occurrence_start, _ = _resolve_occurrence(instance_id.strip())
    deleted_id = recurrence.build_deleted_id(parent.id, occurrence_start)
    override_id = recurrence.build_override_id(parent.id, occurrence_start)

    # Remove existing override for the slot if present.
    with get_db() as conn:
        conn.execute(
            f"DELETE FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ?",
            (override_id,),
        )

        tombstone = Event(
            id=deleted_id,
            title=recurrence.DELETED_INSTANCE_TITLE,
            description="Deleted recurring occurrence",
            start_time=occurrence_start,
            end_time=occurrence_start,
            category=parent.category,
            rrule=None,
            created_at=datetime.now(tz=occurrence_start.tzinfo)
            if occurrence_start.tzinfo
            else datetime.now(),
            updated_at=datetime.now(tz=occurrence_start.tzinfo)
            if occurrence_start.tzinfo
            else datetime.now(),
            is_recurring=False,
            parent_event_id=parent.id,
        )

        existing = conn.execute(
            f"SELECT 1 FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ? LIMIT 1",
            (deleted_id,),
        ).fetchone()

        if existing:
            conn.execute(
                f"UPDATE {schema.EVENTS_TABLE} SET "
                f"{schema.FIELD_TITLE} = ?, "
                f"{schema.FIELD_DESCRIPTION} = ?, "
                f"{schema.FIELD_START_TIME} = ?, "
                f"{schema.FIELD_END_TIME} = ?, "
                f"{schema.FIELD_CATEGORY} = ?, "
                f"{schema.FIELD_UPDATED_AT} = ? "
                f"WHERE {schema.FIELD_ID} = ?",
                (
                    tombstone.title,
                    tombstone.description,
                    _sql_datetime(tombstone.start_time),
                    _sql_datetime(tombstone.end_time) if tombstone.end_time else None,
                    tombstone.category,
                    _sql_datetime(tombstone.updated_at),
                    deleted_id,
                ),
            )
        else:
            conn.execute(
                f"INSERT INTO {schema.EVENTS_TABLE} ("
                f"{schema.FIELD_ID}, {schema.FIELD_TITLE}, {schema.FIELD_DESCRIPTION}, "
                f"{schema.FIELD_START_TIME}, {schema.FIELD_END_TIME}, {schema.FIELD_CATEGORY}, "
                f"{schema.FIELD_RRULE}, {schema.FIELD_CREATED_AT}, {schema.FIELD_UPDATED_AT}, "
                f"{schema.FIELD_IS_RECURRING}, {schema.FIELD_PARENT_EVENT_ID}"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tombstone.id,
                    tombstone.title,
                    tombstone.description,
                    _sql_datetime(tombstone.start_time),
                    _sql_datetime(tombstone.end_time) if tombstone.end_time else None,
                    tombstone.category,
                    None,
                    _sql_datetime(tombstone.created_at),
                    _sql_datetime(tombstone.updated_at),
                    0,
                    tombstone.parent_event_id,
                ),
            )

        conn.commit()


def delete_series(event_id: str) -> None:
    """Delete a recurring series and all child overrides/tombstones."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    series_id = _resolve_series_id(event_id.strip())
    _ensure_recurring_series(series_id)

    with get_db() as conn:
        conn.execute(
            f"DELETE FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ?",
            (series_id,),
        )
        # Safety net if FK cascade is unavailable.
        conn.execute(
            f"DELETE FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_PARENT_EVENT_ID} = ?",
            (series_id,),
        )
        conn.commit()


__all__ = [
    "create_recurring_event",
    "get_instances",
    "update_instance",
    "update_series",
    "delete_instance",
    "delete_series",
]

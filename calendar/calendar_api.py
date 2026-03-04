"""Calendar Primary API layer (Wave 2b).

Provides validated CRUD/query operations on top of the SQLite storage layer.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

try:
    from .db import get_db, init_db
    from .exceptions import DuplicateEventError, EventNotFoundError, ValidationError
    from .models import Event
    from . import query_builder, schema
except ImportError:  # Support direct/script-style loading
    from db import get_db, init_db  # type: ignore
    from exceptions import DuplicateEventError, EventNotFoundError, ValidationError  # type: ignore
    from models import Event  # type: ignore
    import query_builder  # type: ignore
    import schema  # type: ignore


def _parse_datetime(value: Any, *, field_name: str) -> datetime:
    if value is None:
        raise ValidationError(f"{field_name} is required")

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, time.min)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValidationError(f"{field_name} cannot be empty")

        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(
                f"{field_name} must be an ISO datetime string (got: {value!r})"
            ) from exc

    raise ValidationError(
        f"{field_name} must be datetime/date/ISO string (got {type(value).__name__})"
    )


def _parse_optional_datetime(value: Any, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, field_name=field_name)


def _validate_title(title: Any) -> str:
    if title is None:
        raise ValidationError("title is required")
    if not isinstance(title, str):
        raise ValidationError("title must be a string")
    normalized = title.strip()
    if not normalized:
        raise ValidationError("title cannot be empty")
    return normalized


def _normalize_category(category: Any) -> str:
    if category is None:
        return schema.DEFAULT_CATEGORY
    if not isinstance(category, str):
        raise ValidationError("category must be a string")
    normalized = category.strip()
    if not normalized:
        return schema.DEFAULT_CATEGORY
    return normalized


def _normalize_description(description: Any) -> str | None:
    if description is None:
        return None
    if not isinstance(description, str):
        raise ValidationError("description must be a string")
    normalized = description.strip()
    return normalized or None


def _normalize_rrule(rrule: Any) -> str | None:
    if rrule is None:
        return None
    if not isinstance(rrule, str):
        raise ValidationError("rrule must be a string")
    normalized = rrule.strip()
    return normalized or None


def _validate_time_order(start_time: datetime, end_time: datetime | None) -> None:
    if end_time is not None and end_time < start_time:
        raise ValidationError("end_time cannot be earlier than start_time")


def _sql_datetime(value: datetime) -> str:
    rendered = value.isoformat(sep=" ", timespec="seconds")
    tz_key = getattr(value.tzinfo, "key", None)
    if tz_key:
        rendered = f"{rendered}|TZID={tz_key}"
    return rendered


def _row_to_event(row: Any) -> Event:
    return Event.from_row(row)


def _ensure_event_exists(event_id: str) -> Event:
    return get_event_by_id(event_id)


def _check_duplicate_event(
    *,
    conn: Any,
    title: str,
    start_time: datetime,
    exclude_event_id: str | None = None,
) -> None:
    sql = (
        f"SELECT {schema.FIELD_ID} FROM {schema.EVENTS_TABLE} "
        f"WHERE LOWER({schema.FIELD_TITLE}) = LOWER(?) "
        f"AND {schema.FIELD_START_TIME} = ?"
    )
    params: list[Any] = [title, _sql_datetime(start_time)]

    if exclude_event_id:
        sql += f" AND {schema.FIELD_ID} != ?"
        params.append(exclude_event_id)

    sql += " LIMIT 1"

    row = conn.execute(sql, params).fetchone()
    if row is not None:
        raise DuplicateEventError(
            f"Event already exists with title={title!r} at start_time={start_time.isoformat()}"
        )


def add_event(
    title: str,
    start_time: Any,
    end_time: Any = None,
    category: str | None = None,
    description: str | None = None,
    rrule: str | None = None,
) -> Event:
    """Create and persist an event, returning the saved Event object."""
    init_db()

    normalized_title = _validate_title(title)
    parsed_start = _parse_datetime(start_time, field_name="start_time")
    parsed_end = _parse_optional_datetime(end_time, field_name="end_time")
    normalized_category = _normalize_category(category)
    normalized_description = _normalize_description(description)
    normalized_rrule = _normalize_rrule(rrule)

    _validate_time_order(parsed_start, parsed_end)

    event = Event(
        id=f"evt_{uuid.uuid4().hex}",
        title=normalized_title,
        description=normalized_description,
        start_time=parsed_start,
        end_time=parsed_end,
        category=normalized_category,
        rrule=normalized_rrule,
        is_recurring=bool(normalized_rrule),
    )

    insert_sql = (
        f"INSERT INTO {schema.EVENTS_TABLE} ("
        f"{schema.FIELD_ID}, {schema.FIELD_TITLE}, {schema.FIELD_DESCRIPTION}, "
        f"{schema.FIELD_START_TIME}, {schema.FIELD_END_TIME}, {schema.FIELD_CATEGORY}, "
        f"{schema.FIELD_RRULE}, {schema.FIELD_CREATED_AT}, {schema.FIELD_UPDATED_AT}, "
        f"{schema.FIELD_IS_RECURRING}, {schema.FIELD_PARENT_EVENT_ID}"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    with get_db() as conn:
        _check_duplicate_event(conn=conn, title=event.title, start_time=event.start_time)

        conn.execute(
            insert_sql,
            (
                event.id,
                event.title,
                event.description,
                _sql_datetime(event.start_time),
                _sql_datetime(event.end_time) if event.end_time else None,
                event.category,
                event.rrule,
                _sql_datetime(event.created_at),
                _sql_datetime(event.updated_at),
                int(event.is_recurring),
                event.parent_event_id,
            ),
        )
        conn.commit()

        row = conn.execute(
            f"SELECT {', '.join(schema.EVENT_FIELDS)} FROM {schema.EVENTS_TABLE} "
            f"WHERE {schema.FIELD_ID} = ? LIMIT 1",
            (event.id,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Failed to read event after insert")

    return _row_to_event(row)


def get_events(
    start: Any = None,
    end: Any = None,
    category: str | None = None,
) -> list[Event]:
    """Return events in an optional date range/category, sorted chronologically."""
    init_db()

    parsed_start = _parse_optional_datetime(start, field_name="start")
    parsed_end = _parse_optional_datetime(end, field_name="end")
    if parsed_start and parsed_end and parsed_end < parsed_start:
        raise ValidationError("end must be greater than or equal to start")

    sql, params = query_builder.build_events_query(
        start=parsed_start,
        end=parsed_end,
        category=category,
        ascending=True,
    )

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    events = [_row_to_event(row) for row in rows]
    expanded = query_builder.expand_recurring_events(events, start=parsed_start, end=parsed_end)
    return query_builder.sort_events(expanded, ascending=True)


def get_event_by_id(event_id: str) -> Event:
    """Get a single Event by ID or raise EventNotFoundError."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    with get_db() as conn:
        row = conn.execute(
            f"SELECT {', '.join(schema.EVENT_FIELDS)} FROM {schema.EVENTS_TABLE} "
            f"WHERE {schema.FIELD_ID} = ? LIMIT 1",
            (event_id.strip(),),
        ).fetchone()

    if row is None:
        raise EventNotFoundError(f"Event not found: {event_id}")

    return _row_to_event(row)


def update_event(event_id: str, **fields: Any) -> Event:
    """Update mutable event fields and return the updated Event object."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    allowed_fields = {
        schema.FIELD_TITLE,
        schema.FIELD_START_TIME,
        schema.FIELD_END_TIME,
        schema.FIELD_CATEGORY,
        schema.FIELD_DESCRIPTION,
        schema.FIELD_RRULE,
        schema.FIELD_PARENT_EVENT_ID,
    }

    unknown = sorted(set(fields) - allowed_fields)
    if unknown:
        raise ValidationError(f"Unknown update fields: {', '.join(unknown)}")

    if not fields:
        return _ensure_event_exists(event_id)

    current = _ensure_event_exists(event_id)

    next_title = _validate_title(fields[schema.FIELD_TITLE]) if schema.FIELD_TITLE in fields else current.title
    next_start = (
        _parse_datetime(fields[schema.FIELD_START_TIME], field_name=schema.FIELD_START_TIME)
        if schema.FIELD_START_TIME in fields
        else current.start_time
    )
    next_end = (
        _parse_optional_datetime(fields[schema.FIELD_END_TIME], field_name=schema.FIELD_END_TIME)
        if schema.FIELD_END_TIME in fields
        else current.end_time
    )
    next_category = (
        _normalize_category(fields[schema.FIELD_CATEGORY])
        if schema.FIELD_CATEGORY in fields
        else current.category
    )
    next_description = (
        _normalize_description(fields[schema.FIELD_DESCRIPTION])
        if schema.FIELD_DESCRIPTION in fields
        else current.description
    )
    next_rrule = (
        _normalize_rrule(fields[schema.FIELD_RRULE])
        if schema.FIELD_RRULE in fields
        else current.rrule
    )
    next_parent_event_id = (
        fields[schema.FIELD_PARENT_EVENT_ID] if schema.FIELD_PARENT_EVENT_ID in fields else current.parent_event_id
    )

    if next_parent_event_id is not None:
        next_parent_event_id = str(next_parent_event_id).strip() or None

    _validate_time_order(next_start, next_end)

    with get_db() as conn:
        _check_duplicate_event(
            conn=conn,
            title=next_title,
            start_time=next_start,
            exclude_event_id=event_id,
        )

        conn.execute(
            f"UPDATE {schema.EVENTS_TABLE} SET "
            f"{schema.FIELD_TITLE} = ?, "
            f"{schema.FIELD_START_TIME} = ?, "
            f"{schema.FIELD_END_TIME} = ?, "
            f"{schema.FIELD_CATEGORY} = ?, "
            f"{schema.FIELD_DESCRIPTION} = ?, "
            f"{schema.FIELD_RRULE} = ?, "
            f"{schema.FIELD_IS_RECURRING} = ?, "
            f"{schema.FIELD_PARENT_EVENT_ID} = ? "
            f"WHERE {schema.FIELD_ID} = ?",
            (
                next_title,
                _sql_datetime(next_start),
                _sql_datetime(next_end) if next_end else None,
                next_category,
                next_description,
                next_rrule,
                int(bool(next_rrule)),
                next_parent_event_id,
                event_id,
            ),
        )
        conn.commit()

    return get_event_by_id(event_id)


def delete_event(event_id: str) -> bool:
    """Delete an event by ID. Returns True if deleted, False if not found."""
    init_db()

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValidationError("event_id must be a non-empty string")

    with get_db() as conn:
        cursor = conn.execute(
            f"DELETE FROM {schema.EVENTS_TABLE} WHERE {schema.FIELD_ID} = ?",
            (event_id.strip(),),
        )
        conn.commit()
        return cursor.rowcount > 0


def search_events(query: str) -> list[Event]:
    """Case-insensitive text search over event title/description."""
    init_db()

    if not isinstance(query, str) or not query.strip():
        return []

    sql, params = query_builder.build_events_query(query=query, ascending=True)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    events = [_row_to_event(row) for row in rows]
    expanded = query_builder.expand_recurring_events(events)
    return query_builder.sort_events(expanded, ascending=True)


def get_today_events() -> list[Event]:
    """Convenience: events overlapping today in local time."""
    today = datetime.now().date()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    return get_events(start=start, end=end)


def get_week_events() -> list[Event]:
    """Convenience: events overlapping current week (Mon-Sun)."""
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    start = datetime.combine(start_of_week, time.min)
    end = datetime.combine(end_of_week, time.max)
    return get_events(start=start, end=end)


__all__ = [
    "add_event",
    "get_events",
    "get_event_by_id",
    "update_event",
    "delete_event",
    "search_events",
    "get_today_events",
    "get_week_events",
]

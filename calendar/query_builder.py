"""Query-building and result-shaping utilities for Calendar Primary.

Wave responsibilities:
- Date range query clauses
- Category filtering
- Recurring event expansion delegation
- Chronological sorting (default)
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Sequence

try:
    from .models import Event
    from . import schema
except ImportError:  # Support direct/script-style loading
    from models import Event  # type: ignore
    import schema  # type: ignore


def _sql_datetime(value: datetime) -> str:
    """Normalize datetimes for SQLite text comparisons."""
    return value.isoformat(sep=" ", timespec="seconds")


def _sql_field_datetime_expr(field_name: str) -> str:
    """SQLite datetime() expression with optional TZID suffix stripping."""
    # Stored format may optionally include a '|TZID=Area/City' suffix.
    # SQLite datetime() can't parse that suffix directly, so strip it when present.
    return (
        f"datetime(CASE WHEN instr({field_name}, '|TZID=') > 0 "
        f"THEN substr({field_name}, 1, instr({field_name}, '|TZID=') - 1) "
        f"ELSE {field_name} END)"
    )


def build_date_range_clause(
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[str, list[Any]]:
    """Return SQL WHERE fragment + params for date range filtering.

    Logic:
    - Recurring series are always included when a date filter is present,
      then trimmed by the recurrence expansion layer.
    - start + end: overlap query (events that touch the range)
    - start only: events from this point forward
    - end only: events up to this point
    - neither: empty clause
    """
    if start is None and end is None:
        return "", []

    start_field = schema.FIELD_START_TIME
    end_field = schema.FIELD_END_TIME
    recurring_field = schema.FIELD_IS_RECURRING

    start_expr = _sql_field_datetime_expr(start_field)
    end_expr = _sql_field_datetime_expr(end_field)

    recurring_clause = f"({recurring_field} = 1 AND {schema.FIELD_RRULE} IS NOT NULL)"

    if start is not None and end is not None:
        overlap_clause = (
            f"({start_expr} <= datetime(?) "
            f"AND ({end_field} IS NULL OR {end_expr} >= datetime(?)))"
        )
        clause = f"({recurring_clause} OR {overlap_clause})"
        return clause, [_sql_datetime(end), _sql_datetime(start)]

    if start is not None:
        forward_clause = (
            f"(({end_field} IS NOT NULL AND {end_expr} >= datetime(?)) "
            f"OR {start_expr} >= datetime(?))"
        )
        clause = f"({recurring_clause} OR {forward_clause})"
        v = _sql_datetime(start)
        return clause, [v, v]

    upper_clause = f"{start_expr} <= datetime(?)"
    clause = f"({recurring_clause} OR {upper_clause})"
    return clause, [_sql_datetime(end)]


def build_category_clause(category: str | Sequence[str] | None = None) -> tuple[str, list[Any]]:
    """Return SQL WHERE fragment + params for category filtering."""
    if category is None:
        return "", []

    field = schema.FIELD_CATEGORY

    if isinstance(category, str):
        value = category.strip()
        if not value:
            return "", []
        return f"LOWER({field}) = LOWER(?)", [value]

    values = [str(v).strip() for v in category if str(v).strip()]
    if not values:
        return "", []

    placeholders = ", ".join(["LOWER(?)"] * len(values))
    return f"LOWER({field}) IN ({placeholders})", values


def build_search_clause(query: str | None = None) -> tuple[str, list[Any]]:
    """Return SQL WHERE fragment + params for case-insensitive text search."""
    if query is None:
        return "", []

    value = query.strip()
    if not value:
        return "", []

    like = f"%{value}%"
    title_field = schema.FIELD_TITLE
    desc_field = schema.FIELD_DESCRIPTION
    clause = f"(LOWER({title_field}) LIKE LOWER(?) OR LOWER(COALESCE({desc_field}, '')) LIKE LOWER(?))"
    return clause, [like, like]


def build_sort_clause(ascending: bool = True) -> str:
    """Return default chronological ORDER BY clause."""
    direction = "ASC" if ascending else "DESC"
    start_expr = _sql_field_datetime_expr(schema.FIELD_START_TIME)
    end_or_start_expr = (
        f"datetime(CASE "
        f"WHEN {schema.FIELD_END_TIME} IS NULL THEN "
        f"(CASE WHEN instr({schema.FIELD_START_TIME}, '|TZID=') > 0 "
        f"THEN substr({schema.FIELD_START_TIME}, 1, instr({schema.FIELD_START_TIME}, '|TZID=') - 1) "
        f"ELSE {schema.FIELD_START_TIME} END) "
        f"WHEN instr({schema.FIELD_END_TIME}, '|TZID=') > 0 "
        f"THEN substr({schema.FIELD_END_TIME}, 1, instr({schema.FIELD_END_TIME}, '|TZID=') - 1) "
        f"ELSE {schema.FIELD_END_TIME} END)"
    )
    return (
        f"ORDER BY {start_expr} {direction}, "
        f"{end_or_start_expr} {direction}, "
        f"{schema.FIELD_TITLE} COLLATE NOCASE {direction}"
    )


def build_events_query(
    start: datetime | None = None,
    end: datetime | None = None,
    category: str | Sequence[str] | None = None,
    query: str | None = None,
    ascending: bool = True,
) -> tuple[str, list[Any]]:
    """Compose event SELECT query with optional filters and sorting."""
    clauses: list[str] = []
    params: list[Any] = []

    for clause_builder in (
        lambda: build_date_range_clause(start=start, end=end),
        lambda: build_category_clause(category=category),
        lambda: build_search_clause(query=query),
    ):
        clause, clause_params = clause_builder()
        if clause:
            clauses.append(clause)
            params.extend(clause_params)

    select_fields = ", ".join(schema.EVENT_FIELDS)
    sql = f"SELECT {select_fields} FROM {schema.EVENTS_TABLE}"

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += " " + build_sort_clause(ascending=ascending)
    return sql, params


def expand_recurring_events(
    events: Iterable[Event],
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Event]:
    """Expand recurring events into concrete instances.

    Delegates to ``calendar.recurrence.expand_events`` when available.
    Falls back to passthrough behavior if recurrence expansion is unavailable.
    """
    event_list = list(events)

    # Wave 3 hook: optional dynamic import to avoid hard dependency now.
    try:
        from . import recurrence  # type: ignore

        expand_fn = getattr(recurrence, "expand_events", None)
        if callable(expand_fn):
            return list(expand_fn(event_list, start=start, end=end))
    except Exception:
        pass

    return event_list


def sort_events(events: Iterable[Event], ascending: bool = True) -> list[Event]:
    """Sort Event objects chronologically with deterministic tie-breakers."""

    def _normalize_for_sort(dt: datetime) -> datetime:
        # Normalize naive/aware datetimes to UTC-aware for safe comparisons.
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _sort_key(event: Event) -> tuple[Any, ...]:
        end_time = event.end_time or event.start_time
        return (
            _normalize_for_sort(event.start_time),
            _normalize_for_sort(end_time),
            event.title.lower(),
            event.id,
        )

    return sorted(events, key=_sort_key, reverse=not ascending)

"""Database utilities for Calendar Primary (Wave 1a)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

try:
    from .models import Event
except ImportError:  # Support direct/script-style loading
    from models import Event  # type: ignore


DB_PATH = Path("/home/openclaw/.openclaw/workspace/calendar.db")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Suggested categories only; category values are intentionally free-form text.
SUGGESTED_CATEGORIES = (
    "Work",
    "Personal",
    "Kids Club",
    "Staff",
    "Deadlines",
    "Projects/OpenClaw",
)


def get_db(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Return a sqlite3 connection configured for this calendar DB."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(
    db_path: str | Path = DB_PATH,
    schema_path: str | Path = SCHEMA_PATH,
) -> None:
    """Initialize schema, indexes, and triggers."""
    schema_sql = Path(schema_path).read_text(encoding="utf-8")

    with get_db(db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_legacy_time(value: Any) -> time | None:
    """Parse HH:MM[:SS] and simple 12-hour times like '2:30 PM'."""
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    # ISO-friendly path first
    for candidate in (raw, raw + ":00"):
        try:
            return time.fromisoformat(candidate)
        except ValueError:
            continue

    # Minimal 12-hour fallback (e.g., '2:30 PM', '11 AM')
    upper = raw.upper().replace(" ", "")
    if upper.endswith("AM") or upper.endswith("PM"):
        meridiem = upper[-2:]
        base = upper[:-2]
        parts = base.split(":")
        if len(parts) == 1:
            parts.append("00")
        if len(parts) in (2, 3) and all(p.isdigit() for p in parts):
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) == 3 else 0

            if not (1 <= hour <= 12 and 0 <= minute <= 59 and 0 <= second <= 59):
                return None

            if meridiem == "AM" and hour == 12:
                hour = 0
            elif meridiem == "PM" and hour != 12:
                hour += 12

            return time(hour=hour, minute=minute, second=second)

    return None


def _parse_legacy_datetime(date_value: Any, time_value: Any | None = None) -> datetime | None:
    """Parse date/time from legacy CC calendar JSON fields."""
    parsed_date = _parse_iso_date(date_value)
    if parsed_date is None:
        return None

    parsed_time = _parse_legacy_time(time_value) if time_value is not None else None
    if parsed_time is None:
        parsed_time = time.min

    return datetime.combine(parsed_date, parsed_time)


def _parse_any_datetime(value: Any) -> datetime | None:
    """Parse full datetime strings (e.g., ISO timestamps in created_at)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)

    raw = str(value).strip()
    if not raw:
        return None

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass

    try:
        return datetime.combine(date.fromisoformat(raw), time.min)
    except ValueError:
        return None


def _normalize_category(category: Any) -> str:
    if category is None:
        return "Work"
    value = str(category).strip()
    return value or "Work"


def migrate_from_json(
    json_path: str | Path = "/home/openclaw/.openclaw/workspace/kinawa-command-center/data.json",
    db_path: str | Path = DB_PATH,
) -> dict[str, Any]:
    """
    Migrate legacy CC JSON calendar events into the SQLite events table.

    Expected JSON shape:
      {
        "calendar_events": [
          {"id": "...", "title": "...", "date": "YYYY-MM-DD", "time": "HH:MM", ...}
        ]
      }
    """
    init_db(db_path=db_path)

    source = Path(json_path)
    if not source.exists():
        raise FileNotFoundError(f"Legacy calendar JSON not found: {source}")

    payload = json.loads(source.read_text(encoding="utf-8"))

    if isinstance(payload, list):
        legacy_events = payload
    else:
        legacy_events = payload.get("calendar_events", [])

    migrated = 0
    skipped = 0

    upsert_sql = """
    INSERT INTO events (
        id,
        title,
        description,
        start_time,
        end_time,
        category,
        rrule,
        created_at,
        updated_at,
        is_recurring,
        parent_event_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        description = excluded.description,
        start_time = excluded.start_time,
        end_time = excluded.end_time,
        category = excluded.category,
        rrule = excluded.rrule,
        updated_at = excluded.updated_at,
        is_recurring = excluded.is_recurring,
        parent_event_id = excluded.parent_event_id;
    """

    with get_db(db_path) as conn:
        for idx, raw in enumerate(legacy_events, start=1):
            start_dt = _parse_legacy_datetime(raw.get("date"), raw.get("time"))
            if start_dt is None:
                skipped += 1
                continue

            end_dt = _parse_legacy_datetime(raw.get("date"), raw.get("end_time"))

            created_at = (
                _parse_any_datetime(raw.get("created_at"))
                or _parse_legacy_datetime(raw.get("date"), raw.get("time"))
                or datetime.now()
            )
            updated_at = _parse_any_datetime(raw.get("updated_at")) or created_at

            event = Event(
                id=str(raw.get("id") or f"legacy_evt_{idx:05d}"),
                title=str(raw.get("title") or "Untitled Event").strip(),
                description=raw.get("description") or None,
                start_time=start_dt,
                end_time=end_dt,
                category=_normalize_category(raw.get("category")),
                rrule=raw.get("rrule") or None,
                created_at=created_at,
                updated_at=updated_at,
                is_recurring=bool(raw.get("is_recurring") or raw.get("recurring") or raw.get("rrule")),
                parent_event_id=raw.get("parent_event_id") or None,
            )

            conn.execute(
                upsert_sql,
                (
                    event.id,
                    event.title,
                    event.description,
                    event.start_time.isoformat(sep=" "),
                    event.end_time.isoformat(sep=" ") if event.end_time else None,
                    event.category,
                    event.rrule,
                    event.created_at.isoformat(sep=" "),
                    event.updated_at.isoformat(sep=" "),
                    int(event.is_recurring),
                    event.parent_event_id,
                ),
            )
            migrated += 1

        conn.commit()

    return {
        "source": str(source),
        "db_path": str(Path(db_path)),
        "read": len(legacy_events),
        "migrated": migrated,
        "skipped": skipped,
    }

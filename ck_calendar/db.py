"""Database utilities for Calendar Primary (Wave 1a)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Event

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
    db_path = Path(db_path)
    schema_path = Path(schema_path)

    schema_sql = schema_path.read_text(encoding="utf-8")

    with get_db(db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()


def _parse_legacy_datetime(date_value: Any, time_value: Any | None = None) -> datetime | None:
    """Parse date/time from legacy CC calendar JSON fields."""
    if not date_value:
        return None

    date_text = str(date_value).strip()
    if not date_text:
        return None

    time_text = str(time_value).strip() if time_value is not None else ""

    candidates = []
    if time_text:
        candidates.extend(
            [
                f"{date_text} {time_text}",
                f"{date_text}T{time_text}",
            ]
        )
    else:
        candidates.append(date_text)

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    )

    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue

    # Last attempt: Python ISO parser
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue

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
    Migrate legacy CC JSON calendar events into SQLite events table.

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

            created_at = _parse_legacy_datetime(raw.get("created_at")) or datetime.now()
            updated_at = _parse_legacy_datetime(raw.get("updated_at")) or created_at

            event_id = str(raw.get("id") or f"legacy_evt_{idx:05d}")
            title = str(raw.get("title") or "Untitled Event").strip()
            description = raw.get("description") or None
            category = _normalize_category(raw.get("category"))
            rrule = raw.get("rrule") or None
            is_recurring = bool(raw.get("is_recurring") or raw.get("recurring") or rrule)
            parent_event_id = raw.get("parent_event_id") or None

            event = Event(
                id=event_id,
                title=title,
                description=description,
                start_time=start_dt,
                end_time=end_dt,
                category=category,
                rrule=rrule,
                created_at=created_at,
                updated_at=updated_at,
                is_recurring=is_recurring,
                parent_event_id=parent_event_id,
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

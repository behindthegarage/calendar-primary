"""Formatting helpers for Calendar Telegram responses (Wave 2a)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

try:
    from ck_calendar.parsed_event import ParseSuggestion
except Exception:  # pragma: no cover - fallback for partial environments
    ParseSuggestion = Any  # type: ignore


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _event_fields(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event

    data = {
        "id": getattr(event, "id", None),
        "title": getattr(event, "title", "Untitled Event"),
        "description": getattr(event, "description", None),
        "start_time": getattr(event, "start_time", None),
        "end_time": getattr(event, "end_time", None),
        "category": getattr(event, "category", None),
    }

    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        try:
            from_dict = to_dict()
            if isinstance(from_dict, dict):
                data.update(from_dict)
        except Exception:
            pass

    return data


def _fmt_time(dt: datetime) -> str:
    hour = dt.strftime("%I").lstrip("0") or "0"
    return f"{hour}:{dt.strftime('%M %p')}"


def _fmt_date(dt: datetime) -> str:
    return f"{dt.strftime('%a %b')} {dt.day}"


def _format_time_range(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> str:
    if start_dt is None:
        return "time TBD"

    date_part = _fmt_date(start_dt)
    start_part = _fmt_time(start_dt)

    if end_dt and end_dt.date() == start_dt.date():
        end_part = _fmt_time(end_dt)
        return f"{date_part}, {start_part}–{end_part}"

    if end_dt:
        end_part = f"{_fmt_date(end_dt)}, {_fmt_time(end_dt)}"
        return f"{date_part}, {start_part} → {end_part}"

    return f"{date_part}, {start_part}"


def format_event(event: Any) -> str:
    """Format a single event for Telegram display."""
    data = _event_fields(event)

    title = str(data.get("title") or "Untitled Event").strip()
    start_dt = _parse_dt(data.get("start_time"))
    end_dt = _parse_dt(data.get("end_time"))
    category = str(data.get("category") or "").strip()

    when = _format_time_range(start_dt, end_dt)
    category_suffix = f" · {category}" if category else ""
    return f"• {title} — {when}{category_suffix}"


def format_event_list(events: Iterable[Any], title: str) -> str:
    """Format an event list with a compact heading."""
    event_list = list(events)

    if not event_list:
        return f"{title}\nNo events."

    lines = [title]
    lines.extend(format_event(event) for event in event_list)
    return "\n".join(lines)


def format_confirmation(event: Any, action: str) -> str:
    """Format lightweight confirmation for add/update/delete actions."""
    action_map = {
        "add": "Added",
        "create": "Added",
        "update": "Updated",
        "modify": "Updated",
        "delete": "Removed",
        "remove": "Removed",
    }

    verb = action_map.get(action.lower(), "Updated")
    return f"{verb}: {format_event(event)[2:]}"  # trim bullet prefix


def format_suggestion(parse_suggestion: ParseSuggestion) -> str:
    """Format ambiguity clarification prompt."""
    title = getattr(parse_suggestion, "suggested_title", None) or "Untitled Event"
    start = _parse_dt(getattr(parse_suggestion, "suggested_start", None))
    end = _parse_dt(getattr(parse_suggestion, "suggested_end", None))
    questions = list(getattr(parse_suggestion, "questions", []) or [])

    lines = ["I can add this, quick check:"]
    lines.append(f"• {title} — {_format_time_range(start, end)}")

    if questions:
        lines.append("Need from you:")
        for question in questions[:3]:
            lines.append(f"- {question}")

    return "\n".join(lines)

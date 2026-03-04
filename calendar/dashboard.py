"""Lightweight Calendar Primary dashboard.

Run:
    cd calendar && python3 dashboard.py
Then open:
    http://localhost:5005
"""

from __future__ import annotations

from datetime import date, datetime
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

try:  # Package context (python -m calendar.dashboard)
    from .calendar_api import get_today_events, get_week_events
    from .db import get_db, init_db
    from .models import Event
except ImportError:  # Script context (cd calendar && python dashboard.py)
    from calendar_api import get_today_events, get_week_events  # type: ignore
    from db import get_db, init_db  # type: ignore
    from models import Event  # type: ignore


BASE_DIR = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = 5005

CATEGORY_META = {
    "work": {"label": "Work", "class": "category-work"},
    "personal": {"label": "Personal", "class": "category-personal"},
    "kids club": {"label": "Kids Club", "class": "category-kids-club"},
    "staff": {"label": "Staff", "class": "category-staff"},
    "deadlines": {"label": "Deadlines", "class": "category-deadlines"},
    "projects": {"label": "Projects", "class": "category-projects"},
}

LOGGER = logging.getLogger("calendar.dashboard")


def configure_logging() -> None:
    level_name = os.getenv("CALENDAR_DASHBOARD_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    init_db()
    app.logger.info("Calendar dashboard initialized (host=%s, port=%s)", HOST, PORT)

    @app.route("/")
    def dashboard_home() -> str:
        today_events = _prepare_events(get_today_events(), include_day=False)
        week_events = _prepare_events(get_week_events(), include_day=True)
        deadlines = _prepare_events(_get_deadline_events(), include_day=True)

        return render_template(
            "dashboard.html",
            page_title="Dashboard",
            active_view="home",
            current_date=_friendly_date(date.today()),
            show_today=True,
            show_week=True,
            show_deadlines=True,
            today_events=today_events,
            week_events=week_events,
            deadlines=deadlines,
        )

    @app.route("/today")
    def dashboard_today() -> str:
        return render_template(
            "dashboard.html",
            page_title="Today",
            active_view="today",
            current_date=_friendly_date(date.today()),
            show_today=True,
            show_week=False,
            show_deadlines=False,
            today_events=_prepare_events(get_today_events(), include_day=False),
            week_events=[],
            deadlines=[],
        )

    @app.route("/week")
    def dashboard_week() -> str:
        return render_template(
            "dashboard.html",
            page_title="This Week",
            active_view="week",
            current_date=_friendly_date(date.today()),
            show_today=False,
            show_week=True,
            show_deadlines=False,
            today_events=[],
            week_events=_prepare_events(get_week_events(), include_day=True),
            deadlines=[],
        )

    @app.route("/deadlines")
    def dashboard_deadlines() -> str:
        return render_template(
            "dashboard.html",
            page_title="Deadlines",
            active_view="deadlines",
            current_date=_friendly_date(date.today()),
            show_today=False,
            show_week=False,
            show_deadlines=True,
            today_events=[],
            week_events=[],
            deadlines=_prepare_events(_get_deadline_events(), include_day=True),
        )

    @app.route("/api/events")
    def api_events() -> Any:
        today_raw = get_today_events()
        week_raw = get_week_events()
        deadlines_raw = _get_deadline_events()

        return jsonify(
            {
                "generated_at": datetime.now().isoformat(),
                "today": [event.to_dict() for event in today_raw],
                "week": [event.to_dict() for event in week_raw],
                "deadlines": [event.to_dict() for event in deadlines_raw],
                "counts": {
                    "today": len(today_raw),
                    "week": len(week_raw),
                    "deadlines": len(deadlines_raw),
                },
            }
        )

    return app


def _get_deadline_events(limit: int = 20) -> list[Event]:
    """Read upcoming deadline events directly from DB via model parsing."""
    now = datetime.now()

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM events
            WHERE LOWER(category) LIKE '%deadline%'
            ORDER BY start_time ASC
            """
        ).fetchall()

    events = [Event.from_row(row) for row in rows]
    upcoming = [event for event in events if event.start_time >= now]
    upcoming.sort(key=lambda event: event.start_time)
    return upcoming[:limit]


def _prepare_events(events: list[Event], *, include_day: bool) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []

    for event in sorted(events, key=lambda e: e.start_time):
        category_info = _category_meta(event.category)
        prepared.append(
            {
                "id": event.id,
                "title": event.title,
                "description": event.description,
                "time_label": _time_label(event),
                "day_label": event.start_time.strftime("%a, %b %d") if include_day else None,
                "category": category_info["label"],
                "category_class": category_info["class"],
                "start_iso": event.start_time.isoformat(),
            }
        )

    return prepared


def _category_meta(category: str | None) -> dict[str, str]:
    raw = (category or "").strip()
    lowered = raw.lower()

    if lowered.startswith("projects"):
        return CATEGORY_META["projects"]

    if lowered in CATEGORY_META:
        return CATEGORY_META[lowered]

    return {"label": raw or "Work", "class": "category-work"}


def _time_label(event: Event) -> str:
    if event.end_time:
        return f"{_clock(event.start_time)} – {_clock(event.end_time)}"
    return _clock(event.start_time)


def _clock(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def _friendly_date(value: date) -> str:
    return value.strftime("%A, %B %d, %Y")


configure_logging()
app = create_app()


if __name__ == "__main__":
    LOGGER.info("Starting Calendar Primary Dashboard on %s:%s", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)

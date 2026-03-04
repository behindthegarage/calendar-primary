"""Lightweight Calendar Primary dashboard.

Run:
    cd calendar && python3 dashboard.py
Then open:
    http://localhost:5005
"""

from __future__ import annotations

from calendar import Calendar, monthrange
from datetime import date, datetime, time, timedelta
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

try:  # Package context (python -m calendar.dashboard)
    from .calendar_api import get_events, get_today_events, get_week_events
    from .db import get_db, init_db
    from .models import Event
except ImportError:  # Script context (cd calendar && python dashboard.py)
    from calendar_api import get_events, get_today_events, get_week_events  # type: ignore
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
        today = date.today()
        today_events = _prepare_events(get_today_events(), include_day=False)
        week_events = _prepare_events(get_week_events(), include_day=True)
        deadlines = _prepare_events(_get_deadline_events(), include_day=True)

        return render_template(
            "dashboard.html",
            page_title="Dashboard",
            active_view="home",
            current_date=_friendly_date(today),
            nav_date=today.isoformat(),
            show_today=True,
            show_week=True,
            show_deadlines=True,
            show_month=False,
            today_events=today_events,
            week_events=week_events,
            deadlines=deadlines,
        )

    @app.route("/today")
    def dashboard_today() -> str:
        date_param = request.args.get("date", "")
        view_date = _parse_date_param(date_param) or date.today()
        
        day_start = datetime.combine(view_date, time.min)
        day_end = datetime.combine(view_date, time.max)
        day_events = get_events(start=day_start, end=day_end)
        
        prev_next = _get_day_nav(view_date)

        return render_template(
            "dashboard.html",
            page_title="Today",
            active_view="today",
            current_date=_friendly_date(view_date),
            nav_date=view_date.isoformat(),
            show_today=True,
            show_week=False,
            show_deadlines=False,
            show_month=False,
            today_events=_prepare_events(day_events, include_day=False),
            week_events=[],
            deadlines=[],
            nav_prev=prev_next["prev"],
            nav_next=prev_next["next"],
            nav_prev_label="← Previous Day",
            nav_next_label="Next Day →",
        )

    @app.route("/week")
    def dashboard_week() -> str:
        # Support ?week=2026-W10 format
        week_param = request.args.get("week", "")
        date_param = request.args.get("date", "")
        
        if week_param:
            view_date = _parse_week_param(week_param)
        elif date_param:
            view_date = _parse_date_param(date_param)
        else:
            view_date = date.today()
        
        # Calculate week boundaries (Monday-Sunday)
        start_of_week = view_date - timedelta(days=view_date.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        
        week_start = datetime.combine(start_of_week, time.min)
        week_end = datetime.combine(end_of_week, time.max)
        week_events_raw = get_events(start=week_start, end=week_end)
        
        prev_next = _get_week_nav(view_date)

        return render_template(
            "dashboard.html",
            page_title=f"Week of {start_of_week.strftime('%b %d')}",
            active_view="week",
            current_date=f"{start_of_week.strftime('%b %d')} – {end_of_week.strftime('%b %d, %Y')}",
            nav_date=view_date.isoformat(),
            week_start=start_of_week.isoformat(),
            week_end=end_of_week.isoformat(),
            show_today=False,
            show_week=True,
            show_deadlines=False,
            show_month=False,
            today_events=[],
            week_events=_prepare_events(week_events_raw, include_day=True),
            deadlines=[],
            nav_prev=prev_next["prev"],
            nav_next=prev_next["next"],
            nav_prev_label="← Previous Week",
            nav_next_label="Next Week →",
        )

    @app.route("/month")
    def dashboard_month() -> str:
        # Support ?month=2026-03 or ?date=2026-03-15 format
        month_param = request.args.get("month", "")
        date_param = request.args.get("date", "")
        
        if month_param:
            view_date = _parse_month_param(month_param)
        elif date_param:
            view_date = _parse_date_param(date_param) or date.today()
        else:
            view_date = date.today()
        
        # Get month boundaries
        year, month = view_date.year, view_date.month
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        
        month_start = datetime.combine(first_day, time.min)
        month_end = datetime.combine(last_day, time.max)
        month_events_raw = get_events(start=month_start, end=month_end)
        
        # Build calendar grid data
        calendar_data = _build_month_calendar(year, month, month_events_raw)
        
        prev_next = _get_month_nav(view_date)
        
        # Check if a specific day is selected
        selected_day = request.args.get("day", "")
        selected_events = []
        if selected_day:
            selected_date = date(year, month, int(selected_day))
            day_start = datetime.combine(selected_date, time.min)
            day_end = datetime.combine(selected_date, time.max)
            selected_events = _prepare_events(
                get_events(start=day_start, end=day_end), include_day=False
            )

        return render_template(
            "dashboard.html",
            page_title=view_date.strftime("%B %Y"),
            active_view="month",
            current_date=view_date.strftime("%B %Y"),
            nav_date=view_date.isoformat(),
            month_year=year,
            month_num=month,
            month_name=view_date.strftime("%B"),
            show_today=False,
            show_week=False,
            show_deadlines=False,
            show_month=True,
            today_events=[],
            week_events=[],
            deadlines=[],
            calendar_weeks=calendar_data["weeks"],
            calendar_headers=calendar_data["headers"],
            today_str=date.today().isoformat(),
            selected_day=selected_day,
            selected_events=selected_events,
            nav_prev=prev_next["prev"],
            nav_next=prev_next["next"],
            nav_prev_label="← Previous Month",
            nav_next_label="Next Month →",
        )

    @app.route("/deadlines")
    def dashboard_deadlines() -> str:
        return render_template(
            "dashboard.html",
            page_title="Deadlines",
            active_view="deadlines",
            current_date=_friendly_date(date.today()),
            nav_date=date.today().isoformat(),
            show_today=False,
            show_week=False,
            show_deadlines=True,
            show_month=False,
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


# Date parsing helpers
def _parse_date_param(value: str) -> date | None:
    """Parse ISO date string (YYYY-MM-DD)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _parse_week_param(value: str) -> date:
    """Parse ISO week string (YYYY-W##) to the Monday of that week."""
    if not value:
        return date.today()
    try:
        # Format: 2026-W10
        parts = value.strip().split("-W")
        if len(parts) == 2:
            year, week = int(parts[0]), int(parts[1])
            # Find first Monday of the year, then add weeks
            jan1 = date(year, 1, 1)
            # ISO week starts on Monday; week 1 contains Jan 4
            jan4 = date(year, 1, 4)
            week1_monday = jan4 - timedelta(days=jan4.weekday())
            target_monday = week1_monday + timedelta(weeks=week - 1)
            return target_monday
    except (ValueError, IndexError):
        pass
    return date.today()


def _parse_month_param(value: str) -> date:
    """Parse YYYY-MM format to first day of that month."""
    if not value:
        return date.today()
    try:
        year, month = map(int, value.strip().split("-"))
        return date(year, month, 1)
    except (ValueError, IndexError):
        return date.today()


# Navigation helpers
def _get_day_nav(view_date: date) -> dict[str, str]:
    """Return prev/next day navigation links."""
    prev_day = view_date - timedelta(days=1)
    next_day = view_date + timedelta(days=1)
    return {
        "prev": f"/today?date={prev_day.isoformat()}",
        "next": f"/today?date={next_day.isoformat()}",
    }


def _get_week_nav(view_date: date) -> dict[str, str]:
    """Return prev/next week navigation links."""
    prev_week = view_date - timedelta(weeks=1)
    next_week = view_date + timedelta(weeks=1)
    return {
        "prev": f"/week?date={prev_week.isoformat()}",
        "next": f"/week?date={next_week.isoformat()}",
    }


def _get_month_nav(view_date: date) -> dict[str, str]:
    """Return prev/next month navigation links."""
    year, month = view_date.year, view_date.month
    # Previous month
    if month == 1:
        prev_month = date(year - 1, 12, 1)
    else:
        prev_month = date(year, month - 1, 1)
    # Next month
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return {
        "prev": f"/month?month={prev_month.strftime('%Y-%m')}",
        "next": f"/month?month={next_month.strftime('%Y-%m')}",
    }


# Month calendar builder
def _build_month_calendar(year: int, month: int, events: list[Event]) -> dict[str, Any]:
    """Build calendar grid data for month view."""
    # Day headers (Sun-Sat)
    headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    
    # Group events by day
    events_by_day: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        day = event.start_time.day
        if day not in events_by_day:
            events_by_day[day] = []
        category_info = _category_meta(event.category)
        events_by_day[day].append({
            "id": event.id,
            "title": event.title,
            "time_label": _time_label(event),
            "category": category_info["label"],
            "category_class": category_info["class"],
        })
    
    # Build calendar weeks
    cal = Calendar(firstweekday=6)  # Sunday first
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for day in week:
            if day == 0:
                week_days.append(None)  # Empty cell
            else:
                day_events = events_by_day.get(day, [])
                week_days.append({
                    "day": day,
                    "date_iso": f"{year:04d}-{month:02d}-{day:02d}",
                    "has_events": len(day_events) > 0,
                    "events": day_events,
                    "event_count": len(day_events),
                })
        weeks.append(week_days)
    
    return {"weeks": weeks, "headers": headers}


configure_logging()
app = create_app()


if __name__ == "__main__":
    LOGGER.info("Starting Calendar Primary Dashboard on %s:%s", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False)

"""Calendar Primary package.

Application modules should import explicit submodules, e.g.:
    from calendar.calendar_api import add_event

Compatibility note:
This project intentionally uses the top-level package name ``calendar``.
That collides with Python's stdlib module of the same name, so we re-export
stdlib calendar symbols (monthrange, timegm, etc.) to keep third-party imports
working (requests/dateutil/http.cookiejar commonly rely on them).
"""

from __future__ import annotations

import importlib.util
import sys
import sysconfig
from pathlib import Path


def _load_stdlib_calendar_module():
    stdlib_calendar_path = Path(sysconfig.get_path("stdlib")) / "calendar.py"
    spec = importlib.util.spec_from_file_location("_calendar_stdlib", stdlib_calendar_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load stdlib calendar module from {stdlib_calendar_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_stdlib_calendar = _load_stdlib_calendar_module()

# Re-export stdlib attributes so imports like `from calendar import monthrange`
# keep working even though this package shadows the stdlib module name.
for _name in dir(_stdlib_calendar):
    if _name.startswith("__"):
        continue
    if _name in globals():
        continue
    globals()[_name] = getattr(_stdlib_calendar, _name)


del _name


from .db import get_db, init_db
from .calendar_api import (
    add_event,
    delete_event,
    get_event_by_id,
    get_events,
    get_today_events,
    get_week_events,
    search_events,
    update_event,
)

__all__ = [
    # stdlib compatibility (selected commonly-used names)
    "timegm",
    "monthrange",
    "weekday",
    "isleap",
    "day_name",
    "day_abbr",
    "month_name",
    "month_abbr",
    # db exports
    "init_db",
    "get_db",
    # calendar API exports
    "add_event",
    "get_events",
    "get_event_by_id",
    "update_event",
    "delete_event",
    "search_events",
    "get_today_events",
    "get_week_events",
]

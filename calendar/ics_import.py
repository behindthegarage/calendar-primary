"""ICS import functionality for Calendar Primary.

Provides import of external ICS/iCalendar files into the Calendar Primary system.
Handles parsing VEVENT blocks, RRULE import, and conversion to Event objects.

Pure Python implementation - no external dependencies required.

Usage:
    # Import from file
    events = import_from_file("/path/to/calendar.ics")
    
    # Import from string
    events = parse_ics(ics_data)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, date, timedelta
from typing import Any

from .models import Event


# Common RRULE patterns that need normalization
FREQ_PATTERN = re.compile(r"FREQ=(\w+)", re.IGNORECASE)
BYDAY_PATTERN = re.compile(r"BYDAY=([^;]+)", re.IGNORECASE)
COUNT_PATTERN = re.compile(r"COUNT=(\d+)", re.IGNORECASE)
INTERVAL_PATTERN = re.compile(r"INTERVAL=(\d+)", re.IGNORECASE)
UNTIL_PATTERN = re.compile(r"UNTIL=([^;]+)", re.IGNORECASE)
BYMONTHDAY_PATTERN = re.compile(r"BYMONTHDAY=([^;]+)", re.IGNORECASE)


def _unfold_ics_lines(ics_data: str) -> list[str]:
    """Unfold ICS lines (remove continuation lines starting with space)."""
    lines = ics_data.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result = []
    
    for line in lines:
        if line.startswith(" "):
            # Continuation line - append to previous
            if result:
                result[-1] += line[1:]
        else:
            result.append(line)
    
    return result


def _parse_ics_datetime(value: Any) -> datetime | None:
    """Parse ICS datetime or date value.
    
    Handles formats like:
    - 20260304T143000 (local time)
    - 20260304T143000Z (UTC)
    - 20260304 (date only)
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    
    value = str(value).strip()
    if not value:
        return None
    
    # Handle UTC marker
    is_utc = value.endswith("Z")
    if is_utc:
        value = value[:-1]
    
    try:
        # Try datetime format: YYYYMMDDTHHMMSS
        if "T" in value:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
            if is_utc:
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        else:
            # Date only format: YYYYMMDD
            d = datetime.strptime(value, "%Y%m%d").date()
            return datetime.combine(d, datetime.min.time())
    except ValueError:
        pass
    
    # Try ISO format fallback
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    
    return None


def _unescape_ics_text(text: str) -> str:
    """Unescape ICS text values.
    
    ICS escaping rules:
    - \\n or \n -> newline
    - \\; -> semicolon
    - \\, -> comma
    - \\\\ -> backslash
    """
    # Order matters - reverse of escaping
    text = text.replace("\\\\", "\x00")  # Temp placeholder
    text = text.replace("\\;", ";")
    text = text.replace("\\,", ",")
    text = text.replace("\\n", "\n")
    text = text.replace("\\N", "\n")
    text = text.replace("\x00", "\\")
    
    return text


def _extract_rrule(vevent_data: dict[str, Any]) -> str | None:
    """Extract RRULE from a VEVENT component data.
    
    Returns the RRULE string in a normalized format suitable for
    storage in our calendar system.
    """
    rrule = vevent_data.get("rrule")
    if not rrule:
        return None
    
    rrule_str = str(rrule).strip()
    
    # Normalize
    if rrule_str.upper().startswith("RRULE:"):
        rrule_str = rrule_str[6:]
    
    return rrule_str if rrule_str else None


def _extract_categories(vevent_data: dict[str, Any]) -> str | None:
    """Extract categories from a VEVENT component."""
    categories = vevent_data.get("categories")
    if not categories:
        return None
    
    # Can be comma-separated
    if isinstance(categories, list):
        return ",".join(str(c) for c in categories)
    
    return str(categories)


def _convert_vevent_dict_to_event(vevent_data: dict[str, Any], default_category: str = "Work") -> Event | None:
    """Convert a VEVENT dictionary to our Event model.
    
    Args:
        vevent_data: Dictionary of VEVENT properties
        default_category: Category to use if none specified
        
    Returns:
        Event object or None if conversion failed
    """
    try:
        # Required: UID and DTSTART
        uid = vevent_data.get("uid")
        if not uid:
            uid = f"imported_{uuid.uuid4().hex}"
        else:
            uid = str(uid).strip()
        
        dtstart = vevent_data.get("dtstart")
        if not dtstart:
            return None  # Required field
        
        start_time = _parse_ics_datetime(dtstart)
        if not start_time:
            return None
        
        # Summary (title)
        summary = vevent_data.get("summary", "Untitled Event")
        title = _unescape_ics_text(str(summary))
        
        # Description
        description = vevent_data.get("description")
        if description:
            description = _unescape_ics_text(str(description))
        else:
            description = None
        
        # End time or duration
        dtend = vevent_data.get("dtend")
        if dtend:
            end_time = _parse_ics_datetime(dtend)
        else:
            # Try duration
            duration = vevent_data.get("duration")
            if duration:
                dur_str = str(duration).strip()
                # Parse duration like PT1H or 1:00:00
                if dur_str.startswith("P"):
                    try:
                        hours = 1
                        if "H" in dur_str:
                            match = re.search(r'(\d+)H', dur_str)
                            if match:
                                hours = int(match.group(1))
                        end_time = start_time + timedelta(hours=hours)
                    except Exception:
                        end_time = start_time + timedelta(hours=1)
                else:
                    end_time = start_time + timedelta(hours=1)
            else:
                end_time = None
        
        # Categories
        categories = _extract_categories(vevent_data)
        category = categories.split(",")[0] if categories else default_category
        
        # RRULE
        rrule = _extract_rrule(vevent_data)
        is_recurring = rrule is not None
        
        # Timestamps
        created_str = vevent_data.get("created")
        created_at = _parse_ics_datetime(created_str) if created_str else datetime.now()
        
        modified_str = vevent_data.get("last-modified")
        updated_at = _parse_ics_datetime(modified_str) if modified_str else created_at
        
        # Parent event (for recurrence exceptions)
        related = vevent_data.get("related-to")
        parent_event_id = str(related) if related else None
        
        return Event(
            id=uid,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            category=category,
            rrule=rrule,
            created_at=created_at,
            updated_at=updated_at,
            is_recurring=is_recurring,
            parent_event_id=parent_event_id,
        )
    
    except Exception as e:
        # Log and skip malformed events
        print(f"Error converting VEVENT: {e}")
        return None


def parse_ics(ics_data: str, default_category: str = "Work") -> list[Event]:
    """Parse ICS data string into Event objects.
    
    Args:
        ics_data: Raw ICS/iCalendar file content
        default_category: Default category for events without categories
        
    Returns:
        List of Event objects
    """
    events = []
    lines = _unfold_ics_lines(ics_data)
    
    in_event = False
    in_calendar = False
    event_data: dict[str, Any] = {}
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        if line == "BEGIN:VCALENDAR":
            in_calendar = True
            continue
        
        if line == "END:VCALENDAR":
            in_calendar = False
            continue
        
        if line == "BEGIN:VEVENT":
            in_event = True
            event_data = {}
            continue
        
        if line == "END:VEVENT":
            in_event = False
            if event_data.get("dtstart"):
                try:
                    event = _convert_vevent_dict_to_event(event_data, default_category)
                    if event:
                        events.append(event)
                except Exception as e:
                    print(f"Error processing VEVENT: {e}")
            continue
        
        if in_event:
            # Parse property line
            if ":" in line:
                # Handle parameters (e.g., DTSTART;VALUE=DATE:20260304)
                prop_part, value = line.split(":", 1)
                prop = prop_part.split(";")[0].upper()
                event_data[prop.lower()] = value
    
    return events


def import_from_file(filepath: str, default_category: str = "Work") -> list[Event]:
    """Import events from an ICS file.
    
    Args:
        filepath: Path to the .ics file
        default_category: Default category for events without categories
        
    Returns:
        List of Event objects
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        IOError: If the file can't be read
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        ics_data = f.read()
    
    return parse_ics(ics_data, default_category)


__all__ = [
    "parse_ics",
    "import_from_file",
    "_parse_ics_datetime",  # Exposed for testing
    "_unescape_ics_text",   # Exposed for testing
]
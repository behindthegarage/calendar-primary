"""ICS export functionality for Calendar Primary.

Provides ICS (iCalendar) format generation with proper:
- RFC 5545 compliance (VERSION:2.0, PRODID, VEVENT blocks)
- Stable UID generation across exports
- RRULE conversion to ICS format
- Line folding (75 character max per line)
- CRLF line endings

Pure Python implementation - no external dependencies required.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, date, timedelta
from typing import Any

from .models import Event


PRODID = "-//CK Calendar//EN"
VERSION = "2.0"
MAX_LINE_LENGTH = 75
CRLF = "\r\n"


class ICalCalendar:
    """Simple iCalendar object representation for ICS export."""
    
    def __init__(self) -> None:
        self.events: list[ICalEvent] = []
        self.properties: dict[str, Any] = {}
    
    def add(self, name: str, value: Any) -> None:
        """Add a calendar property."""
        self.properties[name.upper()] = value
    
    def add_component(self, component: ICalEvent) -> None:
        """Add an event component."""
        self.events.append(component)
    
    def to_ical(self) -> str:
        """Serialize to ICS format string."""
        lines = []
        lines.append("BEGIN:VCALENDAR")
        
        # Required properties
        prodid = self.properties.get("PRODID", PRODID)
        version = self.properties.get("VERSION", VERSION)
        lines.append(_format_content_line("PRODID", prodid))
        lines.append(_format_content_line("VERSION", version))
        
        # Optional properties
        for key, value in self.properties.items():
            if key not in ("PRODID", "VERSION"):
                lines.append(_format_content_line(key, str(value)))
        
        # Add timezone
        lines.append("BEGIN:VTIMEZONE")
        lines.append(_format_content_line("TZID", "America/Detroit"))
        lines.append("BEGIN:STANDARD")
        lines.append(_format_datetime_property("DTSTART", datetime(1970, 1, 1)))
        lines.append(_format_content_line("TZOFFSETFROM", "-0500"))
        lines.append(_format_content_line("TZOFFSETTO", "-0500"))
        lines.append("END:STANDARD")
        lines.append("END:VTIMEZONE")
        
        # Add events
        for event in self.events:
            lines.append(event.to_ical())
        
        lines.append("END:VCALENDAR")
        return CRLF.join(lines)


class ICalEvent:
    """Simple VEVENT component representation."""
    
    def __init__(self) -> None:
        self.properties: dict[str, Any] = {}
    
    def add(self, name: str, value: Any) -> None:
        """Add an event property."""
        self.properties[name.upper()] = value
    
    def to_ical(self) -> str:
        """Serialize to VEVENT block."""
        lines = []
        lines.append("BEGIN:VEVENT")
        
        # Required: UID, DTSTAMP, DTSTART
        for key in ["UID", "DTSTAMP", "DTSTART", "CREATED", "LAST-MODIFIED"]:
            if key in self.properties:
                value = self.properties[key]
                if isinstance(value, datetime):
                    lines.append(_format_datetime_property(key, value))
                else:
                    lines.append(_format_content_line(key, str(value)))
        
        # DTEND (optional but common)
        if "DTEND" in self.properties:
            value = self.properties["DTEND"]
            if isinstance(value, datetime):
                lines.append(_format_datetime_property("DTEND", value))
            else:
                lines.append(_format_content_line("DTEND", str(value)))
        
        # Summary and description
        if "SUMMARY" in self.properties:
            lines.append(_format_content_line("SUMMARY", str(self.properties["SUMMARY"])))
        
        if "DESCRIPTION" in self.properties:
            desc = str(self.properties["DESCRIPTION"])
            if desc:
                lines.append(_format_content_line("DESCRIPTION", desc))
        
        # Categories
        if "CATEGORIES" in self.properties:
            cats = self.properties["CATEGORIES"]
            if isinstance(cats, list):
                cats = ",".join(str(c) for c in cats)
            lines.append(_format_content_line("CATEGORIES", str(cats)))
        
        # RRULE
        if "RRULE" in self.properties:
            rrule = self.properties["RRULE"]
            if isinstance(rrule, dict):
                rrule_str = ";".join(f"{k}={v}" for k, v in rrule.items())
            else:
                rrule_str = str(rrule)
            lines.append(_format_content_line("RRULE", rrule_str))
        
        lines.append("END:VEVENT")
        return CRLF.join(lines)


class vRecur:
    """Simple RRULE value object."""
    
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
    
    def to_ical(self) -> str:
        return ";".join(f"{k}={v}" for k, v in self.params.items())


def _generate_stable_uid(event: Event) -> str:
    """Generate a stable UID that persists across exports.
    
    Uses the event ID as the primary identifier to ensure
    calendar applications recognize updates to existing events.
    """
    base = f"{event.id}@ck-calendar.hariclaw.com"
    return base


def _datetime_to_ics(dt: datetime) -> str:
    """Convert datetime to ICS format (UTC with Z suffix or local time)."""
    if dt.tzinfo is None:
        # Local time - use local time format (no Z)
        return dt.strftime("%Y%m%dT%H%M%S")
    else:
        # UTC time - convert and add Z
        utc_dt = dt.astimezone(__import__('datetime').timezone.utc)
        return utc_dt.strftime("%Y%m%dT%H%M%SZ")


def _date_to_ics(d: date) -> str:
    """Convert date to ICS DATE format (all-day events)."""
    return d.strftime("%Y%m%d")


def _fold_line(line: str) -> list[str]:
    """Fold a line at 75 characters per RFC 5545.
    
    Content lines longer than 75 octets MUST be folded.
    Continuation lines start with a space.
    """
    if len(line) <= MAX_LINE_LENGTH:
        return [line]
    
    result = []
    while len(line) > MAX_LINE_LENGTH:
        result.append(line[:MAX_LINE_LENGTH])
        line = " " + line[MAX_LINE_LENGTH:]
    result.append(line)
    return result


def _format_content_line(name: str, value: str) -> str:
    """Format a content line with proper escaping and folding."""
    # Escape special characters
    value = value.replace("\\", "\\\\")  # Backslash first
    value = value.replace(";", "\\;")
    value = value.replace(",", "\\,")
    value = value.replace("\n", "\\n")
    
    line = f"{name}:{value}"
    return CRLF.join(_fold_line(line))


def _format_datetime_property(name: str, dt: datetime | date, is_date: bool = False) -> str:
    """Format a datetime property (DTSTART, DTEND, etc.)."""
    if is_date or isinstance(dt, date) and not isinstance(dt, datetime):
        return _format_content_line(f"{name};VALUE=DATE", _date_to_ics(dt))
    else:
        return _format_content_line(name, _datetime_to_ics(dt))


def _rrule_to_ics(rrule: str) -> str | None:
    """Convert internal RRULE string to ICS RRULE format.
    
    Assumes RRULE is stored in a format that can be used directly
    or needs minimal transformation.
    """
    if not rrule:
        return None
    
    # Clean up the RRULE string
    rrule = rrule.strip()
    
    # If it already starts with RRULE:, strip it (we'll add it back)
    if rrule.upper().startswith("RRULE:"):
        rrule = rrule[6:].strip()
    
    # Validate basic RRULE structure
    if "=" not in rrule:
        return None
    
    return _format_content_line("RRULE", rrule)


def event_to_ics_vevent(event: Event) -> str:
    """Convert a single Event to an ICS VEVENT block (string format).
    
    Returns the complete VEVENT block as a string, ready to be
    included in a VCALENDAR block.
    """
    lines = []
    
    lines.append("BEGIN:VEVENT")
    
    # UID - stable across exports
    lines.append(_format_content_line("UID", _generate_stable_uid(event)))
    
    # Timestamps
    now = datetime.now()
    lines.append(_format_datetime_property("DTSTAMP", now))
    lines.append(_format_datetime_property("CREATED", event.created_at))
    lines.append(_format_datetime_property("LAST-MODIFIED", event.updated_at))
    
    # Start time
    lines.append(_format_datetime_property("DTSTART", event.start_time))
    
    # End time or duration
    if event.end_time:
        lines.append(_format_datetime_property("DTEND", event.end_time))
    elif event.is_recurring:
        # For recurring events without explicit end, default to 1 hour
        default_end = event.start_time + timedelta(hours=1)
        lines.append(_format_datetime_property("DTEND", default_end))
    
    # Summary (title)
    lines.append(_format_content_line("SUMMARY", event.title))
    
    # Description
    if event.description:
        lines.append(_format_content_line("DESCRIPTION", event.description))
    
    # Category
    if event.category:
        lines.append(_format_content_line("CATEGORIES", event.category))
    
    # Recurrence rule
    if event.rrule:
        rrule_line = _rrule_to_ics(event.rrule)
        if rrule_line:
            lines.append(rrule_line)
    
    lines.append("END:VEVENT")
    
    return CRLF.join(lines)


def generate_icalendar(events: list[Event]) -> ICalCalendar:
    """Create an icalendar.Calendar object from Event objects.
    
    This is the primary export function that returns a Calendar object
    which can be serialized to string or manipulated further.
    """
    cal = ICalCalendar()
    cal.add("prodid", PRODID)
    cal.add("version", VERSION)
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    
    for event in events:
        vevent = ICalEvent()
        
        # UID
        vevent.add("uid", _generate_stable_uid(event))
        
        # Timestamps
        now = datetime.now()
        vevent.add("dtstamp", now)
        vevent.add("created", event.created_at)
        vevent.add("last-modified", event.updated_at)
        
        # Start time
        vevent.add("dtstart", event.start_time)
        
        # End time
        if event.end_time:
            vevent.add("dtend", event.end_time)
        elif event.is_recurring:
            default_end = event.start_time + timedelta(hours=1)
            vevent.add("dtend", default_end)
        
        # Summary
        vevent.add("summary", event.title)
        
        # Description
        if event.description:
            vevent.add("description", event.description)
        
        # Category
        if event.category:
            vevent.add("categories", event.category)
        
        # RRULE
        if event.rrule:
            try:
                # Parse RRULE string into recurrence dictionary
                rrule_dict = _parse_rrule_string(event.rrule)
                if rrule_dict:
                    vevent.add("rrule", rrule_dict)
            except Exception:
                # If parsing fails, skip the RRULE
                pass
        
        cal.add_component(vevent)
    
    return cal


def _parse_rrule_string(rrule: str) -> dict[str, Any] | None:
    """Parse an RRULE string into a dictionary for icalendar.vRecur.
    
    Example: "FREQ=WEEKLY;BYDAY=MO,WE,FR" -> {"FREQ": "WEEKLY", "BYDAY": ["MO", "WE", "FR"]}
    """
    if not rrule:
        return None
    
    # Strip RRULE: prefix if present
    rrule = rrule.strip()
    if rrule.upper().startswith("RRULE:"):
        rrule = rrule[6:].strip()
    
    result: dict[str, Any] = {}
    
    # Split by semicolon
    parts = rrule.split(";")
    
    for part in parts:
        if "=" not in part:
            continue
        
        key, value = part.split("=", 1)
        key = key.upper().strip()
        value = value.strip()
        
        # Handle array values (comma-separated)
        if "," in value and key not in ("UNTIL", "DTSTART"):
            value = [v.strip() for v in value.split(",")]
        
        # Convert numeric values
        if key in ("COUNT", "INTERVAL"):
            try:
                value = int(value)
            except ValueError:
                pass
        
        result[key] = value
    
    return result if result else None


def export_events(events: list[Event]) -> str:
    """Generate ICS format string from Event objects.
    
    Returns a complete .ics file content as a string with:
    - VERSION:2.0
    - PRODID:-//CK Calendar//EN
    - Proper VEVENT blocks
    - CRLF line endings
    - Line folding for long lines
    
    Args:
        events: List of Event objects to export
        
    Returns:
        Complete ICS file content as a string
    """
    lines = []
    
    # Calendar header
    lines.append("BEGIN:VCALENDAR")
    lines.append(_format_content_line("VERSION", VERSION))
    lines.append(_format_content_line("PRODID", PRODID))
    lines.append(_format_content_line("CALSCALE", "GREGORIAN"))
    lines.append(_format_content_line("METHOD", "PUBLISH"))
    lines.append("")
    
    # Add timezone (optional but helpful)
    lines.append("BEGIN:VTIMEZONE")
    lines.append(_format_content_line("TZID", "America/Detroit"))
    lines.append("BEGIN:STANDARD")
    lines.append(_format_datetime_property("DTSTART", datetime(1970, 1, 1)))
    lines.append(_format_content_line("TZOFFSETFROM", "-0500"))
    lines.append(_format_content_line("TZOFFSETTO", "-0500"))
    lines.append("END:STANDARD")
    lines.append("END:VTIMEZONE")
    lines.append("")
    
    # Add events
    for event in events:
        lines.append(event_to_ics_vevent(event))
        lines.append("")
    
    # Calendar footer
    lines.append("END:VCALENDAR")
    
    return CRLF.join(lines)


def export_to_file(events: list[Event], filepath: str) -> None:
    """Export events to an .ics file.
    
    Args:
        events: List of Event objects to export
        filepath: Path to write the .ics file
    """
    ics_content = export_events(events)
    
    with open(filepath, "w", newline="") as f:
        f.write(ics_content)


# For compatibility with code expecting the icalendar library
Calendar = ICalCalendar
Event = ICalEvent

__all__ = [
    "export_events",
    "export_to_file", 
    "generate_icalendar",
    "event_to_ics_vevent",
    "PRODID",
    "VERSION",
    "ICalCalendar",
    "ICalEvent",
]
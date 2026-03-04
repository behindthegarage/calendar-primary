"""Calendar Skill — Natural language calendar management for CK Calendar.

This module provides intent detection, parsing, and database integration
for the Kinawa Command Center Calendar system.

Usage:
    from skills.calendar import parse_intent, add_event, get_events
    
    # Detect calendar intent in a message
    result = parse_intent("Meeting tomorrow at 3pm")
    if result.confidence > 0.85:
        add_event(result.to_event())
"""

__version__ = "1.0.0"
__author__ = "Hari"

# Core parsing and detection
from .nlp_parser import parse_calendar_intent, CalendarIntent
from .intent_detector import detect_intent, ConfidenceLevel

# Database API
from .calendar_api import (
    add_event,
    get_events,
    find_event_by_time,
    update_event,
    delete_event,
    search_events,
    Event,
)

# Category utilities
from .categories import suggest_category, get_categories, validate_category

# Response formatting
from .formatters import format_event_list, format_confirmation, format_query_result

__all__ = [
    # Version
    "__version__",
    "__author__",
    
    # Parsing
    "parse_calendar_intent",
    "CalendarIntent",
    "detect_intent",
    "ConfidenceLevel",
    
    # Database API
    "add_event",
    "get_events",
    "find_event_by_time",
    "update_event",
    "delete_event",
    "search_events",
    "Event",
    
    # Categories
    "suggest_category",
    "get_categories",
    "validate_category",
    
    # Formatters
    "format_event_list",
    "format_confirmation",
    "format_query_result",
]

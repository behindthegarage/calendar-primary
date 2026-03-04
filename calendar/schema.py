"""Schema constants for Calendar Primary tables/fields.

This module intentionally mirrors the SQLite schema.sql field names so higher
layers can avoid hard-coded strings scattered across the codebase.
"""

from __future__ import annotations

EVENTS_TABLE = "events"

FIELD_ID = "id"
FIELD_TITLE = "title"
FIELD_DESCRIPTION = "description"
FIELD_START_TIME = "start_time"
FIELD_END_TIME = "end_time"
FIELD_CATEGORY = "category"
FIELD_RRULE = "rrule"
FIELD_CREATED_AT = "created_at"
FIELD_UPDATED_AT = "updated_at"
FIELD_IS_RECURRING = "is_recurring"
FIELD_PARENT_EVENT_ID = "parent_event_id"

EVENT_FIELDS = (
    FIELD_ID,
    FIELD_TITLE,
    FIELD_DESCRIPTION,
    FIELD_START_TIME,
    FIELD_END_TIME,
    FIELD_CATEGORY,
    FIELD_RRULE,
    FIELD_CREATED_AT,
    FIELD_UPDATED_AT,
    FIELD_IS_RECURRING,
    FIELD_PARENT_EVENT_ID,
)

DEFAULT_CATEGORY = "Work"

SEARCHABLE_FIELDS = (FIELD_TITLE, FIELD_DESCRIPTION)

DEFAULT_SORT_FIELDS = (FIELD_START_TIME, FIELD_END_TIME, FIELD_TITLE)

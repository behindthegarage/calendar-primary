"""Custom exceptions for Calendar Primary API layer."""

from __future__ import annotations


class CalendarError(Exception):
    """Base class for calendar API errors."""


class EventNotFoundError(CalendarError):
    """Raised when an event ID does not exist."""


class ValidationError(CalendarError):
    """Raised when input validation fails."""


class DuplicateEventError(CalendarError):
    """Raised when attempting to create/update a duplicate event."""

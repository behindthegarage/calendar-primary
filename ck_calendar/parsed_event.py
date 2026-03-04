"""
calendar/parsed_event.py — Data structures for calendar NLP system.

Wave 1b of the Calendar Primary project.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class ParsedEvent:
    """
    Structured representation of an event parsed from natural language.
    
    Attributes:
        title: Event title/description
        start_time: When the event starts (datetime in local timezone)
        end_time: When the event ends (datetime, or None if not specified)
        duration_minutes: Duration if end_time not explicitly specified
        category: Suggested category (work, personal, kids_club, staff, deadline, projects)
        is_recurring: Whether this is a recurring event
        recurrence_rule: RRULE string for recurring events (e.g., "FREQ=WEEKLY;BYDAY=TH")
        confidence: 0.0-1.0 score based on parsing clarity
        raw_text: Original input text
        ambiguity_notes: List of what was ambiguous and how it was resolved
    """
    title: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    category: Optional[str] = None
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    confidence: float = 0.5
    raw_text: str = ""
    ambiguity_notes: list = field(default_factory=list)
    
    def to_event(self, user_id: str = "default") -> Dict[str, Any]:
        """
        Convert to a database-ready event dictionary.
        
        Args:
            user_id: The user who owns this event
            
        Returns:
            Dictionary ready for insertion into calendar database
        """
        event = {
            "title": self.title,
            "start_time": self.start_time.isoformat(),
            "user_id": user_id,
            "category": self.category or "general",
            "is_recurring": self.is_recurring,
            "confidence": self.confidence,
            "raw_parsed_text": self.raw_text,
        }
        
        if self.end_time:
            event["end_time"] = self.end_time.isoformat()
        elif self.duration_minutes:
            # Calculate end time from duration
            from datetime import timedelta
            calculated_end = self.start_time + timedelta(minutes=self.duration_minutes)
            event["end_time"] = calculated_end.isoformat()
            event["duration_minutes"] = self.duration_minutes
        else:
            # Default 1 hour duration
            from datetime import timedelta
            calculated_end = self.start_time + timedelta(hours=1)
            event["end_time"] = calculated_end.isoformat()
            event["duration_minutes"] = 60
            
        if self.recurrence_rule:
            event["recurrence_rule"] = self.recurrence_rule
            
        return event
    
    def is_confident(self, threshold: float = 0.7) -> bool:
        """Check if parsing confidence meets threshold."""
        return self.confidence >= threshold
    
    def has_ambiguity(self) -> bool:
        """Check if there were any ambiguities in parsing."""
        return len(self.ambiguity_notes) > 0
    
    def summary(self) -> str:
        """Generate a human-readable summary of the parsed event."""
        parts = [f"📅 {self.title}"]
        
        # Format time
        if self.start_time.date() == datetime.now().date():
            time_str = self.start_time.strftime("%I:%M %p")
        else:
            time_str = self.start_time.strftime("%a, %b %d at %I:%M %p")
        parts.append(f"🕐 {time_str}")
        
        if self.end_time:
            duration = int((self.end_time - self.start_time).total_seconds() / 60)
            parts.append(f"⏱️ {duration} minutes")
        elif self.duration_minutes:
            parts.append(f"⏱️ {self.duration_minutes} minutes")
            
        if self.category:
            parts.append(f"🏷️ {self.category}")
            
        if self.is_recurring:
            parts.append(f"🔄 Recurring")
            
        if self.confidence < 0.7:
            parts.append(f"⚠️ Confidence: {self.confidence:.0%}")
            
        return "\n".join(parts)


@dataclass
class IntentResult:
    """
    Result of calendar intent detection from natural language.
    
    Attributes:
        confidence: 0.0-1.0 score (HIGH > 0.8, MEDIUM 0.4-0.8, LOW < 0.4)
        is_calendar_mention: Whether this text references calendar/events
        suggested_action: What action to take ("add", "query", "modify", "none")
        detected_time_refs: List of time expressions found
        detected_event_keywords: List of event keywords found
        detected_intent_verbs: List of intent verbs found
        explanation: Why this decision was made
    """
    confidence: float = 0.0
    is_calendar_mention: bool = False
    suggested_action: str = "none"  # "add", "query", "modify", "none"
    detected_time_refs: list = field(default_factory=list)
    detected_event_keywords: list = field(default_factory=list)
    detected_intent_verbs: list = field(default_factory=list)
    explanation: str = ""
    
    # High-level classification
    @property
    def is_high_confidence(self) -> bool:
        """Clear calendar intent with time + event."""
        return self.confidence >= 0.8
    
    @property
    def is_medium_confidence(self) -> bool:
        """Ambiguous - has time or event but not both clearly."""
        return 0.4 <= self.confidence < 0.8
    
    @property
    def is_low_confidence(self) -> bool:
        """Probably not a calendar mention."""
        return self.confidence < 0.4
    
    def should_parse(self) -> bool:
        """Whether this text should be parsed as a calendar event."""
        return self.confidence >= 0.7 and self.suggested_action in ("add", "modify")
    
    def should_query(self) -> bool:
        """Whether this text is querying the calendar."""
        return self.confidence >= 0.7 and self.suggested_action == "query"
    
    def should_confirm(self) -> bool:
        """Whether we should ask user to confirm before adding."""
        return self.is_medium_confidence and self.suggested_action in ("add", "modify")


@dataclass
class ParseSuggestion:
    """
    Suggestion for handling ambiguous or incomplete event parsing.
    
    Used when the parser isn't confident enough to auto-create an event.
    """
    original_text: str
    suggested_title: Optional[str] = None
    suggested_start: Optional[datetime] = None
    suggested_end: Optional[datetime] = None
    questions: list = field(default_factory=list)
    clarification_needed: bool = False
    
    def __post_init__(self):
        if self.questions:
            self.clarification_needed = True

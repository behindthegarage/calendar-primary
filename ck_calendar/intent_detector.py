"""
calendar/intent_detector.py — Detect calendar intent in conversation.

Wave 1b of the Calendar Primary project.

Philosophy: Aggressive detection - better false positives than misses.
Parse liberally, confirm lightly.
"""

import re
import sys
from typing import List, Tuple, Optional
from datetime import datetime

# Handle imports when running as module vs directly
try:
    from ck_calendar.parsed_event import IntentResult
except ImportError:
    from parsed_event import IntentResult


# ============================================================================
# PATTERN DEFINITIONS
# ============================================================================

# Time-related expressions (comprehensive list)
TIME_EXPRESSIONS = [
    # Days of week
    r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\b(mon|tue|tues|wed|thu|thurs|fri|sat|sun)\b',
    
    # Relative dates
    r'\btomorrow\b',
    r'\btoday\b',
    r'\btonight\b',
    r'\bthis morning\b',
    r'\bthis afternoon\b',
    r'\bthis evening\b',
    r'\bnext week\b',
    r'\bthis week\b',
    r'\bnext month\b',
    r'\bthis month\b',
    r'\bnext (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\bthis (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\blast (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    r'\bcoming (monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    
    # Time of day patterns
    r'\bat\s+(\d{1,2})(:\d{2})?\s*(am|pm)\b',
    r'\bat\s+(\d{1,2})\s*(am|pm)\b',
    r'\b(\d{1,2})(:\d{2})?\s*(am|pm)\b',
    r'\b(\d{1,2}):(\d{2})\b',
    r'\bnoon\b',
    r'\bmidnight\b',
    r'\bmorning\b',
    r'\bafternoon\b',
    r'\bevening\b',
    
    # Relative time
    r'\bin\s+\d+\s+(minutes?|hours?|days?)\b',
    r'\bin\s+an?\s+(hour|minute)\b',
    r'\bafter\s+(\d{1,2})(:\d{2})?\s*(am|pm)?\b',
    r'\bbefore\s+(\d{1,2})(:\d{2})?\s*(am|pm)?\b',
    
    # Date patterns
    r'\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b',  # 3/4, 3/4/25
    r'\b\d{1,2}-\d{1,2}(?:-\d{2,4})?\b',  # 3-4, 3-4-25
    r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b',
]

# Event keywords - things that are likely calendar events
EVENT_KEYWORDS = [
    # Meetings
    r'\bmeeting\b',
    r'\bmeet\b',
    r'\bcall\b',
    r'\bconference\b',
    r'\bdiscussion\b',
    r'\bstand-?up\b',
    r'\bone-?on-?one\b',
    r'\b1:1\b',
    r'\bcheck-?in\b',
    r'\breview\b',
    
    # Appointments
    r'\bappointment\b',
    r'\bappt\b',
    r'\bdoctor\b',
    r'\bdentist\b',
    r'\bhaircut\b',
    r'\binterview\b',
    
    # Social
    r'\blunch\b',
    r'\bdinner\b',
    r'\bbrunch\b',
    r'\bcoffee\b',
    r'\bdrinks?\b',
    r'\bparty\b',
    r'\bgame\b',
    r'\bhanging out\b',
    r'\bget together\b',
    r'\bhangout\b',
    
    # Work/Deadlines
    r'\bdeadline\b',
    r'\bdue\b',
    r'\bpresentation\b',
    r'\btraining\b',
    r'\bworkshop\b',
    r'\bconference\b',
    r'\bevent\b',
    r'\bclass\b',
    r'\bsession\b',
    
    # Travel
    r'\bflight\b',
    r'\btrip\b',
    r'\btravel\b',
    r'\bgoing to\b',
    r'\bheaded to\b',
    
    # Personal
    r'\bgym\b',
    r'\bworkout\b',
    r'\bexercise\b',
    r'\brun\b',
    r'\byoga\b',
    r'\bmeditation\b',
    r'\btherapy\b',
]

# Intent verbs - suggest action to take
ADD_INTENT_VERBS = [
    r'\bhave\b',
    r'\bhas\b',
    r'\bgot\b',
    r'\bscheduled\b',
    r'\bschedule\b',
    r'\bset up\b',
    r'\bbook\b',
    r'\bbooking\b',
    r'\bremind me\b',
    r'\bdon\'t forget\b',
    r'\bneed to\b',
    r'\bmust\b',
    r'\bshould\b',
    r'\bplan\b',
    r'\bplanning\b',
    r'\borganize\b',
    r'\borganizing\b',
    r'\bgoing to\b',
    r'\bheaded to\b',
    r'\bmeeting\s+with\b',
    r'\blunch\s+with\b',
    r'\bcall\s+with\b',
    r'\bmeet\s+with\b',
]

QUERY_INTENT_VERBS = [
    r'\bwhat\'s on\b',
    r'\bwhat is on\b',
    r'\bwhat do i have\b',
    r'\bwhat\s+.*\s+scheduled\b',
    r'\bwhen\s+is\b',
    r'\bwhen\s+are\b',
    r'\bwhen\s+.*\b',
    r'\bshow me\b',
    r'\blist\b',
    r'\bcheck\b',
    r'\bchecking\b',
    r'\blook up\b',
    r'\bfind\b',
    r'\bdoes\s+.*\s+have\b',
    r'\bis\s+.*\s+free\b',
    r'\bam i free\b',
    r'\bdo i have\s+(time|anything)\b',
    r'\bcalendar\b',
]

MODIFY_INTENT_VERBS = [
    r'\bmove\b',
    r'\breschedule\b',
    r'\bchange\b',
    r'\bupdate\b',
    r'\bpostpone\b',
    r'\bdelay\b',
    r'\bpush\b',
    r'\bpull\b',
    r'\bbring\s+forward\b',
    r'\bshift\b',
    r'\bcancel\b',
    r'\bdelete\b',
    r'\bremove\b',
    r'\bcall off\b',
]

# Strong signals - these indicate very likely calendar intent
STRONG_CALENDAR_PATTERNS = [
    r'\bi\s+have\s+a\s+\w+\s+(on|at|this|next)\b',  # "I have a meeting on Thursday"
    r'\bmeeting\s+with\s+\w+\s+(on|at|this|next|tomorrow)\b',
    r'\blunch\s+with\s+\w+\s+(on|at|this|next|tomorrow)\b',
    r'\bdon\'t\s+forget\s+(to|about|my)\b',
    r'\bremind\s+me\s+(to|about)\b',
    r'\bwhat\'s\s+on\s+my\s+calendar\b',
    r'\bwhat\s+do\s+i\s+have\s+(today|tomorrow|this|next)\b',
    r'\bmove\s+my\s+\d{1,2}\s*(am|pm)?\s+to\b',
    r'\breschedule\s+my\b',
]

# Negative patterns - things that suggest NOT a calendar intent
NEGATIVE_PATTERNS = [
    r'\bthe\s+meeting\s+(was|went|is\s+over)\b',  # "The meeting went well"
    r'\bhad\s+a\s+\w+\s+(yesterday|last|earlier)\b',  # Past tense retrospective
    r'\bi\s+had\s+\w+\b',  # "I had lunch with Sarah" - past tense
    r'\bjust\s+finished\b',
    r'\bjust\s+had\b',
    r'\bwent\s+to\b',
    r'\battended\b',
    r'\bmissed\s+my\b',  # "I missed my flight" - past event
    r'\bhate\s+\w+',  # "I hate meetings" - opinion
    r'\blove\s+\w+',  # "I love lunch" - opinion
    r'\brooms?\s+are\s+booked\b',  # "Meeting rooms are booked" - not personal
    r'\bwere\s+\w+',  # Past tense
]


# ============================================================================
# INTENT DETECTION FUNCTIONS
# ============================================================================

def detect_calendar_intent(text: str) -> IntentResult:
    """
    Detect if text contains calendar-related intent.
    
    Philosophy: Aggressive detection - better false positives than misses.
    Parse liberally, confirm lightly.
    
    Args:
        text: User input text to analyze
        
    Returns:
        IntentResult with confidence and suggested action
    """
    text_lower = text.lower()
    
    # Find all matching patterns
    time_refs = _find_matches(text_lower, TIME_EXPRESSIONS)
    event_keywords = _find_matches(text_lower, EVENT_KEYWORDS)
    add_verbs = _find_matches(text_lower, ADD_INTENT_VERBS)
    query_verbs = _find_matches(text_lower, QUERY_INTENT_VERBS)
    modify_verbs = _find_matches(text_lower, MODIFY_INTENT_VERBS)
    
    # Check for strong signals
    strong_matches = _find_matches(text_lower, STRONG_CALENDAR_PATTERNS)
    negative_matches = _find_matches(text_lower, NEGATIVE_PATTERNS)
    
    # Calculate base scores
    has_time = len(time_refs) > 0
    has_event = len(event_keywords) > 0
    has_add_verb = len(add_verbs) > 0
    has_query_verb = len(query_verbs) > 0
    has_modify_verb = len(modify_verbs) > 0
    
    # Determine suggested action
    suggested_action = "none"
    if has_modify_verb and (has_time or has_event):
        suggested_action = "modify"
    elif has_query_verb:
        suggested_action = "query"
    elif has_add_verb or (has_time and has_event):
        suggested_action = "add"
    
    # Calculate confidence
    confidence = _calculate_confidence(
        has_time=has_time,
        has_event=has_event,
        has_add_verb=has_add_verb,
        has_query_verb=has_query_verb,
        has_modify_verb=has_modify_verb,
        strong_matches=len(strong_matches),
        negative_matches=len(negative_matches),
        time_count=len(time_refs),
        event_count=len(event_keywords)
    )
    
    # Build explanation
    explanation = _build_explanation(
        confidence=confidence,
        has_time=has_time,
        has_event=has_event,
        suggested_action=suggested_action,
        strong_matches=len(strong_matches),
        negative_matches=len(negative_matches)
    )
    
    return IntentResult(
        confidence=confidence,
        is_calendar_mention=confidence >= 0.3,
        suggested_action=suggested_action,
        detected_time_refs=time_refs,
        detected_event_keywords=event_keywords,
        detected_intent_verbs=add_verbs + query_verbs + modify_verbs,
        explanation=explanation
    )


def _find_matches(text: str, patterns: List[str]) -> List[str]:
    """Find all regex pattern matches in text."""
    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matches.append(match.group(0))
    return matches


def _calculate_confidence(
    has_time: bool,
    has_event: bool,
    has_add_verb: bool,
    has_query_verb: bool,
    has_modify_verb: bool,
    strong_matches: int,
    negative_matches: int,
    time_count: int,
    event_count: int
) -> float:
    """Calculate confidence score based on detected signals."""
    score = 0.0
    
    # Base scoring
    if has_time and has_event:
        score = 0.8  # Strong base - both time and event present
    elif has_time:
        score = 0.55  # Medium - just time (likely an event time)
    elif has_event:
        score = 0.4  # Slightly lower - just event
    
    # Intent verb boosts
    if has_add_verb and has_time and has_event:
        score = 0.95  # Very strong: "I have a meeting tomorrow"
    elif has_add_verb and has_time:
        score = 0.75  # Strong: has time and add intent
    elif has_query_verb:
        score = max(score, 0.85)  # Queries are usually clear
    elif has_modify_verb and has_time:
        score = max(score, 0.85)  # Modify with time reference is clear
    elif has_add_verb:
        score = max(score, 0.6)  # Add verb helps
    
    # Strong pattern bonus
    if strong_matches > 0:
        score = min(1.0, score + 0.15)
    
    # Negative pattern penalty
    if negative_matches > 0:
        score = max(0.0, score - 0.4)
    
    # Multiple signals bonus
    signal_count = sum([has_time, has_event, has_add_verb or has_query_verb or has_modify_verb])
    if signal_count >= 3:
        score = min(1.0, score + 0.05)
    
    # Multiple time/event refs slightly increase confidence
    if time_count > 1:
        score = min(1.0, score + 0.02)
    if event_count > 1:
        score = min(1.0, score + 0.02)
    
    return round(score, 2)


def _build_explanation(
    confidence: float,
    has_time: bool,
    has_event: bool,
    suggested_action: str,
    strong_matches: int,
    negative_matches: int
) -> str:
    """Build human-readable explanation of the detection."""
    parts = []
    
    if confidence >= 0.8:
        parts.append("High confidence: clear calendar intent")
    elif confidence >= 0.4:
        parts.append("Medium confidence: likely calendar mention")
    else:
        parts.append("Low confidence: weak or no calendar signals")
    
    signals = []
    if has_time:
        signals.append("time reference")
    if has_event:
        signals.append("event keyword")
    if suggested_action != "none":
        signals.append(f"{suggested_action} intent")
    
    if signals:
        parts.append(f"Detected: {', '.join(signals)}")
    
    if strong_matches > 0:
        parts.append(f"Strong pattern match ({strong_matches})")
    
    if negative_matches > 0:
        parts.append(f"Negative patterns detected ({negative_matches})")
    
    return "; ".join(parts)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def is_likely_event(text: str, threshold: float = 0.7) -> bool:
    """Quick check if text is likely describing an event to add."""
    result = detect_calendar_intent(text)
    return result.confidence >= threshold and result.suggested_action in ("add", "modify")


def is_query(text: str, threshold: float = 0.7) -> bool:
    """Quick check if text is querying the calendar."""
    result = detect_calendar_intent(text)
    return result.confidence >= threshold and result.suggested_action == "query"


def is_modify(text: str, threshold: float = 0.7) -> bool:
    """Quick check if text is modifying an existing event."""
    result = detect_calendar_intent(text)
    return result.confidence >= threshold and result.suggested_action == "modify"


def should_prompt_confirmation(text: str) -> bool:
    """Check if we should ask user to confirm before adding to calendar."""
    result = detect_calendar_intent(text)
    return result.is_medium_confidence and result.suggested_action in ("add", "modify")


# ============================================================================
# TEST EXAMPLES
# ============================================================================

TEST_CASES = [
    # High confidence - add
    ("I have a meeting Thursday at 10", "add", 0.9),
    ("Lunch with Sarah tomorrow", "add", 0.9),
    ("Remind me to call John at 3pm", "add", 0.9),
    ("Don't forget my dentist appointment next week", "add", 0.85),
    ("Going to the gym at 5", "add", 0.6),
    
    # High confidence - query
    ("What's on my calendar today?", "query", 0.9),
    ("What do I have tomorrow?", "query", 0.9),
    ("When is my meeting?", "query", 0.85),
    ("Show me my schedule", "query", 0.8),
    
    # High confidence - modify
    ("Move my 2pm to 3pm", "modify", 0.9),
    ("Reschedule my meeting to Friday", "modify", 0.85),
    ("Cancel tomorrow's lunch", "modify", 0.85),
    
    # Medium confidence - ambiguous (may need confirmation)
    ("I have a meeting", "add", 0.5),  # No time
    ("Thursday at 10", "add", 0.5),  # No event
    ("Lunch tomorrow maybe", "add", 0.65),  # Uncertain language
    
    # Low confidence - ignore
    ("The meeting went well", "none", 0.0),  # Past tense
    ("I had lunch with Sarah", "none", 0.0),  # Past tense - detected but low conf
    ("Meeting rooms are booked", "none", 0.0),  # Not personal event
    ("I hate meetings", "none", 0.0),  # Opinion, not event
]


def run_tests():
    """Run test cases and report accuracy."""
    print("=" * 60)
    print("CALENDAR INTENT DETECTION TESTS")
    print("=" * 60)
    
    correct = 0
    total = len(TEST_CASES)
    
    for text, expected_action, min_confidence in TEST_CASES:
        result = detect_calendar_intent(text)
        
        action_correct = result.suggested_action == expected_action
        confidence_ok = result.confidence >= min_confidence - 0.1  # Allow 0.1 margin
        
        if action_correct and confidence_ok:
            correct += 1
            status = "✓"
        else:
            status = "✗"
        
        print(f"\n{status} \"{text}\"")
        print(f"   Expected: {expected_action} (≥{min_confidence})")
        print(f"   Got: {result.suggested_action} ({result.confidence:.2f})")
        print(f"   {result.explanation}")
    
    print("\n" + "=" * 60)
    print(f"Accuracy: {correct}/{total} ({100*correct/total:.0f}%)")
    print("=" * 60)
    
    return correct, total


if __name__ == "__main__":
    run_tests()

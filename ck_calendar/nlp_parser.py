"""
calendar/nlp_parser.py — Natural language to structured event parser.

Wave 1b of the Calendar Primary project.

Uses Kimi K2.5 via direct API calls to extract structured event data from
natural language text. Handles ambiguous times, recurring events, and
confidence scoring.
"""

import os
import json
import re
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

# Handle imports when running as module vs directly
try:
    from ck_calendar.parsed_event import ParsedEvent, ParseSuggestion
except ImportError:
    from parsed_event import ParsedEvent, ParseSuggestion


# Kimi API configuration
KIMI_API_KEY = os.environ.get('KIMI_API_KEY')
KIMI_BASE_URL = "https://api.kimi.com/coding"
KIMI_MODEL = "k2p5"


# System prompt for the LLM parser
PARSER_SYSTEM_PROMPT = """You are a calendar event parser. Extract structured event data from natural language.

Your task:
1. Identify the event title/description
2. Parse the start time (datetime)
3. Parse the end time OR duration (if specified)
4. Suggest a category from: work, personal, kids_club, staff, deadline, projects, general
5. Detect if this is a recurring event
6. Generate an RRULE string if recurring

Current date/time context will be provided. Use it to resolve relative dates like "tomorrow" or "next week".

Respond ONLY with valid JSON in this exact format:
{
    "title": "string",
    "start_time": "ISO8601 datetime string",
    "end_time": "ISO8601 datetime string or null",
    "duration_minutes": number or null,
    "category": "suggested category or null",
    "is_recurring": boolean,
    "recurrence_rule": "RRULE string or null",
    "confidence": 0.0-1.0,
    "ambiguity_notes": ["list of what was ambiguous and how resolved"]
}

Confidence scoring:
- 0.9-1.0: Crystal clear - explicit time, date, and event
- 0.7-0.9: Clear - may have minor ambiguity (assumed year, implied duration)
- 0.4-0.7: Ambiguous - missing some details, made reasonable assumptions
- 0.0-0.4: Unclear - major missing info, very vague

For recurring events, generate standard RRULE strings:
- Weekly: "FREQ=WEEKLY;BYDAY=MO" (MO, TU, WE, TH, FR, SA, SU)
- Bi-weekly: "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH"
- Monthly: "FREQ=MONTHLY;BYMONTHDAY=15"
- Daily: "FREQ=DAILY"
- Weekdays: "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"

Default to 1 hour duration if not specified. Assume current year if not specified.
"""


def get_current_context() -> str:
    """Generate current date/time context for the parser."""
    now = datetime.now()
    return f"""Current date/time context:
- Today is: {now.strftime("%A, %B %d, %Y")}
- Current time: {now.strftime("%I:%M %p")}
- Weekday: {now.strftime("%A")}
- Tomorrow is: {(now + timedelta(days=1)).strftime("%A, %B %d")}
- Next {now.strftime("%A")} is: {(now + timedelta(days=7)).strftime("%A, %B %d")}
- This week: {now.strftime("%b %d")} - {(now + timedelta(days=6-now.weekday())).strftime("%b %d")}
- Next week starts: {(now + timedelta(days=7-now.weekday())).strftime("%A, %B %d")}
"""


def parse_event(text: str, reference_time: Optional[datetime] = None) -> ParsedEvent:
    """
    Parse natural language text into a structured event using LLM.
    
    Args:
        text: Natural language description of an event
        reference_time: Optional reference time for relative date parsing
                       (defaults to current time)
    
    Returns:
        ParsedEvent with extracted details and confidence score
    """
    if reference_time is None:
        reference_time = datetime.now()

    if not KIMI_API_KEY:
        return _create_fallback_event(
            text,
            reference_time,
            "KIMI_API_KEY not configured; using fallback parser",
        )
    
    # Build the prompt with context
    context = get_current_context()
    user_prompt = f"{context}\n\nParse this event: \"{text}\""
    
    try:
        # Call Kimi API
        result = _call_llm_parser(user_prompt)
        
        if not result:
            # Fallback: create low-confidence event with defaults
            return _create_fallback_event(text, reference_time)
        
        # Parse the JSON result
        parsed = _extract_json_from_response(result)
        
        # Convert to ParsedEvent
        return _build_parsed_event(parsed, text, reference_time)
        
    except Exception as e:
        # On any error, return fallback with low confidence
        return _create_fallback_event(text, reference_time, f"Parse error: {e}")


def _call_llm_parser(user_prompt: str) -> Optional[str]:
    """Call Kimi API to parse the event text."""
    data = {
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 1024,
        "temperature": 0.1  # Low temperature for consistent parsing
    }
    
    headers = {
        "x-api-key": KIMI_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{KIMI_BASE_URL}/v1/messages",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content_blocks = result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    return block.get("text", "")
        else:
            print(f"LLM API error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("LLM API timeout")
        return None
    except Exception as e:
        print(f"LLM API exception: {e}")
        return None
    
    return None


def _extract_json_from_response(text: str) -> dict:
    """Extract JSON object from LLM response text."""
    # Try to find JSON in markdown code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    match = re.search(json_pattern, text, re.DOTALL)
    
    if match:
        json_str = match.group(1)
    else:
        # Try to find bare JSON object
        json_pattern = r'(\{[\s\S]*\})'
        match = re.search(json_pattern, text)
        if match:
            json_str = match.group(1)
        else:
            # No JSON found, try to parse as-is
            json_str = text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Text was: {json_str[:500]}")
        return {}


def _build_parsed_event(parsed: dict, raw_text: str, reference_time: datetime) -> ParsedEvent:
    """Build a ParsedEvent from parsed JSON data."""
    
    # Parse start time
    start_time = _parse_datetime(parsed.get("start_time"), reference_time)
    if start_time is None:
        start_time = reference_time
    
    # Parse end time
    end_time = None
    end_str = parsed.get("end_time")
    if end_str:
        end_time = _parse_datetime(end_str, reference_time)
    
    # Get duration
    duration = parsed.get("duration_minutes")
    
    # If we have end_time but no duration, calculate it
    if end_time and not duration:
        duration = int((end_time - start_time).total_seconds() / 60)
    
    # Build the event
    return ParsedEvent(
        title=parsed.get("title", "Untitled Event"),
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration,
        category=parsed.get("category"),
        is_recurring=parsed.get("is_recurring", False),
        recurrence_rule=parsed.get("recurrence_rule"),
        confidence=parsed.get("confidence", 0.5),
        raw_text=raw_text,
        ambiguity_notes=parsed.get("ambiguity_notes", [])
    )


def _parse_datetime(dt_str: Optional[str], reference_time: datetime) -> Optional[datetime]:
    """Parse a datetime string, using reference_time for context."""
    if not dt_str:
        return None
    
    try:
        # Try ISO format first
        if 'T' in dt_str or 'Z' in dt_str:
            # Handle Z suffix
            dt_str = dt_str.replace('Z', '+00:00')
            return datetime.fromisoformat(dt_str)
    except:
        pass
    
    try:
        # Use dateutil parser as fallback
        return date_parser.parse(dt_str, default=reference_time)
    except:
        pass
    
    return None


def _create_fallback_event(text: str, reference_time: datetime, error_note: str = "") -> ParsedEvent:
    """Create a low-confidence fallback event when parsing fails."""
    notes = ["Using fallback defaults due to parsing failure"]
    if error_note:
        notes.append(error_note)
    
    # Default: tomorrow at 9am for 1 hour
    tomorrow_9am = reference_time.replace(hour=9, minute=0, second=0, microsecond=0)
    tomorrow_9am = tomorrow_9am + timedelta(days=1)
    
    return ParsedEvent(
        title=text,  # Use the raw text as title
        start_time=tomorrow_9am,
        duration_minutes=60,
        category="general",
        confidence=0.3,
        raw_text=text,
        ambiguity_notes=notes
    )


def suggest_clarification(parsed: ParsedEvent, original_text: str) -> ParseSuggestion:
    """
    Generate clarification questions for ambiguous events.
    
    Args:
        parsed: The parsed event with low confidence
        original_text: Original user input
        
    Returns:
        ParseSuggestion with questions for the user
    """
    questions = []
    
    # Check what was ambiguous
    if parsed.confidence < 0.7:
        if parsed.start_time.hour == 9 and parsed.start_time.minute == 0:
            questions.append(f"Did you mean {parsed.start_time.strftime('%I:%M %p')}? I assumed 9am.")
        
        if parsed.duration_minutes == 60:
            questions.append("How long is this event? I assumed 1 hour.")
    
    if not parsed.end_time and not parsed.duration_minutes:
        questions.append("When does this event end?")
    
    if not parsed.category:
        questions.append("What category is this? (work, personal, kids_club, staff, deadline, projects)")
    
    # Add ambiguity notes as context
    for note in parsed.ambiguity_notes:
        if "assumed" in note.lower() or "default" in note.lower():
            questions.append(f"Note: {note}")
    
    return ParseSuggestion(
        original_text=original_text,
        suggested_title=parsed.title,
        suggested_start=parsed.start_time,
        suggested_end=parsed.end_time,
        questions=questions,
        clarification_needed=len(questions) > 0
    )


def batch_parse(texts: List[str], reference_time: Optional[datetime] = None) -> List[ParsedEvent]:
    """
    Parse multiple event texts in batch.
    
    Args:
        texts: List of natural language event descriptions
        reference_time: Optional reference time for relative dates
        
    Returns:
        List of ParsedEvent objects
    """
    return [parse_event(text, reference_time) for text in texts]


# Common patterns for quick rule-based parsing (before LLM call)
QUICK_PATTERNS = {
    r'\btomorrow\b': lambda m: timedelta(days=1),
    r'\btoday\b': lambda m: timedelta(days=0),
    r'\bnext week\b': lambda m: timedelta(weeks=1),
    r'\bin (\d+) minutes?\b': lambda m: timedelta(minutes=int(m.group(1))),
    r'\bin (\d+) hours?\b': lambda m: timedelta(hours=int(m.group(1))),
    r'\bin (\d+) days?\b': lambda m: timedelta(days=int(m.group(1))),
}


def quick_time_parse(text: str, reference_time: Optional[datetime] = None) -> Optional[datetime]:
    """
    Quick rule-based time parsing for simple cases.
    
    Returns None if no quick match, allowing fallback to LLM.
    """
    if reference_time is None:
        reference_time = datetime.now()
    
    text_lower = text.lower()
    
    for pattern, delta_fn in QUICK_PATTERNS.items():
        match = re.search(pattern, text_lower)
        if match:
            delta = delta_fn(match)
            return reference_time + delta
    
    return None

# Calendar Skill — Aggressive Intent Detection for CK Calendar

> Natural language calendar management with liberal parsing and light confirmation.

---

## Skill Metadata

| Property | Value |
|----------|-------|
| **Name** | calendar |
| **Description** | Detect calendar intents in conversation, parse natural language into structured events, and interact with the CK Calendar database |
| **Version** | 1.0.0 |
| **Author** | Kimi (Hari) |
| **Dependencies** | dateutil, sqlite3 |

---

## Triggers — When to Activate

**ALWAYS scan for calendar intents in EVERY message.** This is a high-priority skill that runs on every conversation.

### Primary Triggers (High Confidence)

These patterns indicate a calendar intent with >90% confidence:

| Pattern | Examples |
|---------|----------|
| Time + Event | "Meeting at 3pm", "Lunch tomorrow at noon" |
| Schedule verbs | "remind me to...", "add to my calendar", "schedule" |
| Query phrases | "what's on my calendar", "when am I free", "do I have anything" |
| Modify verbs | "move my meeting", "cancel lunch", "reschedule" |

### Secondary Triggers (Medium Confidence)

These warrant parsing but need confirmation:

| Pattern | Examples |
|---------|----------|
| Date references | "Thursday", "next week", "March 15th" |
| Time expressions | "morning", "afternoon", "after work" |
| Activity nouns | "dentist", "conference", "training" |

### Ambiguous Triggers (Low Confidence)

Mention for context but don't auto-act:

| Pattern | Examples | Action |
|---------|----------|--------|
| Past tense | "I had a meeting yesterday" | Note only |
| Hypothetical | "if I had a meeting..." | Ignore |
| Third party | "John has a dentist appointment" | Ask if relevant to you |

---

## Detection Philosophy: Aggressive > Conservative

**Core principle: Better false positives than misses.**

- If it *might* be a calendar event → Parse it
- If parsing succeeds → Confirm lightly or just do it
- If you're unsure → Ask a clarifying question (not "should I add this?")

### Confidence Levels

| Level | Threshold | Behavior |
|-------|-----------|----------|
| **HIGH** | >85% | Just do it. Add the event without confirmation. |
| **MEDIUM** | 50-85% | Add with a note. "Added to your calendar (category: Work — adjust if wrong)." |
| **LOW** | <50% | Don't add. Note for context only: "Sounds like you might have something scheduled — want me to add it?" |

---

## Categories

Every event should have a category. Auto-suggest based on content, but allow free-form.

### Standard Categories

| Category | Description | Trigger Words |
|----------|-------------|---------------|
| **Work** | Kinawa meetings, deadlines, director responsibilities | meeting, director, school, okemos, pd day, deadline, report |
| **Personal** | Appointments, family, non-work life | dentist, doctor, family, appointment, personal |
| **Kids Club** | Field trips, activities, kid-facing events | field trip, activity, kids, club kinawa, children |
| **Staff** | Training, evaluations, coverage planning | staff, training, evaluation, cpr, first aid, coverage |
| **Deadlines** | Licensing, forms, submissions | license, form, due, submission, expires, renewal |
| **Projects/OpenClaw** | Builds, research, technical work, BTG queue | build, deploy, code, openclaw, btg, project, research |

### Category Selection Logic

```python
def suggest_category(text: str) -> str:
    """Analyze text and suggest best category match."""
    text_lower = text.lower()
    
    # Check for explicit category mentions
    if any(word in text_lower for word in ["deadline", "due", "expires", "renewal"]):
        return "Deadlines"
    if any(word in text_lower for word in ["staff", "training", "evaluation", "cpr"]):
        return "Staff"
    if any(word in text_lower for word in ["field trip", "activity", "kids"]):
        return "Kids Club"
    if any(word in text_lower for word in ["build", "deploy", "code", "openclaw"]):
        return "Projects/OpenClaw"
    if any(word in text_lower for word in ["meeting", "director", "school", "pd day"]):
        return "Work"
    if any(word in text_lower for word in ["dentist", "doctor", "family", "personal"]):
        return "Personal"
    
    # Default to Work for ambiguous cases during work hours
    return "Work"
```

---

## Parsing Strategy: Liberal + Confirm Lightly

### What to Parse

Parse liberally — extract whatever you can:

| Component | Parse Strategy | Example |
|-----------|---------------|---------|
| **Date** | Relative dates, weekdays, absolute dates | "tomorrow", "Thursday", "March 15" |
| **Time** | Explicit times, relative times, ranges | "3pm", "noon", "10-11am", "after work" |
| **Duration** | Implicit or explicit | "1 hour meeting", "all day" |
| **Title** | Main activity noun phrase | "Staff meeting", "Dentist appointment" |
| **Location** | Prepositional phrases | "at Kinawa", "in the conference room" |
| **Description** | Everything else | "bring the red binder" |

### Relative Date Resolution

```python
RELATIVE_DATES = {
    "today": 0,
    "tomorrow": 1,
    "tonight": 0,  # same day, evening
    "next week": 7,
    "next month": 30,  # approximate
    "this weekend": lambda d: (5 - d.weekday()) % 7,  # Saturday
    "next weekend": lambda d: (12 - d.weekday()) % 7,  # Next Saturday
}

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, 
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
}
```

### Time Parsing Patterns

```python
TIME_PATTERNS = [
    r'(\d{1,2}):?(\d{2})?\s*(am|pm)?',  # 3pm, 3:30pm, 15:00
    r'noon': 12:00,
    r'midnight': 00:00,
    r'morning': 09:00,  # default
    r'afternoon': 14:00,
    r'evening': 18:00,
    r'after work': 17:00,
    r'all day': None,  # all-day event flag
]
```

---

## CK Calendar Database Integration

### Database Location

```python
CALENDAR_DB_PATH = "/home/openclaw/.openclaw/workspace/data/calendar.db"
```

### Core Schema

```sql
-- Events table
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    all_day BOOLEAN DEFAULT 0,
    category TEXT DEFAULT 'Work',
    location TEXT,
    recurrence_rule TEXT,  -- RRULE format
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Categories table (for validation/suggestions)
CREATE TABLE categories (
    name TEXT PRIMARY KEY,
    color TEXT,  -- hex color for UI
    description TEXT
);
```

### API Functions

```python
# calendar_api.py

def add_event(
    title: str,
    start_time: datetime,
    end_time: datetime = None,
    category: str = "Work",
    description: str = "",
    location: str = "",
    all_day: bool = False
) -> int:
    """Add a new event. Returns event ID."""
    pass

def get_events(
    start: datetime = None,
    end: datetime = None,
    category: str = None,
    search: str = None
) -> List[Event]:
    """Query events with filters."""
    pass

def find_event_by_time(
    when: datetime,
    fuzzy: bool = True
) -> Optional[Event]:
    """Find event at or near a specific time."""
    pass

def update_event(
    event_id: int,
    **kwargs
) -> bool:
    """Update event fields."""
    pass

def delete_event(event_id: int) -> bool:
    """Delete an event."""
    pass

def search_events(query: str, limit: int = 10) -> List[Event]:
    """Full-text search across titles and descriptions."""
    pass
```

---

## Response Patterns

### Adding Events

**High confidence:**
> ✅ Added "Staff meeting" to your calendar for Thursday at 3pm (Work).

**Medium confidence:**
> ✅ Added "Lunch with John" for tomorrow at noon. I categorized it as Personal — let me know if that's wrong.

**Low confidence (clarify instead of add):**
> I heard something about Thursday at 3pm — is that a meeting you want on your calendar?

### Querying Events

**Today:**
> 📅 **Today (March 4)**
> • 10:00 AM — Director meeting (Work)
> • 2:30 PM — Staff training (Staff)
> • 4:00 PM — Pick up kids (Personal)

**Empty day:**
> 📅 Nothing on your calendar for tomorrow. You're free!

### Modifying Events

**Move:**
> ✅ Moved "Staff meeting" from 2pm to 3pm on Thursday.

**Cancel:**
> 🗑️ Cancelled "Lunch" for tomorrow at noon.

**Not found:**
> I don't see anything on your calendar around 2pm today. Want me to add something?

---

## Cross-Session Behavior

### This Skill Must Be Active In:

- ✅ Direct messages with Adam
- ✅ All group chats
- ✅ Any session where natural language is used

### What to Remember:

- Last calendar interaction timestamp
- Recent categories used (for better suggestions)
- Upcoming events context (for "move my meeting" resolution)

### What to Surface:

- When Adam mentions being busy → check calendar and confirm
- When Adam says "I have..." → parse and potentially add
- When Adam asks about free time → query and respond

---

## Code Examples

### Example 1: Detect and Parse

```python
from calendar.nlp_parser import parse_calendar_intent

message = "I have a meeting Thursday at 10"
result = parse_calendar_intent(message)

# result:
# {
#   "intent": "add_event",
#   "confidence": 0.92,
#   "title": "Meeting",
#   "date": "2026-03-06",  # upcoming Thursday
#   "time": "10:00",
#   "category": "Work",
#   "action": "auto_add"  # high confidence
# }
```

### Example 2: Query and Format

```python
from calendar.calendar_api import get_events
from datetime import datetime, timedelta

today = datetime.now()
tomorrow = today + timedelta(days=1)
events = get_events(start=today, end=tomorrow)

# Format response
if events:
    lines = [f"📅 **Today ({today.strftime('%B %d')})**"]
    for e in events:
        time_str = e.start_time.strftime('%I:%M %p').lstrip('0')
        lines.append(f"• {time_str} — {e.title} ({e.category})")
    response = "\n".join(lines)
else:
    response = f"📅 Nothing on your calendar for today. You're free!"
```

### Example 3: Find and Update

```python
from calendar.calendar_api import find_event_by_time, update_event
from datetime import datetime

# "Move my 2pm to 3pm"
today_2pm = datetime.now().replace(hour=14, minute=0, second=0)
event = find_event_by_time(today_2pm, fuzzy=True)

if event:
    new_time = today_2pm.replace(hour=15)
    update_event(event.id, start_time=new_time)
    return f"✅ Moved \"{event.title}\" to 3pm."
else:
    return "I don't see anything on your calendar at 2pm."
```

### Example 4: Search and Delete

```python
from calendar.calendar_api import search_events, delete_event

# "Cancel lunch tomorrow"
events = search_events("lunch", limit=5)
tomorrow_events = [e for e in events if is_tomorrow(e.start_time)]

if len(tomorrow_events) == 1:
    delete_event(tomorrow_events[0].id)
    return f"🗑️ Cancelled \"{tomorrow_events[0].title}\" for tomorrow."
elif len(tomorrow_events) > 1:
    return "I found multiple lunch events tomorrow. Which one: " + \
           " or ".join([f"{e.start_time.strftime('%I:%M %p')} ({e.title})" for e in tomorrow_events])
else:
    return "I don't see a lunch event on your calendar for tomorrow."
```

---

## Error Handling

### Common Failures

| Failure | Response |
|---------|----------|
| Parse ambiguity | "I heard 'Thursday' but there's one this week and one next week — which did you mean?" |
| Time missing | "You mentioned a meeting Thursday — what time?" |
| Event not found | "I don't see anything at that time. Want me to add it instead?" |
| Database error | "Having trouble with the calendar right now. I'll try again in a moment." |

### Recovery Patterns

- Always offer an alternative action
- Never just fail silently
- Log errors for debugging
- Fall back to asking user for clarification

---

## Integration Points

### With AGENTS.md

- Add calendar detection to session startup checklist
- Include calendar query in heartbeat checks
- Reference CK Calendar as primary scheduling source

### With SOUL.md

- Calendar-aware behavior is part of "being genuinely helpful"
- Pattern recognition: notice scheduling patterns over time
- Proactive: suggest calendar checks when appropriate

### With BTG_QUEUE.md

- BTG queue items with dates should auto-suggest calendar entries
- Project deadlines should sync to calendar

---

## Testing Checklist

Before marking this skill complete:

- [ ] Can detect "I have X at Y" in any conversation
- [ ] Can parse relative dates (tomorrow, next week)
- [ ] Can parse time expressions (3pm, noon, morning)
- [ ] Can query and format today's events
- [ ] Can find and move events by time reference
- [ ] Can search and delete by description
- [ ] Handles ambiguous cases gracefully
- [ ] Works across different group contexts
- [ ] High confidence events auto-add
- [ ] Medium confidence events add with note
- [ ] Low confidence events ask for clarification

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-04 | Initial skill definition for Wave 4a |

---

*This skill ensures calendar intent detection runs in ALL sessions, across ALL groups. Be aggressive. Parse liberally. Confirm lightly.*

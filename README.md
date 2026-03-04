# Calendar Primary

Natural language calendar management for OpenClaw. No slash commands, no Google Calendar required. Just talk, and it goes on your calendar.

## Philosophy

**Bias toward action.** Better too much on the calendar than forgotten commitments.

## Features

- 🗣️ **Natural language** — "I have a meeting Thursday at 10"
- 🤖 **AI-powered parsing** — LLM extracts times, dates, categories automatically
- 🔄 **Recurring events** — RRULE support (daily, weekly, monthly, yearly)
- 📱 **Telegram integration** — Chat with your calendar
- 📤 **ICS export** — Subscribe in any calendar app
- 🧠 **Cross-session awareness** — Works in all OpenClaw groups

## Quick Start

### 1. Environment Setup

```bash
export CALENDAR_TELEGRAM_BOT_TOKEN="your_bot_token"
export KIMI_API_KEY="your_kimi_key"  # Optional, for better parsing
export CALENDAR_DB_PATH="./calendar.db"
```

### 2. Run the Bot

```bash
cd calendar
python3 bot_runner.py
```

### 3. Start Chatting

- "I have a meeting Thursday at 10"
- "Lunch with Sarah tomorrow at noon"
- "What's on my calendar today?"
- "Move my 2pm to 3pm"
- "Cancel that lunch tomorrow"

## Project Structure

```
calendar/           # Core system
├── schema.sql      # SQLite schema
├── models.py       # Event dataclasses
├── calendar_api.py # CRUD operations
├── recurrence.py   # RRULE expansion
├── ics_*.py        # ICS export/import/server
└── telegram_*.py   # Telegram integration

ck_calendar/        # NLP & intent detection
├── nlp_parser.py
├── intent_detector.py
└── parsed_event.py

skills/calendar/    # OpenClaw skill definition
├── SKILL.md
└── examples.md
```

## Categories

- **Work** — Kinawa meetings, deadlines
- **Personal** — appointments, family
- **Kids Club** — field trips, activities
- **Staff** — training, evaluations
- **Deadlines** — licensing, forms
- **Projects/OpenClaw** — builds, research

## API Usage

```python
from calendar.calendar_api import add_event, get_today_events
from datetime import datetime

# Add event
event = add_event(
    title="Staff Meeting",
    start_time=datetime(2026, 3, 5, 14, 0),
    category="Work"
)

# Get today's events
today = get_today_events()
```

## ICS Subscription

Subscribe to your calendar:
```
http://your-server:port/calendar/export.ics
http://your-server:port/calendar/Work.ics
```

## Built With

- Python 3.11+
- SQLite
- python-dateutil (RRULE)
- python-telegram-bot
- Kimi K2.5 (NLP parsing)

## License

MIT

## Related

- [OpenClaw](https://github.com/openclaw/openclaw)
- [Kinawa Command Center](https://clubkinawa.net)

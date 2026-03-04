# Calendar Primary — Quickstart

## 1) Setup

From workspace root:

```bash
cd /home/openclaw/.openclaw/workspace
python3 -m pip install python-dateutil requests flask
```

Initialize database schema:

```bash
python3 - <<'PY'
from calendar import init_db
init_db()
print('calendar.db initialized')
PY
```

---

## 2) Required / Optional Environment Variables

### Required to run Telegram bot
- `CALENDAR_TELEGRAM_BOT_TOKEN` *(or `TELEGRAM_BOT_TOKEN`)*

### Optional
- `CALENDAR_DB_PATH` (default: `/home/openclaw/.openclaw/workspace/calendar.db`)
- `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated allowlist)
- `TELEGRAM_CHAT_ID` (single chat id fallback)
- `CALENDAR_BOT_LOG_LEVEL` (default: `INFO`)
- `KIMI_API_KEY` (enables LLM NLP parser; without it bot uses fallback parser)
- `CALENDAR_API_TOKEN` (protects ICS endpoints if running ICS server)

---

## 3) Start the Telegram Bot

```bash
export CALENDAR_TELEGRAM_BOT_TOKEN="<your-bot-token>"
# optional:
# export TELEGRAM_ALLOWED_CHAT_IDS="123456789,-1001234567890"

python3 -m calendar.bot_runner
```

---

## 4) Basic Usage Examples (natural language)

Send messages like:
- `Add staff meeting tomorrow at 3pm`
- `What's on my calendar today?`
- `Move my 2pm to 3pm`
- `Cancel tomorrow lunch`

Programmatic usage:

```python
from datetime import datetime, timedelta
from calendar.calendar_api import add_event, get_events

start = datetime.now() + timedelta(days=1)
end = start + timedelta(hours=1)

event = add_event("Director meeting", start, end, category="Work")
print(event.id)

for e in get_events(start=start, end=end):
    print(e.title, e.start_time)
```

ICS export usage:

```python
from calendar.calendar_api import get_events
from calendar.ics_export import export_events

events = get_events()
ics_text = export_events(events)
open("calendar.ics", "w").write(ics_text)
```

---

## 5) (Optional) Run ICS Server

```bash
python3 -m calendar.ics_server --host 0.0.0.0 --port 5005
```

Endpoints:
- `/health`
- `/calendar/export.ics`
- `/calendar/<category>.ics`
- `/calendar/events.json`

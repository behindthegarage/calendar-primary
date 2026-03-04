"""Natural-language Telegram bot integration for Calendar Primary (Wave 2a)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional
from uuid import uuid4

import requests
from dateutil import parser as date_parser

from ck_calendar.intent_detector import detect_calendar_intent
from ck_calendar.nlp_parser import parse_event, suggest_clarification
from ck_calendar.parsed_event import ParsedEvent

try:
    from .db import get_db, init_db
    from .models import Event
    from .telegram_formatters import (
        format_confirmation,
        format_event,
        format_event_list,
        format_suggestion,
    )
except ImportError:  # pragma: no cover - direct script fallback
    from calendar.db import get_db, init_db
    from calendar.models import Event
    from calendar.telegram_formatters import (
        format_confirmation,
        format_event,
        format_event_list,
        format_suggestion,
    )


logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "my",
    "that",
    "the",
    "a",
    "an",
    "to",
    "for",
    "at",
    "on",
    "this",
    "next",
    "today",
    "tomorrow",
    "week",
    "calendar",
    "event",
}


def _now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def _has_keyword(text: str, words: Iterable[str]) -> bool:
    lower = text.lower()
    return any(word in lower for word in words)


def _normalize_title(text: str) -> str:
    clean = re.sub(
        r"^(please\s+)?(add|schedule|book|set up|create|put|remind me to)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    return clean.strip(" .,!?") or "Untitled Event"


def _extract_duration_minutes(text: str) -> Optional[int]:
    lower = text.lower()

    match = re.search(r"\bfor\s+(\d+)\s*(minutes?|mins?)\b", lower)
    if match:
        return int(match.group(1))

    match = re.search(r"\bfor\s+(\d+)\s*(hours?|hrs?)\b", lower)
    if match:
        return int(match.group(1)) * 60

    if "half hour" in lower:
        return 30

    return None


def _extract_explicit_time(text: str) -> Optional[tuple[int, int]]:
    lower = text.lower()

    if "noon" in lower:
        return (12, 0)
    if "midnight" in lower:
        return (0, 0)

    ampm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lower)
    if ampm:
        hour = int(ampm.group(1))
        minute = int(ampm.group(2) or 0)
        mer = ampm.group(3)
        if mer == "am" and hour == 12:
            hour = 0
        elif mer == "pm" and hour != 12:
            hour += 12
        return (hour, minute)

    hhmm = re.search(r"\b(\d{1,2}):(\d{2})\b", lower)
    if hhmm:
        return int(hhmm.group(1)), int(hhmm.group(2))

    return None


def _parse_datetime_guess(text: str, base: Optional[datetime] = None) -> datetime:
    base = (base or _now()).replace(second=0, microsecond=0)
    working = text
    lower = working.lower()

    explicit_time = _extract_explicit_time(lower)

    # Replace common relative tokens with concrete dates to improve parser reliability.
    if "tomorrow" in lower:
        target = (base + timedelta(days=1)).date().isoformat()
        working = re.sub(r"\btomorrow\b", target, working, flags=re.IGNORECASE)
    if "today" in lower:
        target = base.date().isoformat()
        working = re.sub(r"\btoday\b", target, working, flags=re.IGNORECASE)
    if "next week" in lower:
        target = (base + timedelta(days=7)).date().isoformat()
        working = re.sub(r"\bnext\s+week\b", target, working, flags=re.IGNORECASE)

    parsed = date_parser.parse(working, fuzzy=True, default=base).replace(second=0, microsecond=0)

    if explicit_time:
        parsed = parsed.replace(hour=explicit_time[0], minute=explicit_time[1])

    return parsed


def _fallback_parse_event(text: str, reference_time: Optional[datetime] = None) -> ParsedEvent:
    reference_time = reference_time or _now()

    try:
        start = _parse_datetime_guess(text, base=reference_time)
    except Exception:
        start = (reference_time + timedelta(days=1)).replace(hour=9, minute=0)

    duration_minutes = _extract_duration_minutes(text) or 60

    category = "Work"
    lower = text.lower()
    if any(word in lower for word in ("dentist", "doctor", "family", "birthday")):
        category = "Personal"
    elif any(word in lower for word in ("staff", "evaluation", "coverage", "training")):
        category = "Staff"
    elif any(word in lower for word in ("deadline", "due", "submit", "licensing")):
        category = "Deadlines"
    elif any(word in lower for word in ("project", "build", "openclaw", "btg")):
        category = "Projects/OpenClaw"

    return ParsedEvent(
        title=_normalize_title(text),
        start_time=start,
        end_time=start + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
        category=category,
        confidence=0.45,
        raw_text=text,
        ambiguity_notes=["Used fallback parser (LLM unavailable or failed)."],
    )


def _parsed_to_event(parsed: ParsedEvent) -> Event:
    start_time = parsed.start_time.replace(second=0, microsecond=0)

    if parsed.end_time:
        end_time = parsed.end_time.replace(second=0, microsecond=0)
    elif parsed.duration_minutes:
        end_time = start_time + timedelta(minutes=parsed.duration_minutes)
    else:
        end_time = start_time + timedelta(hours=1)

    now = _now()

    return Event(
        id=f"evt_{uuid4().hex[:12]}",
        title=(parsed.title or "Untitled Event").strip(),
        description=None,
        start_time=start_time,
        end_time=end_time,
        category=(parsed.category or "Work").replace("_", " ").title(),
        rrule=parsed.recurrence_rule,
        created_at=now,
        updated_at=now,
        is_recurring=bool(parsed.is_recurring or parsed.recurrence_rule),
        parent_event_id=None,
    )


def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in raw if token not in _STOP_WORDS and len(token) > 1}


def _extract_target_phrase(text: str) -> str:
    cleaned = re.sub(
        r"\b(cancel|delete|remove|call off|move|reschedule|change|update|shift)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+to\s+.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .,!?")


def _extract_move_parts(text: str) -> tuple[str, str]:
    match = re.search(
        r"\b(?:move|reschedule|change|update|shift)\b\s+(?P<target>.+?)\s+\b(?:to|for)\b\s+(?P<new>.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return text, ""
    return match.group("target").strip(), match.group("new").strip()


def _contains_date_hint(text: str) -> bool:
    lower = text.lower()
    if any(token in lower for token in ("today", "tomorrow", "next week", "this week")):
        return True

    if re.search(r"\b(mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday|sun|sunday)\b", lower):
        return True

    if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", lower):
        return True

    if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", lower):
        return True

    return False


def _range_for_query(text: str) -> tuple[datetime, datetime, str]:
    now = _now()
    lower = text.lower()

    start_of_today = now.replace(hour=0, minute=0)

    if "today" in lower:
        return start_of_today, start_of_today + timedelta(days=1), "Today"

    if "tomorrow" in lower:
        start = start_of_today + timedelta(days=1)
        return start, start + timedelta(days=1), "Tomorrow"

    if "this week" in lower:
        start = start_of_today - timedelta(days=start_of_today.weekday())
        return start, start + timedelta(days=7), "This week"

    if "next week" in lower:
        start = (start_of_today - timedelta(days=start_of_today.weekday())) + timedelta(days=7)
        return start, start + timedelta(days=7), "Next week"

    match = re.search(r"next\s+(\d+)\s+days?", lower)
    if match:
        days = max(1, int(match.group(1)))
        return now, now + timedelta(days=days), f"Next {days} days"

    match = re.search(r"next\s+(\d+)\s+weeks?", lower)
    if match:
        weeks = max(1, int(match.group(1)))
        return now, now + timedelta(days=weeks * 7), f"Next {weeks} weeks"

    return now, now + timedelta(days=7), "Coming up"


def _range_hint_for_text(text: str) -> tuple[datetime, datetime]:
    now = _now()
    lower = text.lower()
    start = now - timedelta(days=1)
    end = now + timedelta(days=30)

    if "today" in lower:
        day = now.replace(hour=0, minute=0)
        return day, day + timedelta(days=1)

    if "tomorrow" in lower:
        day = now.replace(hour=0, minute=0) + timedelta(days=1)
        return day, day + timedelta(days=1)

    if "next week" in lower:
        day = now.replace(hour=0, minute=0)
        week_start = (day - timedelta(days=day.weekday())) + timedelta(days=7)
        return week_start, week_start + timedelta(days=7)

    return start, end


def _score_candidate(query: str, event: Event) -> float:
    q_tokens = _tokenize(query)
    e_tokens = _tokenize(event.title)

    score = 0.0
    if q_tokens and e_tokens:
        overlap = len(q_tokens & e_tokens)
        score += overlap / max(len(q_tokens), 1)

    query_lower = query.lower()
    if query_lower and query_lower in event.title.lower():
        score += 0.35

    # time mention boost (e.g., "my 2pm")
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", query_lower)
    if time_match:
        hh = int(time_match.group(1))
        mm = int(time_match.group(2) or 0)
        mer = time_match.group(3)
        if mer == "am" and hh == 12:
            hh = 0
        if mer == "pm" and hh != 12:
            hh += 12
        if event.start_time.hour == hh and event.start_time.minute == mm:
            score += 0.45

    return score


class CalendarTelegramBot:
    """Natural-language-first Telegram bot for calendar CRUD."""

    def __init__(
        self,
        token: str,
        db_path: Optional[str] = None,
        allowed_chat_ids: Optional[set[int]] = None,
        poll_timeout: int = 25,
    ):
        self.token = token.strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.poll_timeout = poll_timeout
        self.allowed_chat_ids = allowed_chat_ids or set()
        self.db_path = db_path

        if db_path:
            init_db(db_path=db_path)
        else:
            init_db()

    # ------------------------------------------------------------------
    # Public handler surface
    # ------------------------------------------------------------------
    def process_text(self, text: str, chat_id: Optional[int] = None, user_id: Optional[int] = None) -> str:
        text = (text or "").strip()
        if not text:
            return "Say it naturally: add, move, cancel, or ask what's coming up."

        intent = detect_calendar_intent(text)

        if intent.should_query():
            return self._handle_query(text)

        if intent.suggested_action == "modify" and intent.confidence >= 0.45:
            if self._is_delete_intent(text):
                return self._handle_delete(text)
            return self._handle_modify(text)

        # Bias toward action: add first when likely calendar mention.
        if intent.suggested_action == "add" or intent.is_calendar_mention:
            return self._handle_add(text)

        return "Got it. If you want calendar help, just say it naturally (e.g., 'lunch tomorrow at noon')."

    def handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        text = message.get("text")
        if not text:
            return

        chat = message.get("chat") or {}
        chat_id = int(chat.get("id")) if chat.get("id") is not None else None
        user_id = (message.get("from") or {}).get("id")

        if self.allowed_chat_ids and chat_id not in self.allowed_chat_ids:
            logger.debug("Ignoring chat_id=%s not in allow list", chat_id)
            return

        reply = self.process_text(text=text, chat_id=chat_id, user_id=user_id)
        if chat_id is not None:
            self.send_message(chat_id, reply)

    def run_forever(self) -> None:
        logger.info("CalendarTelegramBot polling started")
        offset: Optional[int] = None

        while True:
            try:
                updates = self._get_updates(offset=offset, timeout=self.poll_timeout)
                for upd in updates:
                    offset = int(upd["update_id"]) + 1
                    self.handle_update(upd)
            except KeyboardInterrupt:
                logger.info("CalendarTelegramBot stopped by keyboard interrupt")
                break
            except Exception:
                logger.exception("Polling loop error")
                time.sleep(2)

    # ------------------------------------------------------------------
    # Core conversation handlers
    # ------------------------------------------------------------------
    def _handle_add(self, text: str) -> str:
        parsed = self._parse_event_with_fallback(text)
        event = _parsed_to_event(parsed)
        self._insert_event(event)

        confirmation = format_confirmation(event, "add")

        if parsed.confidence < 0.5:
            suggestion = suggest_clarification(parsed, text)
            return f"{confirmation}\n{format_suggestion(suggestion)}"

        return confirmation

    def _handle_query(self, text: str) -> str:
        start, end, title = _range_for_query(text)
        events = self._get_events_between(start, end)
        return format_event_list(events, title)

    def _handle_delete(self, text: str) -> str:
        target_phrase = _extract_target_phrase(text)
        start, end = _range_hint_for_text(text)
        matches = self._find_candidate_events(target_phrase, start=start, end=end)

        if not matches:
            return "I couldn't find a matching event to remove."

        top = matches[0]
        if len(matches) > 1 and (matches[0][0] - matches[1][0]) < 0.2:
            ambiguous = [evt for _, evt in matches[:3]]
            return format_event_list(ambiguous, "I found a few possible matches:")

        event = top[1]
        self._delete_event(event.id)
        return format_confirmation(event, "delete")

    def _handle_modify(self, text: str) -> str:
        target_phrase, new_phrase = _extract_move_parts(text)
        start, end = _range_hint_for_text(target_phrase)
        matches = self._find_candidate_events(target_phrase, start=start, end=end)

        if not matches:
            return "I couldn't find which event to update."

        if len(matches) > 1 and (matches[0][0] - matches[1][0]) < 0.2:
            ambiguous = [evt for _, evt in matches[:3]]
            return format_event_list(ambiguous, "I found multiple events. Which one should I move?")

        current = matches[0][1]

        if not new_phrase:
            return f"Tell me where to move it: {format_event(current)}"

        updated = self._apply_move(current, new_phrase)
        self._update_event(updated)
        return format_confirmation(updated, "update")

    # ------------------------------------------------------------------
    # Parse + transform helpers
    # ------------------------------------------------------------------
    def _parse_event_with_fallback(self, text: str) -> ParsedEvent:
        try:
            return parse_event(text)
        except Exception as exc:
            logger.warning("parse_event failed (%s), using fallback parser", exc)
            return _fallback_parse_event(text)

    def _apply_move(self, event: Event, new_phrase: str) -> Event:
        # Parse explicit date phrases relative to "now", but time-only phrases
        # relative to the event's existing date.
        parse_base = _now() if _contains_date_hint(new_phrase) else event.start_time

        new_start = None
        try:
            new_start = _parse_datetime_guess(new_phrase, base=parse_base)
        except Exception:
            pass

        duration = None
        if event.end_time:
            duration = event.end_time - event.start_time

        if new_start is None:
            # fallback: title-only update, keep times
            new_title = new_phrase.strip()
            if not new_title:
                return event
            return replace(event, title=new_title, updated_at=_now())

        new_end = None
        if duration:
            new_end = new_start + duration

        return replace(
            event,
            start_time=new_start,
            end_time=new_end,
            updated_at=_now(),
        )

    def _is_delete_intent(self, text: str) -> bool:
        return _has_keyword(text, ("cancel", "delete", "remove", "call off"))

    # ------------------------------------------------------------------
    # Telegram transport
    # ------------------------------------------------------------------
    def _get_updates(self, offset: Optional[int], timeout: int) -> list[dict[str, Any]]:
        payload = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset

        res = requests.get(f"{self.base_url}/getUpdates", params=payload, timeout=timeout + 5)
        res.raise_for_status()
        body = res.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {body}")
        return body.get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        res = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=15)
        res.raise_for_status()

    # ------------------------------------------------------------------
    # DB operations
    # ------------------------------------------------------------------
    def _get_conn(self):
        if self.db_path:
            return get_db(self.db_path)
        return get_db()

    def _insert_event(self, event: Event) -> None:
        sql = """
        INSERT INTO events (
            id, title, description, start_time, end_time,
            category, rrule, created_at, updated_at, is_recurring, parent_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    event.id,
                    event.title,
                    event.description,
                    event.start_time.isoformat(sep=" "),
                    event.end_time.isoformat(sep=" ") if event.end_time else None,
                    event.category,
                    event.rrule,
                    event.created_at.isoformat(sep=" "),
                    event.updated_at.isoformat(sep=" "),
                    int(event.is_recurring),
                    event.parent_event_id,
                ),
            )
            conn.commit()

    def _update_event(self, event: Event) -> None:
        sql = """
        UPDATE events
        SET
            title = ?,
            description = ?,
            start_time = ?,
            end_time = ?,
            category = ?,
            rrule = ?,
            is_recurring = ?,
            parent_event_id = ?,
            updated_at = ?
        WHERE id = ?
        """

        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    event.title,
                    event.description,
                    event.start_time.isoformat(sep=" "),
                    event.end_time.isoformat(sep=" ") if event.end_time else None,
                    event.category,
                    event.rrule,
                    int(event.is_recurring),
                    event.parent_event_id,
                    _now().isoformat(sep=" "),
                    event.id,
                ),
            )
            conn.commit()

    def _delete_event(self, event_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()

    def _get_events_between(self, start: datetime, end: datetime, limit: int = 50) -> list[Event]:
        sql = """
        SELECT *
        FROM events
        WHERE start_time >= ? AND start_time < ?
        ORDER BY start_time ASC
        LIMIT ?
        """

        with self._get_conn() as conn:
            rows = conn.execute(
                sql,
                (
                    start.isoformat(sep=" "),
                    end.isoformat(sep=" "),
                    limit,
                ),
            ).fetchall()

        return [Event.from_row(row) for row in rows]

    def _find_candidate_events(self, text: str, start: datetime, end: datetime) -> list[tuple[float, Event]]:
        events = self._get_events_between(start=start, end=end, limit=100)
        scored: list[tuple[float, Event]] = []

        for event in events:
            score = _score_candidate(text, event)
            if score > 0.01:
                scored.append((score, event))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

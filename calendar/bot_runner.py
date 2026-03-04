#!/usr/bin/env python3
"""Run Calendar Primary Telegram bot (Wave 2a)."""

from __future__ import annotations

import logging
import os

try:
    from .telegram_bot import CalendarTelegramBot
except ImportError:  # pragma: no cover - direct script fallback
    from calendar.telegram_bot import CalendarTelegramBot


def _parse_allowed_chat_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        one = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not one:
            return set()
        raw = one

    values = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            values.add(int(chunk))
        except ValueError:
            continue
    return values


def main() -> None:
    logging.basicConfig(
        level=os.getenv("CALENDAR_BOT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    token = (
        os.getenv("CALENDAR_TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()

    if not token:
        raise SystemExit(
            "Missing bot token. Set CALENDAR_TELEGRAM_BOT_TOKEN (or TELEGRAM_BOT_TOKEN)."
        )

    db_path = os.getenv("CALENDAR_DB_PATH")
    allowed_chat_ids = _parse_allowed_chat_ids()

    bot = CalendarTelegramBot(
        token=token,
        db_path=db_path,
        allowed_chat_ids=allowed_chat_ids,
    )
    bot.run_forever()


if __name__ == "__main__":
    main()

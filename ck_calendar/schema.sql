-- Calendar Primary (Wave 1a)
-- SQLite schema for event storage.
--
-- Suggested categories (free-form text, not enforced):
--   Work, Personal, Kids Club, Staff, Deadlines, Projects/OpenClaw

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    start_time TEXT NOT NULL,           -- ISO-8601 datetime
    end_time TEXT,                      -- ISO-8601 datetime (optional)
    category TEXT NOT NULL DEFAULT 'Work',
    rrule TEXT,                         -- RFC 5545 RRULE string
    created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    is_recurring INTEGER NOT NULL DEFAULT 0 CHECK (is_recurring IN (0, 1)),
    parent_event_id TEXT,
    FOREIGN KEY (parent_event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_rrule ON events(rrule);

-- Helpful for linking recurring instances to their parent
CREATE INDEX IF NOT EXISTS idx_events_parent_event_id ON events(parent_event_id);

-- Keep updated_at in sync on updates
CREATE TRIGGER IF NOT EXISTS trg_events_updated_at
AFTER UPDATE ON events
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE events
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

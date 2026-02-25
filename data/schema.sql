-- UMN Bar Traffic — SQLite schema

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────
-- bars
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bars (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    neighborhood  TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────
-- observations  (ground-truth wait times)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    bar_id        INTEGER NOT NULL REFERENCES bars(id) ON DELETE CASCADE,
    observed_at   TEXT    NOT NULL,          -- ISO-8601 UTC
    wait_minutes  REAL    NOT NULL CHECK (wait_minutes >= 0),
    cover_charge  REAL,                      -- dollars, NULL if none
    notes         TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bar_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_obs_bar_time
    ON observations (bar_id, observed_at);

-- ─────────────────────────────────────────────
-- signals  (external features at observation time)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id   INTEGER NOT NULL REFERENCES observations(id) ON DELETE CASCADE UNIQUE,
    temperature_c    REAL,                   -- °C at observation time
    precipitation_mm REAL,                   -- mm in last hour
    is_game_day      INTEGER NOT NULL DEFAULT 0 CHECK (is_game_day IN (0,1)),
    is_holiday       INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday IN (0,1)),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

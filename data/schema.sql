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
    wait_minutes       REAL    NOT NULL CHECK (wait_minutes >= 0),
    pct_full           REAL    CHECK (pct_full BETWEEN 0 AND 100),
    drink_wait_minutes REAL    CHECK (drink_wait_minutes >= 0),
    cover_charge       REAL,                      -- dollars, NULL if none
    notes              TEXT,
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

    -- Weather
    temperature_c    REAL,
    precipitation_mm REAL,
    wind_chill_c     REAL,           -- apparent/feels-like temperature (°C)
    snowfall_mm      REAL,           -- snowfall in last hour (mm)
    wind_speed_ms    REAL,           -- wind speed (m/s)
    is_severe_weather INTEGER NOT NULL DEFAULT 0 CHECK (is_severe_weather IN (0,1)),

    -- Legacy game/holiday flags (kept for compatibility)
    is_game_day      INTEGER NOT NULL DEFAULT 0 CHECK (is_game_day IN (0,1)),
    is_holiday       INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday IN (0,1)),

    -- Athletics (sport-specific)
    is_football_home   INTEGER NOT NULL DEFAULT 0 CHECK (is_football_home   IN (0,1)),
    is_basketball_home INTEGER NOT NULL DEFAULT 0 CHECK (is_basketball_home IN (0,1)),
    is_hockey_home     INTEGER NOT NULL DEFAULT 0 CHECK (is_hockey_home     IN (0,1)),
    hours_until_game   REAL,         -- negative = hours since game started; NULL if no game today
    is_rivalry_game    INTEGER NOT NULL DEFAULT 0 CHECK (is_rivalry_game    IN (0,1)),

    -- Academic calendar
    classes_in_session INTEGER NOT NULL DEFAULT 0 CHECK (classes_in_session IN (0,1)),
    is_finals_week     INTEGER NOT NULL DEFAULT 0 CHECK (is_finals_week     IN (0,1)),
    is_welcome_week    INTEGER NOT NULL DEFAULT 0 CHECK (is_welcome_week    IN (0,1)),
    is_break           INTEGER NOT NULL DEFAULT 0 CHECK (is_break           IN (0,1)),
    is_summer_session  INTEGER NOT NULL DEFAULT 0 CHECK (is_summer_session  IN (0,1)),
    week_of_semester   INTEGER,      -- 1–16 when classes in session, NULL otherwise

    -- Events
    is_st_patricks        INTEGER NOT NULL DEFAULT 0 CHECK (is_st_patricks        IN (0,1)),
    is_halloween          INTEGER NOT NULL DEFAULT 0 CHECK (is_halloween          IN (0,1)),
    is_homecoming         INTEGER NOT NULL DEFAULT 0 CHECK (is_homecoming         IN (0,1)),
    is_bar_crawl          INTEGER NOT NULL DEFAULT 0 CHECK (is_bar_crawl          IN (0,1)),
    is_blackout_wednesday INTEGER NOT NULL DEFAULT 0 CHECK (is_blackout_wednesday IN (0,1)),
    is_new_years_eve      INTEGER NOT NULL DEFAULT 0 CHECK (is_new_years_eve      IN (0,1)),

    -- Sports (external to UMN)
    is_twins_home         INTEGER NOT NULL DEFAULT 0 CHECK (is_twins_home         IN (0,1)),

    -- Academic (expanded)
    is_midterms_week      INTEGER NOT NULL DEFAULT 0 CHECK (is_midterms_week      IN (0,1)),
    is_syllabus_week      INTEGER NOT NULL DEFAULT 0 CHECK (is_syllabus_week      IN (0,1)),
    days_until_break      REAL,   -- days until next break/finals; NULL when already on break

    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Migrations for existing databases are handled in data/db.py (_migrate_signals)

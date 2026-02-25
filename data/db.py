"""SQLite connection helpers and schema initialisation."""

import sqlite3
from pathlib import Path

from config.settings import DB_PATH, BARS

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# New signals columns added after the initial release.
# Each entry is (column_name, column_definition).
# init_db() attempts to ALTER TABLE for each one; errors (column already
# exists) are silently ignored — works on any SQLite version.
_SIGNALS_MIGRATIONS: list[tuple[str, str]] = [
    ("wind_chill_c",      "REAL"),
    ("snowfall_mm",       "REAL"),
    ("wind_speed_ms",     "REAL"),
    ("is_severe_weather", "INTEGER NOT NULL DEFAULT 0"),
    ("is_football_home",   "INTEGER NOT NULL DEFAULT 0"),
    ("is_basketball_home", "INTEGER NOT NULL DEFAULT 0"),
    ("is_hockey_home",     "INTEGER NOT NULL DEFAULT 0"),
    ("hours_until_game",   "REAL"),
    ("is_rivalry_game",    "INTEGER NOT NULL DEFAULT 0"),
    ("classes_in_session", "INTEGER NOT NULL DEFAULT 0"),
    ("is_finals_week",     "INTEGER NOT NULL DEFAULT 0"),
    ("is_welcome_week",    "INTEGER NOT NULL DEFAULT 0"),
    ("is_break",           "INTEGER NOT NULL DEFAULT 0"),
    ("is_summer_session",  "INTEGER NOT NULL DEFAULT 0"),
    ("week_of_semester",   "INTEGER"),
    ("is_st_patricks",        "INTEGER NOT NULL DEFAULT 0"),
    ("is_halloween",          "INTEGER NOT NULL DEFAULT 0"),
    ("is_homecoming",         "INTEGER NOT NULL DEFAULT 0"),
    ("is_bar_crawl",          "INTEGER NOT NULL DEFAULT 0"),
    ("is_blackout_wednesday",  "INTEGER NOT NULL DEFAULT 0"),
    ("is_new_years_eve",       "INTEGER NOT NULL DEFAULT 0"),
    ("is_twins_home",          "INTEGER NOT NULL DEFAULT 0"),
    ("is_midterms_week",       "INTEGER NOT NULL DEFAULT 0"),
    ("is_syllabus_week",       "INTEGER NOT NULL DEFAULT 0"),
    ("days_until_break",       "REAL"),
    # TV sports
    ("is_nfl_game_day",        "INTEGER NOT NULL DEFAULT 0"),
    ("is_nfl_playoffs",        "INTEGER NOT NULL DEFAULT 0"),
    ("is_super_bowl",          "INTEGER NOT NULL DEFAULT 0"),
    ("is_vikings_game",        "INTEGER NOT NULL DEFAULT 0"),
    ("is_cfb_saturday",        "INTEGER NOT NULL DEFAULT 0"),
    ("is_cfb_championship",    "INTEGER NOT NULL DEFAULT 0"),
    ("is_march_madness",       "INTEGER NOT NULL DEFAULT 0"),
    ("is_march_madness_elite", "INTEGER NOT NULL DEFAULT 0"),
    ("is_nba_playoffs",        "INTEGER NOT NULL DEFAULT 0"),
    ("tv_game_hour",           "INTEGER"),
    ("tv_game_weight",         "REAL NOT NULL DEFAULT 0.0"),
]


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection with row_factory set to Row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    """Create tables, seed the bars list, and migrate any new columns (idempotent)."""
    conn = get_connection(path)
    with conn:
        conn.executescript(_SCHEMA_PATH.read_text())
        conn.executemany(
            "INSERT OR IGNORE INTO bars (name, neighborhood) VALUES (?, ?)",
            [(b["name"], b["neighborhood"]) for b in BARS],
        )
        _migrate_signals(conn)
    conn.close()


def _migrate_signals(conn: sqlite3.Connection) -> None:
    """Add any missing columns to the signals table (safe on all SQLite versions)."""
    for col, col_def in _SIGNALS_MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass  # column already exists — nothing to do

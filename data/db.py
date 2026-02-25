"""SQLite connection helpers and schema initialisation."""

import sqlite3
from pathlib import Path

from config.settings import DB_PATH, BARS

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a connection with row_factory set to Row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path = DB_PATH) -> None:
    """Create tables and seed the bars list (idempotent)."""
    conn = get_connection(path)
    with conn:
        conn.executescript(_SCHEMA_PATH.read_text())
        conn.executemany(
            "INSERT OR IGNORE INTO bars (name, neighborhood) VALUES (?, ?)",
            [(b["name"], b["neighborhood"]) for b in BARS],
        )
    conn.close()

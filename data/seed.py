"""Seed the database with synthetic observations for development / demo.

Run once:
    python -m data.seed
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import numpy as np

from data.db import get_connection, init_db

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# How many days of synthetic history to generate
HISTORY_DAYS = 60

# Realistic wait-time distributions per bar (mean, std) in minutes
BAR_PROFILES = {
    1: {"mean": 12, "std": 8},   # Blarney
    2: {"mean": 8,  "std": 5},   # The Library
    3: {"mean": 15, "std": 10},  # Stub & Herbs
    4: {"mean": 5,  "std": 4},   # Bock's
    5: {"mean": 20, "std": 12},  # Bullwinkle's
}

# Hours during which the bar is open (inclusive)
OPEN_HOURS = list(range(18, 24)) + list(range(0, 3))  # 6 PM – 2 AM


def _wait(bar_id: int, hour: int, is_weekend: bool, is_late_night: bool) -> float:
    """Simulate a realistic wait time with temporal modifiers."""
    p = BAR_PROFILES[bar_id]
    base = np.random.normal(p["mean"], p["std"])

    # Peak hours boost
    if hour in (22, 23, 0, 1):
        base *= 1.5
    if is_weekend:
        base *= 1.4
    if is_late_night:
        base *= 1.2

    return max(0.0, round(base, 1))


def seed(days: int = HISTORY_DAYS) -> None:
    init_db()
    conn = get_connection()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    inserted = 0
    with conn:
        for day_offset in range(days):
            day = start + timedelta(days=day_offset)
            is_weekend = day.weekday() >= 4  # Fri–Sun
            is_game_day = random.random() < 0.15  # ~15% of days

            for bar_id in BAR_PROFILES:
                for hour in OPEN_HOURS:
                    ts = day.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
                    if hour >= 24:
                        ts += timedelta(days=1)

                    is_late_night = hour in (0, 1, 2)
                    wait = _wait(bar_id, hour, is_weekend, is_late_night)
                    # Slight game-day bump
                    if is_game_day:
                        wait *= 1.3

                    try:
                        cur = conn.execute(
                            """
                            INSERT OR IGNORE INTO observations
                                (bar_id, observed_at, wait_minutes)
                            VALUES (?, ?, ?)
                            """,
                            (bar_id, ts.isoformat(), round(wait, 1)),
                        )
                        obs_id = cur.lastrowid
                        if obs_id:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO signals
                                    (observation_id, temperature_c, precipitation_mm,
                                     is_game_day, is_holiday)
                                VALUES (?, ?, ?, ?, 0)
                                """,
                                (
                                    obs_id,
                                    round(np.random.normal(5, 10), 1),   # Minneapolis temp
                                    round(max(0, np.random.normal(0.5, 1.5)), 2),
                                    int(is_game_day),
                                ),
                            )
                            inserted += 1
                    except Exception as exc:
                        print(f"  skip {bar_id} {ts}: {exc}")

    conn.close()
    print(f"Seeded {inserted} observations into the database.")


if __name__ == "__main__":
    seed()

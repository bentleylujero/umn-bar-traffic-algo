"""Seed the database with synthetic observations for development / demo.

Run once:
    python -m data.seed
"""

from __future__ import annotations

import random
from datetime import date as _date
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
    1: {"mean": 14, "std": 9},   # Blarney's Pub and Grill
    2: {"mean": 10, "std": 6},   # Sally's Saloon
    3: {"mean": 18, "std": 11},  # Kollege Klub
}

# % of capacity (0–100)
BAR_PCT_PROFILES = {
    1: {"mean": 55, "std": 20},  # Blarney's Pub and Grill
    2: {"mean": 45, "std": 18},  # Sally's Saloon
    3: {"mean": 65, "std": 18},  # Kollege Klub
}

# Time to get a drink at the bar (minutes)
BAR_DRINK_PROFILES = {
    1: {"mean": 8,  "std": 4},   # Blarney's Pub and Grill
    2: {"mean": 6,  "std": 3},   # Sally's Saloon
    3: {"mean": 12, "std": 6},   # Kollege Klub
}

# Hours during which the bar is open (inclusive)
OPEN_HOURS = list(range(18, 24)) + list(range(0, 3))  # 6 PM – 2 AM

# ── Academic calendar constants (Spring 2026) ────────────────────────────────
_SPRING_2026_START        = _date(2026, 1, 20)
_SPRING_2026_WELCOME_END  = _date(2026, 1, 26)  # end of first / welcome week
_SPRING_2026_FINALS_START = _date(2026, 4, 27)
_SPRING_2026_END          = _date(2026, 5, 15)

# Known holidays in the seed window (late Dec – late Feb)
_HOLIDAY_DATES = {_date(2025, 12, 31), _date(2026, 1, 1)}


# ── Signal helpers ───────────────────────────────────────────────────────────

def _academic_flags(day: datetime) -> dict:
    """Return academic-calendar binary flags for a given day."""
    d = day.date()
    if _SPRING_2026_START <= d < _SPRING_2026_FINALS_START:
        week = (d - _SPRING_2026_START).days // 7 + 1
        return {
            "classes_in_session": 1,
            "is_finals_week":     0,
            "is_welcome_week":    int(d <= _SPRING_2026_WELCOME_END),
            "is_break":           0,
            "is_summer_session":  0,
            "week_of_semester":   week,
        }
    if _SPRING_2026_FINALS_START <= d <= _SPRING_2026_END:
        return {
            "classes_in_session": 0,
            "is_finals_week":     1,
            "is_welcome_week":    0,
            "is_break":           0,
            "is_summer_session":  0,
            "week_of_semester":   16,
        }
    # Winter break, summer, or between semesters
    is_summer = 5 <= d.month <= 8
    return {
        "classes_in_session": 0,
        "is_finals_week":     0,
        "is_welcome_week":    0,
        "is_break":           int(not is_summer),
        "is_summer_session":  int(is_summer),
        "week_of_semester":   None,
    }


def _game_flags(day: datetime) -> dict:
    """Return athletics flags for the day (same for all bars on a given day)."""
    d    = day.date()
    dow  = d.weekday()           # 0=Mon … 6=Sun
    is_fri_sat = dow in (4, 5)

    # Football: Aug–Nov home games
    is_football_home = int(
        d.month in {8, 9, 10, 11} and
        random.random() < (0.35 if is_fri_sat else 0.12)
    )
    # Hockey: Oct–Mar, prefer Fri/Sat
    is_hockey_home = int(
        d.month in {10, 11, 12, 1, 2, 3} and not is_football_home and
        random.random() < (0.28 if is_fri_sat else 0.10)
    )
    # Basketball: Nov–Mar, on any day
    is_basketball_home = int(
        d.month in {11, 12, 1, 2, 3} and not is_hockey_home and not is_football_home and
        random.random() < 0.15
    )

    is_game_day    = int(bool(is_football_home or is_hockey_home or is_basketball_home))
    is_rivalry     = int(is_game_day and random.random() < 0.06)
    game_hour      = 19 if is_game_day else None  # nominal 7 PM tipoff/kickoff

    return {
        "is_game_day":         is_game_day,
        "is_football_home":    is_football_home,
        "is_hockey_home":      is_hockey_home,
        "is_basketball_home":  is_basketball_home,
        "is_rivalry_game":     is_rivalry,
        "game_hour":           game_hour,
    }


def _synthetic_weather(day: datetime) -> dict:
    """Generate plausible Minneapolis weather for a given day."""
    month = day.month
    if month in (12, 1, 2):
        temp_c = round(np.random.normal(-8, 8), 1)
    elif month in (3, 11):
        temp_c = round(np.random.normal(0, 8), 1)
    else:
        temp_c = round(np.random.normal(15, 8), 1)

    wind_ms = round(max(0.0, np.random.exponential(4)), 1)

    # Wind chill only matters below ~10 °C
    wind_chill_c = round(temp_c - wind_ms * 0.7, 1) if temp_c < 10 else temp_c

    # Snowfall: occasional in cold months
    if month in (12, 1, 2, 3) and random.random() < 0.12:
        snowfall_mm = round(np.random.exponential(8), 1)
    else:
        snowfall_mm = 0.0

    precip_mm     = round(max(0.0, np.random.normal(0.5, 1.5)), 2)
    is_severe     = int(random.random() < 0.02 or snowfall_mm > 50)

    return {
        "temperature_c":    temp_c,
        "precipitation_mm": precip_mm,
        "wind_chill_c":     wind_chill_c,
        "snowfall_mm":      snowfall_mm,
        "wind_speed_ms":    wind_ms,
        "is_severe_weather": is_severe,
    }


def _traffic_multiplier(bar_id: int, acad: dict, games: dict, weather: dict) -> float:
    """Combine signal flags into a single wait/crowd multiplier."""
    mult = 1.0

    # Academic calendar — strongest structural signal
    if not acad["classes_in_session"] and not acad["is_finals_week"]:
        mult *= 0.35   # break / summer: near-empty
    elif acad["is_welcome_week"]:
        mult *= 1.40   # first week energy
    elif acad["is_finals_week"]:
        mult *= 0.85   # mixed stress-drink vs. study effect

    # Athletics — bar-specific sensitivity
    if games["is_football_home"]:
        # Sally's (bar_id=2) is steps from Huntington Bank Stadium
        mult *= 1.60 if bar_id == 2 else 1.30
    elif games["is_hockey_home"]:
        mult *= 1.35
    elif games["is_basketball_home"]:
        mult *= 1.20
    if games["is_rivalry_game"]:
        mult *= 1.20

    # Severe weather suppresses foot traffic
    if weather["is_severe_weather"]:
        mult *= 0.40
    elif weather["snowfall_mm"] > 50:
        mult *= 0.55
    elif weather["wind_chill_c"] < -25:
        mult *= 0.65

    return mult


def _cover_charge(bar_id: int, day: datetime) -> float | None:
    """Only Kollege Klub (bar_id=3) charges cover; higher on Thu–Sat."""
    if bar_id != 3:
        return None
    dow = day.weekday()
    if dow in (3, 4, 5):   # Thu, Fri, Sat
        return float(random.choice([5, 7, 8, 10]))
    return float(random.choice([0, 3, 5]))


# ── Base simulation helpers (unchanged logic) ────────────────────────────────

def _wait(bar_id: int, hour: int, is_weekend: bool, is_late_night: bool) -> float:
    p    = BAR_PROFILES[bar_id]
    base = np.random.normal(p["mean"], p["std"])
    if hour in (22, 23, 0, 1):
        base *= 1.5
    if is_weekend:
        base *= 1.4
    if is_late_night:
        base *= 1.2
    return max(0.0, round(base, 1))


def _pct_full(bar_id: int, hour: int, is_weekend: bool, is_late_night: bool) -> float:
    p    = BAR_PCT_PROFILES[bar_id]
    base = np.random.normal(p["mean"], p["std"])
    if hour in (22, 23, 0, 1):
        base *= 1.3
    if is_weekend:
        base *= 1.2
    if is_late_night:
        base *= 1.1
    return max(0.0, min(100.0, round(base, 1)))


def _drink_wait(bar_id: int, hour: int, is_weekend: bool, is_late_night: bool) -> float:
    p    = BAR_DRINK_PROFILES[bar_id]
    base = np.random.normal(p["mean"], p["std"])
    if hour in (22, 23, 0, 1):
        base *= 1.5
    if is_weekend:
        base *= 1.4
    if is_late_night:
        base *= 1.2
    return max(0.0, round(base, 1))


# ── Main seeder ──────────────────────────────────────────────────────────────

def seed(days: int = HISTORY_DAYS) -> None:
    init_db()
    conn = get_connection()
    now   = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    inserted = 0
    with conn:
        for day_offset in range(days):
            day        = start + timedelta(days=day_offset)
            is_weekend = day.weekday() >= 4  # Fri–Sun

            acad       = _academic_flags(day)
            games      = _game_flags(day)
            is_holiday = int(day.date() in _HOLIDAY_DATES)

            # St. Patrick's Day / Halloween / etc. are outside the 60-day dev window
            # but the columns are seeded as 0 so the schema is exercised.
            is_st_patricks = int(day.date().month == 3 and day.date().day == 17)
            is_halloween   = int(day.date().month == 10 and day.date().day == 31)
            is_homecoming  = 0   # manually set for Homecoming weekend
            is_bar_crawl   = int(random.random() < 0.01)   # ~1% of days

            for bar_id in BAR_PROFILES:
                cover = _cover_charge(bar_id, day)

                for hour in OPEN_HOURS:
                    ts            = day.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
                    if hour >= 24:
                        ts += timedelta(days=1)

                    is_late_night = hour in (0, 1, 2)
                    weather       = _synthetic_weather(day)
                    mult          = _traffic_multiplier(bar_id, acad, games, weather)

                    wait  = max(0.0, round(_wait(bar_id, hour, is_weekend, is_late_night) * mult, 1))
                    pct   = max(0.0, min(100.0, round(_pct_full(bar_id, hour, is_weekend, is_late_night) * mult, 1)))
                    drink = max(0.0, round(_drink_wait(bar_id, hour, is_weekend, is_late_night) * mult, 1))

                    # hours_until_game: positive = before, negative = after, None = no game
                    obs_hour        = hour % 24
                    hours_until_game = (
                        round(games["game_hour"] - obs_hour, 1)
                        if games["game_hour"] is not None else None
                    )

                    try:
                        cur = conn.execute(
                            """
                            INSERT OR IGNORE INTO observations
                                (bar_id, observed_at, wait_minutes, pct_full,
                                 drink_wait_minutes, cover_charge)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (bar_id, ts.isoformat(), wait, pct, drink, cover),
                        )
                        obs_id = cur.lastrowid
                        if obs_id:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO signals
                                    (observation_id,
                                     temperature_c, precipitation_mm,
                                     wind_chill_c, snowfall_mm, wind_speed_ms, is_severe_weather,
                                     is_game_day, is_holiday,
                                     is_football_home, is_basketball_home, is_hockey_home,
                                     hours_until_game, is_rivalry_game,
                                     classes_in_session, is_finals_week, is_welcome_week,
                                     is_break, is_summer_session, week_of_semester,
                                     is_st_patricks, is_halloween, is_homecoming, is_bar_crawl)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    obs_id,
                                    weather["temperature_c"],
                                    weather["precipitation_mm"],
                                    weather["wind_chill_c"],
                                    weather["snowfall_mm"],
                                    weather["wind_speed_ms"],
                                    weather["is_severe_weather"],
                                    games["is_game_day"],
                                    is_holiday,
                                    games["is_football_home"],
                                    games["is_basketball_home"],
                                    games["is_hockey_home"],
                                    hours_until_game,
                                    games["is_rivalry_game"],
                                    acad["classes_in_session"],
                                    acad["is_finals_week"],
                                    acad["is_welcome_week"],
                                    acad["is_break"],
                                    acad["is_summer_session"],
                                    acad["week_of_semester"],
                                    is_st_patricks,
                                    is_halloween,
                                    is_homecoming,
                                    is_bar_crawl,
                                ),
                            )
                            inserted += 1
                    except Exception as exc:
                        print(f"  skip {bar_id} {ts}: {exc}")

    conn.close()
    print(f"Seeded {inserted} observations into the database.")


if __name__ == "__main__":
    seed()

"""Seed the database with synthetic observations for development / demo.

Run once:
    python -m data.seed
"""

from __future__ import annotations

import random
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from config.settings import BAR_SCHEDULES
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
OPEN_HOURS = list(range(14, 24)) + list(range(0, 3))  # 2 PM – 2 AM

# ── Academic calendar constants (Spring 2026) ────────────────────────────────
_SPRING_2026_START        = _date(2026, 1, 20)
_SPRING_2026_WELCOME_END  = _date(2026, 1, 26)  # end of first / welcome week
_SPRING_2026_MIDTERMS_S   = _date(2026, 3,  2)  # ~week 7
_SPRING_2026_MIDTERMS_E   = _date(2026, 3, 20)  # ~week 9
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
        days_until_break = (_SPRING_2026_FINALS_START - d).days
        return {
            "classes_in_session": 1,
            "is_finals_week":     0,
            "is_welcome_week":    int(d <= _SPRING_2026_WELCOME_END),
            "is_syllabus_week":   int(d <= _SPRING_2026_WELCOME_END),
            "is_midterms_week":   int(_SPRING_2026_MIDTERMS_S <= d <= _SPRING_2026_MIDTERMS_E),
            "is_break":           0,
            "is_summer_session":  0,
            "week_of_semester":   week,
            "days_until_break":   float(days_until_break),
            "is_study_days":      int(_SPRING_2026_FINALS_START - timedelta(days=3) <= d < _SPRING_2026_FINALS_START),
            "days_since_semester_start": (d - _SPRING_2026_START).days,
            "is_commencement":    0,
        }
    if _SPRING_2026_FINALS_START <= d <= _SPRING_2026_END:
        return {
            "classes_in_session": 0,
            "is_finals_week":     1,
            "is_welcome_week":    0,
            "is_syllabus_week":   0,
            "is_midterms_week":   0,
            "is_break":           0,
            "is_summer_session":  0,
            "week_of_semester":   16,
            "days_until_break":   0.0,
            "is_study_days":      0,
            "days_since_semester_start": (d - _SPRING_2026_START).days,
            "is_commencement":    0,
        }
    # Winter break, summer, or between semesters
    is_summer = 5 <= d.month <= 8
    return {
        "classes_in_session": 0,
        "is_finals_week":     0,
        "is_welcome_week":    0,
        "is_syllabus_week":   0,
        "is_midterms_week":   0,
        "is_break":           int(not is_summer),
        "is_summer_session":  int(is_summer),
        "week_of_semester":   None,
        "days_until_break":   None,
        "is_study_days":      0,
        "days_since_semester_start": None,
        "is_commencement":    int(d.month == 5 and _SPRING_2026_END < d <= _SPRING_2026_END + timedelta(days=3)),
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

    # Cloud cover (0-100%)
    cloud_cover = round(min(100.0, max(0.0, np.random.beta(2, 2) * 100)), 1)
    is_first_nice_day = int(month in (2, 3, 4) and temp_c >= 10.0)

    return {
        "temperature_c":    temp_c,
        "precipitation_mm": precip_mm,
        "wind_chill_c":     wind_chill_c,
        "snowfall_mm":      snowfall_mm,
        "wind_speed_ms":    wind_ms,
        "is_severe_weather": is_severe,
        "cloud_cover":       cloud_cover,
        "is_first_nice_day": is_first_nice_day,
    }


def _bar_special_boost(bar_id: int, dow: int, hour: int) -> float:
    """Return the traffic_boost for any active weekly special at (bar_id, dow, hour).

    Uses the same schedule data as features/builder.py so synthetic observations
    are consistent with the feature signals the model will see at prediction time.
    Returns 0.0 when no special is active.
    """
    sched = BAR_SCHEDULES.get(bar_id, {})
    frac  = float(hour)          # decimal hour (seed always uses whole hours)

    best_boost = 0.0

    # Happy-hour boost: not modelled separately here — handled below as part of
    # the bar-specific logic that already exists.

    for special in sched.get("weekly_specials", []):
        sp_days = special.get("days") or [special.get("day")]
        s_frac  = special["start"][0] + special["start"][1] / 60.0
        e_frac  = special["end"][0]   + special["end"][1]   / 60.0
        boost   = special.get("traffic_boost", 0.0)

        if e_frac <= 24:
            active = (dow in sp_days) and (s_frac <= frac < e_frac)
        else:
            # Overnight special: same day (after start) OR next day (before end-24)
            e_next     = e_frac - 24.0
            next_days  = [(d + 1) % 7 for d in sp_days]
            same_night = (dow in sp_days)      and (frac >= s_frac)
            next_morn  = (dow in next_days)    and (frac <  e_next)
            active     = same_night or next_morn

        if active:
            best_boost = max(best_boost, boost)

    return best_boost


def _traffic_multiplier(
    bar_id: int,
    hour: int,
    dow: int,
    acad: dict,
    games: dict,
    weather: dict,
    extras: dict,
    tv: dict,
) -> float:
    """Combine signal flags into a single wait/crowd multiplier."""
    mult = 1.0

    # Early-afternoon ramp: bars are nearly empty before 6 PM.
    # The multiplier scales from ~5% capacity at 2 PM up to full baseline at 6 PM.
    _EARLY_RAMP = {14: 0.05, 15: 0.15, 16: 0.30, 17: 0.55}
    if hour in _EARLY_RAMP:
        mult *= _EARLY_RAMP[hour]

    # Academic calendar — strongest structural signal
    if not acad["classes_in_session"] and not acad["is_finals_week"]:
        mult *= 0.35   # break / summer: near-empty
    elif acad["is_syllabus_week"]:
        mult *= 1.45   # very first week, everyone socialising
    elif acad["is_welcome_week"]:
        mult *= 1.40   # first week energy
    elif acad["is_midterms_week"]:
        mult *= 0.80   # studying pressure; similar to finals
    elif acad["is_finals_week"]:
        mult *= 0.85   # mixed stress-drink vs. study effect

    # days_until_break: winding-up effect in final weeks before break
    dub = acad.get("days_until_break")
    if dub is not None and 0 < dub <= 7:
        mult *= 1.15   # last-week-of-class celebration bump

    # UMN Athletics — bar-specific sensitivity
    if games["is_football_home"]:
        mult *= 1.60 if bar_id == 2 else 1.30  # Sally's near stadium
    elif games["is_hockey_home"]:
        mult *= 1.35
    elif games["is_basketball_home"]:
        mult *= 1.20
    if games["is_rivalry_game"]:
        mult *= 1.20

    # Twins home — Dinkytown bars (1 & 3) benefit more from downtown spillover
    if extras["is_twins_home"]:
        mult *= 1.25 if bar_id in (1, 3) else 1.15

    # Minnesota Wild game (Sally's has Wild specials)
    if extras.get("is_wild_game"):
        mult *= 1.25 if bar_id == 2 else 1.10

    # Minnesota Timberwolves game (Sally's has T-Wolves specials)
    if extras.get("is_timberwolves_game"):
        mult *= 1.20 if bar_id == 2 else 1.08

    # Cinco de Mayo bar crawl boost
    if extras.get("is_cinco_de_mayo"):
        mult *= 1.35

    # Commencement weekend — families celebrating at nearby bars
    if acad.get("is_commencement"):
        mult *= 1.35

    # Parents' Weekend — families on campus
    if extras.get("is_parents_weekend"):
        mult *= 1.20

    # First nice spring day — outdoor patio surge
    if weather.get("is_first_nice_day"):
        mult *= 1.25

    # Drinking holidays
    if extras["is_blackout_wednesday"] or extras["is_new_years_eve"]:
        mult *= 1.70

    # Bar-specific schedule effects
    if bar_id == 1:   # Blarney's — drunk-migration draw escalates after 10pm
        if hour in (22, 23, 0, 1, 2):
            h_adj = hour if hour >= 22 else hour + 24   # 0→24, 1→25, 2→26
            draw  = (h_adj - 22) / 4.0                 # 0 at 10pm → 1 at 2am
            mult *= 1.0 + draw * 0.60                  # up to +60% at 2am

    # Weekly specials — apply traffic_boost from BAR_SCHEDULES.
    # This ensures synthetic observations show a realistic crowd spike during
    # deal nights (karaoke Thursday, KK Tuesday, etc.) so the model can learn
    # the pattern from training data.
    special_boost = _bar_special_boost(bar_id, dow, hour)
    if special_boost > 0:
        mult *= 1.0 + special_boost

    # TV sports — biggest effect during and just after game time (early hours)
    tv_weight = tv.get("tv_game_weight", 0.0)
    if tv_weight > 0:
        tv_hour = tv.get("tv_game_hour")
        if tv_hour is not None:
            # Hours during/right after the game get the full boost;
            # hours more than 4h away get reduced boost
            hrs_from_game = abs(hour - tv_hour)
            proximity = max(0.0, 1.0 - hrs_from_game / 5.0)
        else:
            proximity = 0.5
        mult *= 1.0 + (tv_weight * 0.18 * proximity)

    # Severe weather suppresses foot traffic
    if weather["is_severe_weather"]:
        mult *= 0.40
    elif weather["snowfall_mm"] > 50:
        mult *= 0.55
    elif weather["wind_chill_c"] < -25:
        mult *= 0.65

    return mult


def _thanksgiving(year: int) -> _date:
    """Return the date of Thanksgiving (4th Thursday of November)."""
    nov1 = _date(year, 11, 1)
    # weekday(): 0=Mon … 6=Sun; Thursday=3
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(weeks=3)


def _tv_sports_flags(day: datetime) -> dict:
    """Synthetic TV-sports signals based on day-of-week and month.

    Covers the realistic sports calendar so the model can learn the
    early-evening crowd boost driven by watching big games at bars.
    """
    d     = day.date()
    dow   = d.weekday()   # 0=Mon … 6=Sun
    month = d.month

    # NFL: Sep–Feb; Sundays + Thursday/Monday night games
    nfl_season   = month in {9, 10, 11, 12, 1, 2}
    nfl_game_day = int(nfl_season and dow in {3, 0, 6})  # Thu/Mon/Sun
    # Playoffs: 2nd week of Jan onward
    nfl_playoffs = int(nfl_game_day and (
        (month == 1 and d.day >= 10) or month == 2
    ))
    # Super Bowl: first Sunday in February (~Feb 8 in 2026)
    is_super_bowl = int(d.month == 2 and dow == 6 and 1 <= d.day <= 14
                        and nfl_playoffs)
    # Vikings: 60% chance they're in any NFL game
    is_vikings_game = int(nfl_game_day and random.random() < 0.60)

    # CFB: Sep–Dec Saturdays; bowl games Dec 28–Jan 20
    is_cfb_saturday    = int(dow == 5 and month in {9, 10, 11, 12})
    is_cfb_championship = int(
        (month == 12 and d.day >= 28) or (month == 1 and d.day <= 20)
    )

    # March Madness: mid-March to early April
    is_march_madness = int(
        (month == 3 and d.day >= 14) or (month == 4 and d.day <= 7)
    )
    is_march_madness_elite = int(
        is_march_madness and random.random() < 0.30
    )

    # NBA playoffs: April–June, most nights
    is_nba_playoffs = int(month in {4, 5, 6} and random.random() < 0.55)

    # TV game weight (magnitude 0–4)
    weight = 0.0
    if is_super_bowl:
        weight = 4.0
    elif nfl_playoffs:
        weight = max(weight, 2.0)
    elif is_cfb_championship:
        weight = max(weight, 1.5)
    elif is_march_madness_elite:
        weight = max(weight, 2.0)
    elif nfl_game_day:
        weight = max(weight, 1.0)
    elif is_march_madness:
        weight = max(weight, 0.8)
    elif is_nba_playoffs:
        weight = max(weight, 1.0)
    elif is_cfb_saturday:
        weight = max(weight, 0.6)
    if is_vikings_game:
        weight = min(weight + 0.5, 4.0)

    # Typical kickoff hours (local, 24h)
    if is_super_bowl:
        tv_game_hour = 18
    elif nfl_game_day:
        tv_game_hour = 13   # 1 PM typical early window
    elif is_cfb_saturday or is_cfb_championship:
        tv_game_hour = 12
    elif is_march_madness:
        tv_game_hour = 14
    elif is_nba_playoffs:
        tv_game_hour = 20   # 8 PM ET → 7 PM CT
    else:
        tv_game_hour = None

    return {
        "is_nfl_game_day":        nfl_game_day,
        "is_nfl_playoffs":        nfl_playoffs,
        "is_super_bowl":          is_super_bowl,
        "is_vikings_game":        is_vikings_game,
        "is_cfb_saturday":        is_cfb_saturday,
        "is_cfb_championship":    is_cfb_championship,
        "is_march_madness":       is_march_madness,
        "is_march_madness_elite": is_march_madness_elite,
        "is_nba_playoffs":        is_nba_playoffs,
        "tv_game_hour":           tv_game_hour,
        "tv_game_weight":         weight,
    }


def _extra_event_flags(day: datetime) -> dict:
    """Return flags for major drinking holidays and external sports."""
    d   = day.date()
    dow = d.weekday()

    # Blackout Wednesday: day before Thanksgiving
    tgiving = _thanksgiving(d.year)
    is_blackout_wednesday = int(d == tgiving - timedelta(days=1))

    # New Year's Eve
    is_new_years_eve = int(d.month == 12 and d.day == 31)

    # Twins home: April–September; ~30% chance on any day in season
    is_twins_home = int(
        d.month in {4, 5, 6, 7, 8, 9} and
        random.random() < (0.40 if dow in (4, 5, 6) else 0.28)
    )

    # Cinco de Mayo — bar crawl night
    is_cinco_de_mayo = int(d.month == 5 and d.day == 5)

    # Minnesota Wild: Oct–Apr; more on Fri/Sat
    is_wild_game = int(
        d.month in {10, 11, 12, 1, 2, 3, 4} and
        random.random() < (0.28 if dow in (4, 5) else 0.16)
    )

    # Minnesota Timberwolves: Oct–Apr (regular season); occasionally May–Jun playoffs
    is_timberwolves_game = int(
        d.month in {10, 11, 12, 1, 2, 3, 4} and
        random.random() < 0.20
    )

    # NHL playoffs: April–June
    is_nhl_playoffs = int(
        d.month in {4, 5, 6} and random.random() < 0.40
    )

    # Parents' Weekend
    is_parents_weekend = int(
        (_date(2025, 10, 17) <= d <= _date(2025, 10, 19)) or
        (_date(2026, 10, 16) <= d <= _date(2026, 10, 18))
    )

    return {
        "is_blackout_wednesday": is_blackout_wednesday,
        "is_new_years_eve":      is_new_years_eve,
        "is_twins_home":         is_twins_home,
        "is_cinco_de_mayo":      is_cinco_de_mayo,
        "is_wild_game":          is_wild_game,
        "is_timberwolves_game":  is_timberwolves_game,
        "is_nhl_playoffs":       is_nhl_playoffs,
        "is_parents_weekend":    is_parents_weekend,
    }


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
            extras     = _extra_event_flags(day)
            tv         = _tv_sports_flags(day)
            is_holiday = int(day.date() in _HOLIDAY_DATES)

            is_st_patricks = int(day.date().month == 3 and day.date().day == 17)
            is_halloween   = int(day.date().month == 10 and day.date().day == 31)
            is_homecoming  = 0
            is_bar_crawl   = int(random.random() < 0.01)

            for bar_id in BAR_PROFILES:
                cover = _cover_charge(bar_id, day)

                for hour in OPEN_HOURS:
                    ts            = day.replace(hour=hour % 24, minute=0, second=0, microsecond=0)
                    if hour >= 24:
                        ts += timedelta(days=1)

                    is_late_night = hour in (0, 1, 2)
                    weather       = _synthetic_weather(day)
                    mult          = _traffic_multiplier(bar_id, hour, day.weekday(), acad, games, weather, extras, tv)

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
                                     is_st_patricks, is_halloween, is_homecoming, is_bar_crawl,
                                     is_blackout_wednesday, is_new_years_eve, is_twins_home,
                                     is_midterms_week, is_syllabus_week, days_until_break,
                                     is_nfl_game_day, is_nfl_playoffs, is_super_bowl,
                                     is_vikings_game, is_cfb_saturday, is_cfb_championship,
                                     is_march_madness, is_march_madness_elite, is_nba_playoffs,
                                     tv_game_hour, tv_game_weight,
                                     is_wild_game, is_timberwolves_game, is_nhl_playoffs,
                                     cloud_cover, is_first_nice_day,
                                     is_study_days, is_commencement, days_since_semester_start,
                                     is_cinco_de_mayo, is_parents_weekend)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                                    extras["is_blackout_wednesday"],
                                    extras["is_new_years_eve"],
                                    extras["is_twins_home"],
                                    acad["is_midterms_week"],
                                    acad["is_syllabus_week"],
                                    acad["days_until_break"],
                                    tv["is_nfl_game_day"],
                                    tv["is_nfl_playoffs"],
                                    tv["is_super_bowl"],
                                    tv["is_vikings_game"],
                                    tv["is_cfb_saturday"],
                                    tv["is_cfb_championship"],
                                    tv["is_march_madness"],
                                    tv["is_march_madness_elite"],
                                    tv["is_nba_playoffs"],
                                    tv["tv_game_hour"],
                                    tv["tv_game_weight"],
                                    extras["is_wild_game"],
                                    extras["is_timberwolves_game"],
                                    extras["is_nhl_playoffs"],
                                    weather["cloud_cover"],
                                    weather["is_first_nice_day"],
                                    acad["is_study_days"],
                                    acad["is_commencement"],
                                    acad["days_since_semester_start"],
                                    extras["is_cinco_de_mayo"],
                                    extras["is_parents_weekend"],
                                ),
                            )
                            inserted += 1
                    except Exception as exc:
                        print(f"  skip {bar_id} {ts}: {exc}")

    conn.close()
    print(f"Seeded {inserted} observations into the database.")


if __name__ == "__main__":
    seed()

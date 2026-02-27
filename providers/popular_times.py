"""Google Popular Times baseline busyness provider.

Two-tier system:
  1. Google Places API (if GOOGLE_PLACES_API_KEY env var is set)
  2. Calibrated fallback patterns based on UMN bar culture and BAR_SCHEDULES

The calibrated patterns are: dict[bar_id, dict[day_of_week, dict[hour, float]]]
where float is busyness_pct (0–100).

Day-of-week encoding: 0=Monday … 6=Sunday (matches Python datetime.weekday()).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour — popular times change slowly
_cache: dict[str, tuple[float, dict]] = {}

# Google Places API endpoint
_PLACES_BASE = "https://maps.googleapis.com/maps/api/place/details/json"

# Approximate Google Place IDs for each bar (bar_id → place_id)
PLACE_IDS: dict[int, str] = {
    1: "ChIJnVT0vPgts1IRsRvv5XrONvk",  # Blarney's approximate
    2: "ChIJQ9g5XistslIRwZFXDJPV2Rg",  # Sally's approximate
    3: "ChIJqcJ_T_gts1IRaKH0ZZkHZgE",  # Kollege Klub approximate
}

# Bar names for readability
_BAR_NAMES: dict[int, str] = {
    1: "Blarney's Pub and Grill",
    2: "Sally's Saloon",
    3: "Kollege Klub",
}

# ── Calibrated typical busyness patterns ─────────────────────────────────────
# Structure: {bar_id: {day_of_week: {hour: busyness_pct}}}
# day_of_week: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
# Derived from BAR_SCHEDULES, UMN bar culture knowledge, and known deal nights.
#
# Blarney's (bar_id=1):
#   - Karaoke Thursday (9pm–2am) is biggest weekly draw → ~90%
#   - Fri/Sat 10pm–1am → ~80%
#   - Wed "Thirsty Wednesday" 9pm–1am → ~65%
#   - Daily happy hour 3:17–6:17pm → moderate early crowd
#
# Sally's (bar_id=2):
#   - More consistent baseline; Late Happy Hour every night 10pm–midnight
#   - $2 Tuesday 8pm–midnight → ~75%
#   - Fri/Sat → ~80%
#
# Kollege Klub (bar_id=3):
#   - KK Tuesday 9pm–2am is UMN institution → ~95%
#   - KK Thursday 9pm–2am → ~85%
#   - Fri After Class 3–7pm → ~60%
#   - Cover charge Thu–Sat keeps casual crowd lower before 9pm

def _make_daily_pattern(peak_hours: dict[int, float], base: float = 10.0) -> dict[int, float]:
    """Build a full 24-hour busyness dict given a sparse peak-hours mapping.

    Hours not in peak_hours fall back to base busyness.
    The bar is effectively closed 3–13 (3am–1pm) → 0%.
    """
    pattern: dict[int, float] = {}
    for h in range(24):
        if h <= 2:          # last call / closing
            pattern[h] = peak_hours.get(h, base * 0.5)
        elif 3 <= h <= 13:  # closed / essentially empty
            pattern[h] = 0.0
        elif 14 <= h <= 16: # opening hours — trickle of traffic
            pattern[h] = peak_hours.get(h, base)
        else:               # prime evening hours
            pattern[h] = peak_hours.get(h, base)
    return pattern


# Blarney's daily patterns by day-of-week
_BLARNEYS_PATTERNS: dict[int, dict[int, float]] = {
    0: _make_daily_pattern({17: 25, 18: 20, 19: 20, 20: 25, 21: 30, 22: 35, 23: 30, 0: 20, 1: 15}),  # Mon
    1: _make_daily_pattern({17: 25, 18: 20, 19: 20, 20: 25, 21: 30, 22: 35, 23: 30, 0: 20, 1: 15}),  # Tue
    2: _make_daily_pattern({17: 30, 18: 25, 21: 50, 22: 65, 23: 65, 0: 55, 1: 40}),                  # Wed (Thirsty Wed)
    3: _make_daily_pattern({17: 35, 18: 30, 19: 35, 20: 45, 21: 70, 22: 85, 23: 90, 0: 85, 1: 70, 2: 50}),  # Thu (Karaoke)
    4: _make_daily_pattern({17: 40, 18: 35, 19: 40, 20: 50, 21: 60, 22: 75, 23: 80, 0: 75, 1: 55}),  # Fri
    5: _make_daily_pattern({17: 35, 18: 30, 19: 40, 20: 55, 21: 65, 22: 78, 23: 80, 0: 72, 1: 55}),  # Sat
    6: _make_daily_pattern({17: 25, 18: 20, 19: 25, 20: 30, 21: 35, 22: 35, 23: 30, 0: 20}),         # Sun
}

# Sally's daily patterns by day-of-week
_SALLYS_PATTERNS: dict[int, dict[int, float]] = {
    0: _make_daily_pattern({15: 25, 16: 30, 17: 28, 18: 25, 21: 30, 22: 35, 23: 30, 0: 20}),         # Mon
    1: _make_daily_pattern({15: 30, 16: 35, 17: 32, 18: 28, 20: 55, 21: 65, 22: 75, 23: 72, 0: 55}), # Tue ($2 Tues)
    2: _make_daily_pattern({15: 28, 16: 32, 17: 30, 18: 25, 21: 35, 22: 45, 23: 42, 0: 30}),         # Wed
    3: _make_daily_pattern({15: 35, 16: 40, 17: 38, 18: 32, 20: 45, 21: 55, 22: 65, 23: 62, 0: 50}), # Thu
    4: _make_daily_pattern({15: 40, 16: 45, 17: 42, 18: 38, 20: 55, 21: 65, 22: 80, 23: 80, 0: 70}), # Fri
    5: _make_daily_pattern({15: 38, 16: 42, 17: 40, 18: 35, 20: 58, 21: 68, 22: 80, 23: 78, 0: 65}), # Sat
    6: _make_daily_pattern({15: 25, 16: 28, 17: 25, 18: 22, 21: 35, 22: 38, 23: 30, 0: 22}),         # Sun
}

# Kollege Klub daily patterns by day-of-week
_KK_PATTERNS: dict[int, dict[int, float]] = {
    0: _make_daily_pattern({20: 25, 21: 30, 22: 35, 23: 30, 0: 20}),                                  # Mon
    1: _make_daily_pattern({20: 60, 21: 80, 22: 90, 23: 95, 0: 90, 1: 75, 2: 50}),                   # Tue (KK Tues — institution)
    2: _make_daily_pattern({20: 28, 21: 35, 22: 40, 23: 38, 0: 28}),                                  # Wed
    3: _make_daily_pattern({15: 35, 16: 45, 17: 42, 18: 30, 20: 55, 21: 70, 22: 82, 23: 85, 0: 80, 1: 65, 2: 45}),  # Thu (KK Thu)
    4: _make_daily_pattern({15: 50, 16: 60, 17: 55, 18: 45, 19: 35, 20: 55, 21: 65, 22: 75, 23: 72, 0: 60}),         # Fri (After Class + night)
    5: _make_daily_pattern({20: 55, 21: 65, 22: 72, 23: 70, 0: 60, 1: 45}),                           # Sat
    6: _make_daily_pattern({20: 25, 21: 30, 22: 32, 23: 28, 0: 18}),                                  # Sun
}

# Consolidated calibrated model: bar_id → day_of_week → hour → busyness_pct
_CALIBRATED_PATTERNS: dict[int, dict[int, dict[int, float]]] = {
    1: _BLARNEYS_PATTERNS,
    2: _SALLYS_PATTERNS,
    3: _KK_PATTERNS,
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, payload = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            return payload
    return None


def _cache_set(key: str, payload: dict) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), payload)


# ── Google Places API tier ────────────────────────────────────────────────────

def _fetch_google_popular_times(bar_id: int) -> Optional[dict]:
    """Attempt Google Places API for popular_times data.

    Returns the raw popular_times list if available, None otherwise.
    Only called when GOOGLE_PLACES_API_KEY is set in the environment.
    """
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return None

    place_id = PLACE_IDS.get(bar_id)
    if not place_id:
        return None

    try:
        resp = requests.get(
            _PLACES_BASE,
            params={
                "place_id": place_id,
                "fields":   "name,popular_times",
                "key":      api_key,
            },
            timeout=10,
            headers={"User-Agent": "umn-bar-traffic/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        result_block = data.get("result") or {}
        popular_times = result_block.get("popular_times")
        if not popular_times:
            log.debug("Google Places: no popular_times data for bar_id=%d", bar_id)
            return None
        return popular_times
    except Exception as exc:
        log.warning("Google Places fetch failed for bar_id=%d: %s", bar_id, exc)
        return None


def _parse_google_popular_times(popular_times: list[dict], hour: int, day_of_week: int) -> float:
    """Extract busyness_pct from Google Places popular_times structure.

    Google encodes day 0=Sunday … 6=Saturday.
    Python datetime.weekday() encodes 0=Monday … 6=Sunday.
    Convert: google_day = (python_dow + 1) % 7
    """
    google_day = (day_of_week + 1) % 7
    for day_block in popular_times:
        if day_block.get("day") == google_day:
            for slot in day_block.get("data", []):
                if slot.get("time") == hour:
                    return float(slot.get("percentage", 0))
    return 0.0


# ── Calibrated fallback ───────────────────────────────────────────────────────

def _calibrated_busyness(bar_id: int, hour: int, day_of_week: int) -> float:
    """Return calibrated busyness_pct from pre-built patterns."""
    bar_patterns = _CALIBRATED_PATTERNS.get(bar_id)
    if bar_patterns is None:
        return 20.0  # unknown bar — generic low baseline

    day_pattern = bar_patterns.get(day_of_week)
    if day_pattern is None:
        return 20.0

    return day_pattern.get(hour, 10.0)


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_popular_times(bar_id: int, hour: int, day_of_week: int) -> dict:
    """Fetch typical busyness for a bar at a given hour and day of week.

    Tries Google Places API first (if GOOGLE_PLACES_API_KEY is set),
    falls back to calibrated patterns.

    Parameters
    ----------
    bar_id       : int  — bar identifier (1=Blarney's, 2=Sally's, 3=KK)
    hour         : int  — 0–23 local hour
    day_of_week  : int  — 0=Monday … 6=Sunday (Python weekday encoding)

    Returns
    -------
    dict with keys:
        typical_busyness_pct : float  (0–100)
        data_source          : str    ("google_places" or "calibrated_model")
        bar_name             : str
    """
    cache_key = f"pop_times_{bar_id}_{day_of_week}_{hour}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    bar_name = _BAR_NAMES.get(bar_id, f"Bar {bar_id}")

    # Tier 1: Google Places API
    google_data = _fetch_google_popular_times(bar_id)
    if google_data is not None:
        busyness = _parse_google_popular_times(google_data, hour, day_of_week)
        result = {
            "typical_busyness_pct": busyness,
            "data_source":          "google_places",
            "bar_name":             bar_name,
        }
        _cache_set(cache_key, result)
        return result

    # Tier 2: Calibrated fallback
    busyness = _calibrated_busyness(bar_id, hour, day_of_week)
    result = {
        "typical_busyness_pct": busyness,
        "data_source":          "calibrated_model",
        "bar_name":             bar_name,
    }
    _cache_set(cache_key, result)
    return result


def fetch_all_popular_times(dt: datetime) -> dict[int, dict]:
    """Fetch typical busyness for all bars at the given datetime.

    Parameters
    ----------
    dt : datetime — the reference datetime (hour and weekday are extracted)

    Returns
    -------
    dict mapping bar_id → fetch_popular_times() result
    """
    hour = dt.hour
    # Convert to Python weekday (0=Mon … 6=Sun)
    day_of_week = dt.weekday()

    results: dict[int, dict] = {}
    for bar_id in _BAR_NAMES:
        results[bar_id] = fetch_popular_times(bar_id, hour, day_of_week)

    return results

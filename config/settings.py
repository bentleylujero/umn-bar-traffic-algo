"""Central configuration for the UMN Bar Line Forecasting project.

Edit config/tuning.py to adjust rough figures (capacities, boosts, holidays,
model params). This file handles paths, API settings, and structural config.
"""

import os
from pathlib import Path

# Re-export all tunable parameters so existing imports stay unchanged.
from config.tuning import (  # noqa: F401
    BAR_CAPACITIES,
    BAR_CLOSE_HOUR,
    BAR_OPEN_HOUR,
    DRINKING_HOLIDAY_WEIGHTS,
    HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER,
    RANDOM_SEED,
    RF_MAX_DEPTH,
    RF_N_ESTIMATORS,
    TEST_SPLIT_DAYS,
    TRAFFIC_BOOSTS,
)

# Project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Data
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "bar_traffic.db"

# Weather API (Open-Meteo — free, no key required)
WEATHER_BASE_URL = "https://api.open-meteo.com/v1/forecast"
# Minneapolis coordinates
LATITUDE = 44.9778
LONGITUDE = -93.2650

# Bars tracked (name → rough address for display and coordinates for map)
BARS = [
    {"name": "Blarney's Pub and Grill", "neighborhood": "Dinkytown", "latitude": 44.9796, "longitude": -93.2363},
    {"name": "Sally's Saloon", "neighborhood": "Stadium Village", "latitude": 44.9734, "longitude": -93.2285},
    {"name": "Kollege Klub", "neighborhood": "Dinkytown", "latitude": 44.9810, "longitude": -93.2373},
]


# Canonical deal-type tags for manual observations.
# These are stored on the observation row (deal_type column) so future
# feature engineering can derive a deal-intensity signal.
# cover_charge deal type also sets the cover_charge dollar field directly
# (which the model already uses as a feature via SIGNAL_FEATURES).
DEAL_TYPES: list[str] = [
    "none",           # no active deal
    "happy_hour",     # standard happy-hour pricing
    "drink_special",  # recurring deal night (e.g. KK Tuesday, $2 Tuesday)
    "entertainment",  # karaoke, DJ, trivia, live music
    "cover_charge",   # door cover being collected
]

# Bar-specific recurring schedules.
# happy_hour : dict with start/end as (hour, minute) tuples, active every day.
# weekly_specials : list of recurring promos; "day" is ISO weekday (0=Mon, 6=Sun);
#   end hours > 23 denote overnight continuation (e.g. 26 = 2 AM next day).
# traffic_boost values come from TRAFFIC_BOOSTS in config/tuning.py.
BAR_SCHEDULES: dict[int, dict] = {
    1: {  # Blarney's Pub and Grill — "Office Hours"
        "happy_hour": {
            "days":  list(range(7)),
            "start": (15, 17),   # 3:17 PM (their signature quirky time)
            "end":   (18, 17),   # 6:17 PM
        },
        "weekly_specials": [
            {
                "name":  "Blarney's Karaoke Thursday",
                "days":  [3],          # Thursday only (0=Mon)
                "start": (21, 0),      # 9 PM — karaoke starts
                "end":   (26, 0),      # 2 AM Friday (overnight)
                "traffic_boost": TRAFFIC_BOOSTS["blarneys_karaoke_thursday"],
            },
            {
                "name":  "Blarney's Wednesday Deals",
                "days":  [2],          # Wednesday
                "start": (21, 0),      # 9 PM
                "end":   (25, 0),      # 1 AM Thursday
                "traffic_boost": TRAFFIC_BOOSTS["blarneys_wednesday_deals"],
            },
        ],
        # After midnight, drunk crowds migrate here from cheaper bars.
        "late_night_draw": True,
    },
    2: {  # Sally's Saloon
        "happy_hour": {
            "days":  list(range(7)),
            "start": (15, 0),    # 3:00 PM
            "end":   (18, 0),    # 6:00 PM
        },
        "weekly_specials": [
            {
                "name":  "Sally's Late Happy Hour",
                "days":  list(range(7)),  # every day
                "start": (22, 0),         # 10 PM
                "end":   (24, 0),         # midnight
                "traffic_boost": TRAFFIC_BOOSTS["sallys_late_happy_hour"],
            },
            {
                "name":  "Sally's $2 Tuesday",
                "days":  [1],             # Tuesday
                "start": (20, 0),         # 8 PM
                "end":   (24, 0),         # midnight
                "traffic_boost": TRAFFIC_BOOSTS["sallys_tuesday_deal"],
            },
        ],
        "late_night_draw": False,
    },
    3: {  # Kollege Klub
        "happy_hour": None,
        "weekly_specials": [
            {
                "name":  "KK Tuesday",
                "days":  [1],        # Tuesday only (0=Mon)
                "start": (21, 0),    # 9 PM
                "end":   (26, 0),    # 2 AM Wednesday (> 24 = next day)
                "traffic_boost": TRAFFIC_BOOSTS["kk_tuesday"],
            },
            {
                "name":  "KK Thursday",
                "days":  [3],        # Thursday
                "start": (21, 0),    # 9 PM
                "end":   (26, 0),    # 2 AM Friday
                "traffic_boost": TRAFFIC_BOOSTS["kk_thursday"],
            },
            {
                "name":  "KK Friday After Class",
                "days":  [4],        # Friday only
                "start": (15, 0),    # 3 PM
                "end":   (19, 0),    # 7 PM
                "traffic_boost": TRAFFIC_BOOSTS["kk_friday_after_class"],
            },
        ],
        "late_night_draw": False,
    },
}

"""Central configuration for the UMN Bar Line Forecasting project."""

import os
from pathlib import Path

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

# Bars tracked (name → rough address for display)
BARS = [
    {"name": "Blarney's Pub and Grill", "neighborhood": "Dinkytown"},
    {"name": "Sally's Saloon", "neighborhood": "Stadium Village"},
    {"name": "Kollege Klub", "neighborhood": "Dinkytown"},
]

# Model
TEST_SPLIT_DAYS = 14          # hold-out last N days for evaluation
RANDOM_SEED = 42
RF_N_ESTIMATORS = 200
RF_MAX_DEPTH = 10

# Hour range during which bars are open
BAR_OPEN_HOUR = 18            # 6 PM
BAR_CLOSE_HOUR = 2            # 2 AM (next day)

# Bar-specific recurring schedules.
# happy_hour : dict with start/end as (hour, minute) tuples, active every day.
# weekly_specials : list of recurring promos; "day" is ISO weekday (0=Mon, 6=Sun);
#   end hours > 23 denote overnight continuation (e.g. 26 = 2 AM next day).
BAR_SCHEDULES: dict[int, dict] = {
    1: {  # Blarney's Pub and Grill — "Office Hours"
        "happy_hour": {
            "days":  list(range(7)),
            "start": (15, 17),   # 3:17 PM
            "end":   (18, 17),   # 6:17 PM
        },
        "weekly_specials": [],
        # After midnight, drunk crowds migrate here from cheaper bars.
        # The later the hour, the stronger the draw.
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
            },
            {
                "name":  "KK Friday After Class",
                "days":  [4],        # Friday only
                "start": (15, 0),    # 3 PM
                "end":   (19, 0),    # 7 PM
            },
        ],
        "late_night_draw": False,
    },
}

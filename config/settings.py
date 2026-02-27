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

# Drinking-holiday configuration
# Each entry maps a signal column name → relative intensity (arbitrary scale).
# Used by FeatureBuilder to build a composite `drinking_holiday_weight` feature
# and by the training pipeline to up-weight holiday rows so the RF pays more
# attention to these rare, high-traffic events.
DRINKING_HOLIDAY_WEIGHTS: dict[str, float] = {
    "is_st_patricks":        5.0,   # biggest bar night of the year for college students
    "is_new_years_eve":      4.5,   # second biggest; bars pack out even in MN cold
    "is_halloween":          4.0,   # huge costume + bar culture at UMN
    "is_bar_crawl":          3.5,   # organized crawl guarantees a massive crowd surge
    "is_blackout_wednesday": 3.5,   # Thanksgiving eve — college students home = bars packed
    "is_homecoming":         3.0,   # UMN homecoming weekend has significant bar traffic
    "is_cinco_de_mayo":      3.0,   # Mexican holiday bar crawls; Blarney's especially
    "is_commencement":       2.5,   # families + graduates celebrating at nearby bars
    "is_parents_weekend":    1.5,   # families on campus — moderate bar activity
}
# Training rows that fall on a drinking holiday are multiplied by this factor so
# the RandomForest fits those observations much more tightly.
HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER: float = 10.0

# Hour range during which bars are open
BAR_OPEN_HOUR = 14            # 2 PM
BAR_CLOSE_HOUR = 2            # 2 AM (next day)

# Bar-specific recurring schedules.
# happy_hour : dict with start/end as (hour, minute) tuples, active every day.
# weekly_specials : list of recurring promos; "day" is ISO weekday (0=Mon, 6=Sun);
#   end hours > 23 denote overnight continuation (e.g. 26 = 2 AM next day).
BAR_SCHEDULES: dict[int, dict] = {
    1: {  # Blarney's Pub and Grill — "Office Hours"
        "happy_hour": {
            "days":  list(range(7)),
            "start": (15, 17),   # 3:17 PM (their signature quirky time)
            "end":   (18, 17),   # 6:17 PM
        },
        "weekly_specials": [
            {
                # Karaoke Thursday is Blarney's signature event — the biggest
                # weekly draw. Students specifically plan their Thursday around it.
                "name":  "Blarney's Karaoke Thursday",
                "days":  [3],          # Thursday only (0=Mon)
                "start": (21, 0),      # 9 PM — karaoke starts
                "end":   (26, 0),      # 2 AM Friday (overnight)
                # Multiplier applied on top of baseline when this special is active.
                # +55% reflects a destination crowd (people come *for* karaoke).
                "traffic_boost": 0.55,
            },
            {
                # Wednesday specials — "Thirsty Wednesday" cheap drinks draw
                # pre-Thursday crowd; moderate but reliable lift.
                "name":  "Blarney's Wednesday Deals",
                "days":  [2],          # Wednesday
                "start": (21, 0),      # 9 PM
                "end":   (25, 0),      # 1 AM Thursday
                "traffic_boost": 0.25,
            },
        ],
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
                # Late happy hour runs every night — cheap drinks keep the
                # early-night crowd from leaving at 10.
                "name":  "Sally's Late Happy Hour",
                "days":  list(range(7)),  # every day
                "start": (22, 0),         # 10 PM
                "end":   (24, 0),         # midnight
                "traffic_boost": 0.20,
            },
            {
                # Tuesday deal night — $2 taps draw students on a slow weeknight.
                "name":  "Sally's $2 Tuesday",
                "days":  [1],             # Tuesday
                "start": (20, 0),         # 8 PM
                "end":   (24, 0),         # midnight
                "traffic_boost": 0.30,
            },
        ],
        "late_night_draw": False,
    },
    3: {  # Kollege Klub
        "happy_hour": None,
        "weekly_specials": [
            {
                # KK Tuesday is a UMN institution — one of the busiest bar
                # nights of the week. Cheap drinks + high energy = massive crowd.
                # +70% is justified: students specifically go OUT on Tuesdays
                # because of this deal.
                "name":  "KK Tuesday",
                "days":  [1],        # Tuesday only (0=Mon)
                "start": (21, 0),    # 9 PM
                "end":   (26, 0),    # 2 AM Wednesday (> 24 = next day)
                "traffic_boost": 0.70,
            },
            {
                # Thursday deal night — rides the same Thursday bar culture
                # as Blarney's karaoke; competes for the same crowd.
                "name":  "KK Thursday",
                "days":  [3],        # Thursday
                "start": (21, 0),    # 9 PM
                "end":   (26, 0),    # 2 AM Friday
                "traffic_boost": 0.40,
            },
            {
                # Friday after-class happy hour — early crowd right after 3 PM
                # classes let out; lower boost, shorter window.
                "name":  "KK Friday After Class",
                "days":  [4],        # Friday only
                "start": (15, 0),    # 3 PM
                "end":   (19, 0),    # 7 PM
                "traffic_boost": 0.35,
            },
        ],
        "late_night_draw": False,
    },
}

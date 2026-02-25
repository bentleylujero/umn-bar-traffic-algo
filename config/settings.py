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
    {"name": "Blarney Pub & Grill", "neighborhood": "Dinkytown"},
    {"name": "The Library Bar", "neighborhood": "Dinkytown"},
    {"name": "Stub & Herbs", "neighborhood": "Dinkytown"},
    {"name": "Bock's Bar", "neighborhood": "Marcy-Holmes"},
    {"name": "Bullwinkle's Saloon", "neighborhood": "Dinkytown"},
]

# Model
TEST_SPLIT_DAYS = 14          # hold-out last N days for evaluation
RANDOM_SEED = 42
RF_N_ESTIMATORS = 200
RF_MAX_DEPTH = 10

# Hour range during which bars are open
BAR_OPEN_HOUR = 18            # 6 PM
BAR_CLOSE_HOUR = 2            # 2 AM (next day)

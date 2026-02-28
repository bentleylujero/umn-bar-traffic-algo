"""
TUNING PARAMETERS — edit this file to adjust the algorithm's predictions.
All changes take effect on the next server/Streamlit restart.

Sections
────────
  1. Bar occupancy      — headcount → % full conversion
  2. Deal-night boosts  — per-special traffic lift (fraction of baseline)
  3. Drinking holidays  — holiday intensity & training weight
  4. Model params       — RandomForest hyperparameters, test-split window
  5. Operating hours    — when bars are considered open
"""

# ── 1. Bar occupancy ─────────────────────────────────────────────────────────
# Estimated maximum legal occupancy (people).
# Source: fire-marshal posting inside each bar.
# Used to convert a raw headcount check-in → pct_full (0–100).

BAR_CAPACITIES: dict[int, int] = {
    1: 600,    # Blarney's Pub and Grill (basement + main floor)
    2: 1000,   # Sally's Saloon
    3: 500,    # Kollege Klub (two floors)
}


# ── 2. Deal-night traffic boosts ─────────────────────────────────────────────
# Fractional lift on top of baseline wait/fullness while a special is active.
# 0.25 = +25 % over whatever the baseline predicts for that hour.
# Used by synthetic data generation (data/seed.py) and feature engineering.

TRAFFIC_BOOSTS: dict[str, float] = {
    # Blarney's
    "blarneys_karaoke_thursday":  0.55,   # destination crowd — people plan their Thursday around it
    "blarneys_wednesday_deals":   0.25,   # pre-Thursday warm-up
    # Sally's
    "sallys_late_happy_hour":     0.20,   # keeps the early crowd from leaving at 10
    "sallys_tuesday_deal":        0.30,   # $2 taps on an otherwise slow night
    # Kollege Klub
    "kk_tuesday":                 0.70,   # UMN institution — biggest single weekly lift
    "kk_thursday":                0.40,   # competes with Blarney's karaoke for same crowd
    "kk_friday_after_class":      0.35,   # right after 3 PM class release
}


# ── 3. Drinking holidays ─────────────────────────────────────────────────────
# Relative intensity of each holiday (arbitrary scale, higher = more impact).
# Affects two places:
#   a) FeatureBuilder: builds a composite `drinking_holiday_weight` feature column
#   b) Training: rows on a holiday get extra sample weight so the RF fits them tightly

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

# Training rows that fall on a drinking holiday get this sample-weight multiplier
# so the RandomForest pays much more attention to these rare high-traffic nights.
HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER: float = 10.0


# ── 4. Model hyperparameters ─────────────────────────────────────────────────
# Changing these requires a model retrain (restart Streamlit or re-run models/train.py).

TEST_SPLIT_DAYS  = 14    # hold-out the last N days for evaluation; not used in training
RANDOM_SEED      = 42
RF_N_ESTIMATORS  = 200   # more trees → lower variance, slower training
RF_MAX_DEPTH     = 10    # shallower → less overfitting on sparse holiday rows


# ── 5. Operating hours ───────────────────────────────────────────────────────
BAR_OPEN_HOUR  = 14   # 2 PM  — predictions outside this window use floor values
BAR_CLOSE_HOUR = 2    # 2 AM  (next day)

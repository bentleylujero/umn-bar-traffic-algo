"""Training pipeline: load data → build features → fit baseline + ML model.

Usage:
    python -m models.train
"""

from __future__ import annotations

import logging
import sqlite3

import numpy as np
import pandas as pd

from config.settings import DRINKING_HOLIDAY_WEIGHTS, HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER
from data.db import get_connection, init_db
from features.builder import FeatureBuilder
from models.baseline import BaselineModel
from models.ml_model import WaitTimeModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_observations(conn: sqlite3.Connection) -> pd.DataFrame:
    """Join observations with signals into a flat DataFrame."""
    query = """
        SELECT
            o.id                AS observation_id,
            o.bar_id,
            b.name              AS bar_name,
            o.observed_at,
            o.wait_minutes,
            o.pct_full,
            o.drink_wait_minutes,
            o.cover_charge,
            -- Weather
            s.temperature_c,
            s.precipitation_mm,
            s.wind_chill_c,
            s.snowfall_mm,
            s.wind_speed_ms,
            COALESCE(s.is_severe_weather,   0) AS is_severe_weather,
            s.cloud_cover,
            COALESCE(s.is_first_nice_day,   0) AS is_first_nice_day,
            -- Legacy flags
            COALESCE(s.is_game_day,         0) AS is_game_day,
            COALESCE(s.is_holiday,          0) AS is_holiday,
            -- Athletics
            COALESCE(s.is_football_home,    0) AS is_football_home,
            COALESCE(s.is_basketball_home,  0) AS is_basketball_home,
            COALESCE(s.is_hockey_home,      0) AS is_hockey_home,
            s.hours_until_game,
            COALESCE(s.is_rivalry_game,     0) AS is_rivalry_game,
            -- Academic calendar
            COALESCE(s.classes_in_session,  0) AS classes_in_session,
            COALESCE(s.is_finals_week,      0) AS is_finals_week,
            COALESCE(s.is_welcome_week,     0) AS is_welcome_week,
            COALESCE(s.is_break,            0) AS is_break,
            COALESCE(s.is_summer_session,   0) AS is_summer_session,
            s.week_of_semester,
            -- Events
            COALESCE(s.is_st_patricks,           0) AS is_st_patricks,
            COALESCE(s.is_halloween,             0) AS is_halloween,
            COALESCE(s.is_homecoming,            0) AS is_homecoming,
            COALESCE(s.is_bar_crawl,             0) AS is_bar_crawl,
            COALESCE(s.is_blackout_wednesday,    0) AS is_blackout_wednesday,
            COALESCE(s.is_new_years_eve,         0) AS is_new_years_eve,
            -- External sports (bar-watching TV events)
            COALESCE(s.is_twins_home,            0) AS is_twins_home,
            COALESCE(s.is_nfl_game_day,          0) AS is_nfl_game_day,
            COALESCE(s.is_nfl_playoffs,          0) AS is_nfl_playoffs,
            COALESCE(s.is_super_bowl,            0) AS is_super_bowl,
            COALESCE(s.is_vikings_game,          0) AS is_vikings_game,
            COALESCE(s.is_cfb_saturday,          0) AS is_cfb_saturday,
            COALESCE(s.is_cfb_championship,      0) AS is_cfb_championship,
            COALESCE(s.is_march_madness,         0) AS is_march_madness,
            COALESCE(s.is_march_madness_elite,   0) AS is_march_madness_elite,
            COALESCE(s.is_nba_playoffs,          0) AS is_nba_playoffs,
            COALESCE(s.is_wild_game,             0) AS is_wild_game,
            COALESCE(s.is_timberwolves_game,     0) AS is_timberwolves_game,
            COALESCE(s.is_nhl_playoffs,          0) AS is_nhl_playoffs,
            s.tv_game_hour,
            COALESCE(s.tv_game_weight,         0.0) AS tv_game_weight,
            -- Academic (expanded)
            COALESCE(s.is_midterms_week,         0) AS is_midterms_week,
            COALESCE(s.is_syllabus_week,         0) AS is_syllabus_week,
            s.days_until_break,
            COALESCE(s.is_study_days,            0) AS is_study_days,
            COALESCE(s.is_commencement,          0) AS is_commencement,
            s.days_since_semester_start,
            COALESCE(s.is_cinco_de_mayo,         0) AS is_cinco_de_mayo,
            COALESCE(s.is_parents_weekend,       0) AS is_parents_weekend
        FROM observations o
        JOIN bars b ON b.id = o.bar_id
        LEFT JOIN signals s ON s.observation_id = o.id
        ORDER BY o.observed_at
    """
    df = pd.read_sql_query(query, conn)
    df["observed_at"] = pd.to_datetime(df["observed_at"], format="ISO8601", utc=True)
    return df


def run_training(add_lag_features: bool = False) -> dict:
    """Full training run — fits one model pair per target metric.

    Returns
    -------
    dict with keys:
        "wait"     : (BaselineModel, WaitTimeModel) for line wait
        "pct_full" : (BaselineModel, WaitTimeModel) for bar fullness
        "drink"    : (BaselineModel, WaitTimeModel) for drink wait
        "df_feat"  : pd.DataFrame  — the feature matrix used for training
    """
    init_db()
    conn = get_connection()
    df_raw = load_observations(conn)
    conn.close()

    if df_raw.empty:
        raise RuntimeError(
            "No observations in the database. Run `python -m data.seed` first."
        )

    log.info("Loaded %d raw observations.", len(df_raw))

    fb = FeatureBuilder(add_lag_features=add_lag_features)
    df_feat = fb.build(df_raw)
    feature_cols = fb.feature_columns(df_feat)
    log.info("Feature columns: %s", feature_cols)

    # Build per-row sample weights: drinking-holiday rows get a large multiplier
    # so the RandomForest pays much more attention to those rare, high-impact nights.
    holiday_cols = [c for c in DRINKING_HOLIDAY_WEIGHTS if c in df_feat.columns]
    is_holiday = (df_feat[holiday_cols].fillna(0) > 0).any(axis=1)
    sample_weight = np.where(is_holiday, HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER, 1.0)
    n_holiday = int(is_holiday.sum())
    log.info(
        "Sample weights: %d holiday rows × %.1f, %d normal rows × 1.0",
        n_holiday, HOLIDAY_SAMPLE_WEIGHT_MULTIPLIER, len(df_feat) - n_holiday,
    )

    result: dict = {"df_feat": df_feat}

    for target, key in [
        ("wait_minutes",       "wait"),
        ("pct_full",           "pct_full"),
        ("drink_wait_minutes", "drink"),
    ]:
        baseline = BaselineModel(target_col=target)
        baseline.fit(df_feat)

        ml = WaitTimeModel(feature_cols=feature_cols, target_col=target)
        ml.fit(df_feat, sample_weight=sample_weight)

        log.info(
            "[%s] Train MAE=%.2f  Test MAE=%s",
            target,
            ml.train_metrics.get("mae", float("nan")),
            f"{ml.test_metrics['mae']:.2f}" if ml.test_metrics else "n/a",
        )
        result[key] = (baseline, ml)

    log.info("Training complete.")
    return result


if __name__ == "__main__":
    models = run_training()
    for key in ("wait", "pct_full", "drink"):
        _, ml = models[key]
        print(f"\n=== {key} ===")
        print("Feature importances:")
        print(ml.feature_importances_.to_string())
        print("Test metrics:", ml.test_metrics)

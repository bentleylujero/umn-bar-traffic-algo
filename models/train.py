"""Training pipeline: load data → build features → fit baseline + ML model.

Usage:
    python -m models.train
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

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
            o.id           AS observation_id,
            o.bar_id,
            b.name         AS bar_name,
            o.observed_at,
            o.wait_minutes,
            s.temperature_c,
            s.precipitation_mm,
            COALESCE(s.is_game_day, 0) AS is_game_day,
            COALESCE(s.is_holiday, 0)  AS is_holiday
        FROM observations o
        JOIN bars b ON b.id = o.bar_id
        LEFT JOIN signals s ON s.observation_id = o.id
        ORDER BY o.observed_at
    """
    return pd.read_sql_query(query, conn, parse_dates=["observed_at"])


def run_training(add_lag_features: bool = False) -> tuple[BaselineModel, WaitTimeModel, pd.DataFrame]:
    """Full training run.

    Returns
    -------
    baseline : BaselineModel
    ml_model : WaitTimeModel
    df_features : pd.DataFrame  — the feature matrix used for training
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

    # Feature engineering
    fb = FeatureBuilder(add_lag_features=add_lag_features)
    df_feat = fb.build(df_raw)
    feature_cols = fb.feature_columns(df_feat)
    log.info("Feature columns: %s", feature_cols)

    # Baseline
    baseline = BaselineModel()
    baseline.fit(df_feat)

    # ML model
    ml = WaitTimeModel(feature_cols=feature_cols)
    ml.fit(df_feat)

    log.info("Training complete.")
    if ml.test_metrics:
        log.info(
            "ML test  → MAE=%.2f min  RMSE=%.2f min",
            ml.test_metrics["mae"],
            ml.test_metrics["rmse"],
        )

    return baseline, ml, df_feat


if __name__ == "__main__":
    baseline, ml, _ = run_training()
    print("\nFeature importances:")
    print(ml.feature_importances_.to_string())
    print("\nTest metrics:", ml.test_metrics)

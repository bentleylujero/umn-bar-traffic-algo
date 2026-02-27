"""Predictor node — wraps existing ML and baseline models.

Adapted to the actual models/train.py API:
  - run_training() returns {"wait": (BaselineModel, WaitTimeModel), ...}
  - BaselineModel.predict_one(bar_id, day_of_week, hour) — not predict_one(bar_id, datetime)
  - WaitTimeModel.predict_one(feature_dict) — dict must have model's feature_cols as keys
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)


class PredictorNode:
    """Runs wait-time prediction using ML model with baseline fallback."""

    node_type = "predictor"

    def execute(self, config: dict, inputs: dict) -> dict:
        """Run predictions for all bars using features from upstream nodes.

        Expects inputs to contain a 'features' key from FeatureExtractorNode.
        Returns predictions keyed by bar_id.
        """
        from config.settings import BARS

        # Find the feature dict from upstream FeatureExtractorNode output
        features_by_bar: dict[int, dict] = {}
        feature_cols: list[str] = []
        for val in inputs.values():
            if isinstance(val, dict) and "features" in val:
                features_by_bar = val["features"]
                feature_cols = val.get("feature_columns", [])
                break

        if not features_by_bar:
            return {"predictions": {}, "error": "No features found in inputs"}

        predictions: dict[int, dict] = {}

        # Train once for all bars (avoid re-training per bar)
        ml_model = None
        ml_error: str | None = None
        try:
            ml_model = _load_ml_model(features_by_bar)
        except Exception as exc:
            ml_error = str(exc)
            log.warning("ML model training failed: %s — falling back to baseline", exc)

        for bar_id, feat_dict in features_by_bar.items():
            bar_name = BARS[bar_id - 1]["name"] if bar_id <= len(BARS) else f"Bar {bar_id}"

            if ml_model is not None:
                try:
                    pred_dict = {c: feat_dict.get(c, 0) for c in ml_model.feature_cols}
                    wait = max(0.0, float(ml_model.predict_one(pred_dict)))
                    model_used = "ml"
                except Exception as exc:
                    log.warning("ML predict failed for bar_id=%d: %s", bar_id, exc)
                    ml_model = None  # disable for remaining bars too
                    ml_error = str(exc)
                    try:
                        wait = _predict_baseline(bar_id, feat_dict)
                        model_used = "baseline"
                    except Exception as exc2:
                        log.warning("Baseline also failed for bar_id=%d: %s", bar_id, exc2)
                        wait = 10.0
                        model_used = "fallback_default"
            else:
                try:
                    wait = _predict_baseline(bar_id, feat_dict)
                    model_used = "baseline"
                except Exception as exc2:
                    log.warning(
                        "Baseline also failed for bar_id=%d: %s — using default", bar_id, exc2
                    )
                    wait = 10.0
                    model_used = "fallback_default"

            # Convert wait minutes to pct_full heuristic (45min = 100% full)
            pct_full = min(1.0, wait / 45.0)
            confidence = "high" if model_used == "ml" else ("medium" if model_used == "baseline" else "low")

            predictions[bar_id] = {
                "bar_id":                   bar_id,
                "bar_name":                 bar_name,
                "predicted_wait_minutes":   round(wait, 1),
                "predicted_pct_full":       round(pct_full, 3),
                "confidence":               confidence,
                "model_used":               model_used,
                "signals_used":             {},
            }

        return {"predictions": predictions}


def _load_ml_model(features_by_bar: dict):
    """Train the ML model once and return it.

    Uses run_training() from models/train.py which is the actual public API.
    Raises on insufficient data or training failure.
    """
    from data.db import get_connection
    from models.train import run_training

    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    finally:
        conn.close()

    if count < 50:
        raise ValueError(f"Insufficient training data: {count} rows (need >= 50)")

    # run_training() returns {"wait": (BaselineModel, WaitTimeModel), "df_feat": df, ...}
    training_result = run_training()
    _, ml_model = training_result["wait"]
    return ml_model


def _predict_baseline(bar_id: int, feat_dict: dict) -> float:
    """Baseline model prediction using historical medians.

    BaselineModel.predict_one() requires (bar_id, day_of_week, hour).
    We extract day_of_week and hour from feat_dict if available,
    otherwise fall back to the current time.
    """
    from data.db import get_connection
    from features.builder import FeatureBuilder
    from models.baseline import BaselineModel

    conn = get_connection()
    try:
        import pandas as pd

        df = pd.read_sql_query("SELECT * FROM observations", conn)
    finally:
        conn.close()

    if df.empty:
        raise ValueError("No observations in DB for baseline model")

    fb = FeatureBuilder()
    df_feat = fb.build(df)

    bm = BaselineModel(target_col="wait_minutes")
    bm.fit(df_feat)

    # Extract day_of_week and hour from feat_dict, fall back to current time
    now = datetime.now(timezone.utc)
    day_of_week = int(feat_dict.get("day_of_week", now.weekday()))
    hour = int(feat_dict.get("hour", now.hour))

    return bm.predict_one(bar_id, day_of_week, hour)

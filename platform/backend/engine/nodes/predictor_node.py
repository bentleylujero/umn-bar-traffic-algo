"""Predictor node — wraps existing ML and baseline models.

Adapted to the actual models/train.py API:
  - run_training() returns {"wait": (BaselineModel, WaitTimeModel), ...}
  - BaselineModel.predict_one(bar_id, day_of_week, hour) — not predict_one(bar_id, datetime)
  - WaitTimeModel.predict_one(feature_dict) — dict must have model's feature_cols as keys

Model cache
-----------
Training is expensive (~2–5 s).  We train lazily on the first predict request
and cache the result at module level.  The cache is invalidated when the
observation count grows by at least NEW_OBS_RETRAIN_THRESHOLD rows (i.e. after
manual check-ins) OR after MAX_CACHE_AGE_S seconds (24 h backstop).

Call `invalidate_model_cache()` to force a retrain on the next request.
Call `model_cache_status()` to inspect the current cache state.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ── Cache config ──────────────────────────────────────────────────────────────
# Retrain when at least this many new observations have been added since the
# last train (e.g. from manual check-ins via the headcount panel).
NEW_OBS_RETRAIN_THRESHOLD = 3
# Hard upper bound: retrain even with no new data after this many seconds.
MAX_CACHE_AGE_S = 24 * 3600  # 24 hours

# ── Module-level cache (shared across all requests / nodes) ───────────────────
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


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

        # Load (or serve from cache) — only retrains when cache is stale/empty
        ml_model = None
        ml_error: str | None = None
        try:
            result = _get_models()
            _, ml_model = result["wait"]
        except Exception as exc:
            ml_error = str(exc)
            log.warning("ML model unavailable: %s — falling back to baseline", exc)

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


def _obs_count() -> int:
    """Return the current number of rows in the observations table."""
    from data.db import get_connection

    conn = get_connection()
    try:
        return conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    finally:
        conn.close()


def _do_train() -> dict:
    """Run run_training() and return its full result dict. Always slow."""
    from models.train import run_training

    log.info("Training models (cache miss)…")
    t0 = time.perf_counter()
    result = run_training()
    elapsed = time.perf_counter() - t0
    log.info("Training complete in %.1f s", elapsed)
    return result


def _cache_is_valid(count: int) -> bool:
    """Return True if the cache is populated and still fresh."""
    if not _cache:
        return False
    age = time.time() - _cache["trained_at"]
    new_obs = count - _cache["obs_count"]
    return age < MAX_CACHE_AGE_S and new_obs < NEW_OBS_RETRAIN_THRESHOLD


def _get_models() -> dict:
    """Return the cached training result, retraining only when necessary.

    Thread-safe.  Blocks concurrent callers on the first (cold) train so we
    don't launch N parallel run_training() calls.
    """
    with _cache_lock:
        count = _obs_count()
        if _cache_is_valid(count):
            return _cache["result"]

        if count < 50:
            raise ValueError(
                f"Insufficient training data: {count} rows (need >= 50)"
            )

        result = _do_train()
        _cache.clear()
        _cache["result"] = result
        _cache["obs_count"] = count
        _cache["trained_at"] = time.time()
        return result


def invalidate_model_cache() -> None:
    """Force a retrain on the next predict request."""
    with _cache_lock:
        _cache.clear()
    log.info("Model cache invalidated — will retrain on next request.")


def model_cache_status() -> dict:
    """Return a dict describing the current cache state (for /models/status)."""
    with _cache_lock:
        if not _cache:
            return {"status": "untrained", "obs_count": None, "trained_at": None, "age_s": None}
        age = time.time() - _cache["trained_at"]
        return {
            "status": "cached",
            "obs_count": _cache["obs_count"],
            "trained_at": datetime.fromtimestamp(
                _cache["trained_at"], tz=timezone.utc
            ).isoformat(),
            "age_s": round(age),
            "expires_in_s": max(0, round(MAX_CACHE_AGE_S - age)),
            "retrain_threshold": NEW_OBS_RETRAIN_THRESHOLD,
        }


def _predict_baseline(bar_id: int, feat_dict: dict) -> float:
    """Baseline model prediction — uses cached training result."""
    result = _get_models()
    bm, _ = result["wait"]

    now = datetime.now(timezone.utc)
    day_of_week = int(feat_dict.get("day_of_week", now.weekday()))
    hour = int(feat_dict.get("hour", now.hour))
    return bm.predict_one(bar_id, day_of_week, hour)

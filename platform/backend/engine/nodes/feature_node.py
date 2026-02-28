"""Feature extraction node — wraps existing features/builder.py."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)


class FeatureExtractorNode:
    """Assembles all upstream signals into a feature row for each bar."""

    node_type = "feature_extractor"

    def execute(self, config: dict, inputs: dict) -> dict:
        """Merge upstream signal dicts and build per-bar feature rows.

        Parameters
        ----------
        config : dict
            Expected keys:
                datetime : str | datetime — the reference time (defaults to now)
                bar_ids  : list[int]      — bars to compute features for
        inputs : dict
            Merged dict of all upstream node outputs (keyed by node_id).

        Returns
        -------
        dict with keys:
            features        : dict[bar_id, dict[str, float]]
            feature_columns : list[str]
        """
        from config.settings import BARS
        from features.builder import FeatureBuilder

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        # Merge all upstream signal dicts into one flat signals dict
        signals: dict = {}
        for val in inputs.values():
            if isinstance(val, dict):
                # popular_times returns {bar_id: {...}} — skip nested dicts
                # that are keyed by integer (popular times per bar)
                for k, v in val.items():
                    if not isinstance(v, dict):
                        signals[k] = v
                    # leave bar-keyed popular times dicts out of flat signals
                    pass
            
            # Handle crowd_reports specifically (they are bar-specific)
            crowd_reports = inputs.get("crowd_reports", {}).get("crowd_reports", {})

        # >>> DATA WARDEN LAYER <<<
        # Validate data to ensure the model does not ingest outdated/irrelevant information
        from platform.backend.engine.warden import DataWarden
        warden = DataWarden(ref_time=dt)
        signals = warden.validate_signals(signals)
        crowd_reports = warden.validate_crowd_reports(crowd_reports)

        fb = FeatureBuilder()
        results: dict[int, dict] = {}

        bar_ids: list[int] = config.get("bar_ids") or [b_idx + 1 for b_idx in range(len(BARS))]

        for bar_id in bar_ids:
            # Build a minimal observation row for feature engineering
            row = {
                "observed_at": dt,
                "bar_id":      bar_id,
                "wait_minutes": 0.0,  # placeholder — not used for prediction
                **signals,
                **crowd_reports.get(bar_id, {}),
            }
            df = pd.DataFrame([row])
            df = fb.build(df)
            feat_cols = fb.feature_columns(df)
            results[bar_id] = df[feat_cols].iloc[0].to_dict()

        feature_columns = list(results[bar_ids[0]].keys()) if results else []

        return {
            "features":        results,
            "feature_columns": feature_columns,
        }

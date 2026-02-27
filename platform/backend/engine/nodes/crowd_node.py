"""Crowd report pipeline node — fetches recent live signals from the DB."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)


class CrowdReportNode:
    """Fetches the most recent crowd-sourced reports from the DB."""

    node_type = "crowd_reports"

    def execute(self, config: dict, inputs: dict) -> dict:
        """Fetch latest observations for all bars within a recent window.
        
        Parameters
        ----------
        config : dict
            Expected keys:
                window_minutes : int — how far back to look (default 60)
        """
        from data.db import get_connection

        window_mins = config.get("window_minutes", 60)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_mins)).isoformat()

        conn = get_connection()
        try:
            # For each bar, get the most recent observation in the window
            query = """
                SELECT bar_id, wait_minutes, pct_full
                FROM observations
                WHERE observed_at >= ?
                GROUP BY bar_id
                HAVING observed_at = MAX(observed_at)
            """
            rows = conn.execute(query, (cutoff,)).fetchall()
            
            # Aggregate into signal fields
            # Since FeatureExtractor merges all upstream dicts, we return a flat dict 
            # with bar-specific keys that the FeatureExtractor can handle if we 
            # adapt it, OR we return global signals.
            # To keep it simple and compatible with PredictorNode's expectation of 
            # flat signals, we'll return them per-bar in a structured way.
            
            live_signals: dict[int, dict] = {}
            for row in rows:
                live_signals[row["bar_id"]] = {
                    "live_wait_minutes": row["wait_minutes"],
                    "live_pct_full": row["pct_full"]
                }
            
            return {"crowd_reports": live_signals}
        finally:
            conn.close()

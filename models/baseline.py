"""Baseline model: median wait time grouped by (bar_id, day_of_week, hour).

This is a simple lookup table — no ML, interpretable, and hard to beat
on sparse data. It serves as the benchmark for the RandomForest model.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

# Fallback when a group has no historical data
_GLOBAL_FALLBACK_MINUTES = 10.0


class BaselineModel:
    """Predict wait time using the historical median for the same slot.

    The "slot" is (bar_id, day_of_week, hour).  A coarser fallback
    (bar_id, day_of_week) → (bar_id,) → global median is used when the
    exact slot has no data.
    """

    def __init__(self, target_col: str = "wait_minutes") -> None:
        self.target_col = target_col
        self._table: pd.DataFrame | None = None
        self._fallback_bar: pd.Series | None = None      # bar_id → median
        self._fallback_dow: pd.Series | None = None      # day_of_week → median
        self._global_median: float = _GLOBAL_FALLBACK_MINUTES

    # ── Fitting ───────────────────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> "BaselineModel":
        """Compute the lookup table from the training DataFrame.

        Required columns: bar_id, day_of_week, hour, wait_minutes.
        """
        required = {"bar_id", "day_of_week", "hour", self.target_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"BaselineModel.fit: missing columns {missing}")

        self._table = (
            df.groupby(["bar_id", "day_of_week", "hour"])[self.target_col]
            .median()
            .rename("predicted_val")
            .reset_index()
        )

        self._fallback_bar = (
            df.groupby("bar_id")[self.target_col].median()
        )
        self._fallback_dow = (
            df.groupby("day_of_week")[self.target_col].median()
        )
        self._global_median = float(df[self.target_col].median())
        log.info(
            "BaselineModel fitted on %d rows, %d unique slots",
            len(df),
            len(self._table),
        )
        return self

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of predicted wait minutes, one per row of *df*.

        Required columns: bar_id, day_of_week, hour.
        """
        if self._table is None:
            raise RuntimeError("Call fit() before predict().")

        results = []
        for _, row in df.iterrows():
            bid, dow, hr = row["bar_id"], row["day_of_week"], row["hour"]
            pred = self._lookup(bid, dow, hr)
            results.append(pred)
        return pd.Series(results, index=df.index, name="baseline_pred")

    def predict_one(self, bar_id: int, day_of_week: int, hour: int) -> float:
        """Convenience: predict for a single observation."""
        if self._table is None:
            raise RuntimeError("Call fit() before predict_one().")
        return self._lookup(bar_id, day_of_week, hour)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _lookup(self, bar_id: int, day_of_week: int, hour: int) -> float:
        mask = (
            (self._table["bar_id"] == bar_id)
            & (self._table["day_of_week"] == day_of_week)
            & (self._table["hour"] == hour)
        )
        rows = self._table[mask]
        if not rows.empty:
            return float(rows.iloc[0]["predicted_val"])

        # Fallback 1: same bar, any time
        if bar_id in self._fallback_bar.index:  # type: ignore[union-attr]
            return float(self._fallback_bar[bar_id])  # type: ignore[index]

        # Fallback 2: same day-of-week
        if day_of_week in self._fallback_dow.index:  # type: ignore[union-attr]
            return float(self._fallback_dow[day_of_week])  # type: ignore[index]

        return self._global_median

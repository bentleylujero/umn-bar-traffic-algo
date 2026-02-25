"""Feature engineering for bar wait-time prediction.

Usage
-----
    from features.builder import FeatureBuilder

    fb = FeatureBuilder()
    df_features = fb.build(df_raw)

The raw DataFrame must contain at least:
    - observed_at  : datetime (tz-aware or naive UTC)
    - bar_id       : int
    - wait_minutes : float  (the target — preserved, not used as a feature)

Optional columns (passed through if present):
    - temperature_c, precipitation_mm, is_game_day, is_holiday
"""

from __future__ import annotations

import pandas as pd


# ── Time-based feature names ─────────────────────────────────────────────────
TIME_FEATURES = [
    "hour",
    "day_of_week",
    "is_weekend",
    "month",
    "week_of_year",
    "is_late_night",   # 12 AM–2 AM  (bars still open, crowd maxes)
]

# ── Signal feature names (present only when signals table is joined) ──────────
SIGNAL_FEATURES = [
    "temperature_c",
    "precipitation_mm",
    "is_game_day",
    "is_holiday",
]

ALL_FEATURES = TIME_FEATURES + ["bar_id"] + SIGNAL_FEATURES


class FeatureBuilder:
    """Transforms raw observation rows into an ML-ready feature matrix.

    Parameters
    ----------
    add_lag_features : bool
        If True, compute lag features (requires enough historical data per bar).
    lag_hours : list[int]
        Which hourly lags to compute when add_lag_features=True.
    """

    def __init__(
        self,
        add_lag_features: bool = False,
        lag_hours: list[int] | None = None,
    ) -> None:
        self.add_lag_features = add_lag_features
        self.lag_hours = lag_hours or [1, 2, 4, 7 * 24]  # 1h, 2h, 4h, one week

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a new DataFrame with all engineered features appended.

        The original columns are preserved; engineered columns are added.
        The returned DataFrame is sorted by observed_at.
        """
        df = df.copy()
        df = self._ensure_datetime(df)
        df = df.sort_values("observed_at").reset_index(drop=True)
        df = self._add_time_features(df)

        if self.add_lag_features:
            df = self._add_lag_features(df)

        return df

    def feature_columns(self, df: pd.DataFrame) -> list[str]:
        """Return the list of feature column names present in *df*."""
        candidates = TIME_FEATURES + ["bar_id"] + SIGNAL_FEATURES
        if self.add_lag_features:
            lag_cols = self._lag_column_names()
            candidates = candidates + lag_cols
        return [c for c in candidates if c in df.columns]

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
        if not pd.api.types.is_datetime64_any_dtype(df["observed_at"]):
            df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
        return df

    @staticmethod
    def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
        ts = df["observed_at"].dt
        df["hour"] = ts.hour
        df["day_of_week"] = ts.dayofweek          # 0=Mon … 6=Sun
        df["is_weekend"] = (df["day_of_week"] >= 4).astype(int)  # Fri–Sun
        df["month"] = ts.month
        df["week_of_year"] = ts.isocalendar().week.astype(int)
        df["is_late_night"] = ((df["hour"] >= 0) & (df["hour"] <= 2)).astype(int)
        return df

    def _add_lag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add per-bar rolling lag features of wait_minutes.

        Observations are expected to be approximately hourly; lags are in hours.
        NaN-fills for early rows are left as-is (models handle them via imputation
        or the caller should drop rows with too many NaNs).
        """
        df = df.set_index("observed_at")
        lag_dfs = []
        for bar_id, group in df.groupby("bar_id"):
            group = group.sort_index()
            for lag in self.lag_hours:
                col = f"wait_lag_{lag}h"
                group[col] = (
                    group["wait_minutes"]
                    .shift(lag)          # shift by lag periods (≈hours)
                )
            lag_dfs.append(group)
        df = pd.concat(lag_dfs).sort_index().reset_index()
        return df

    def _lag_column_names(self) -> list[str]:
        return [f"wait_lag_{lag}h" for lag in self.lag_hours]

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
    Weather     : temperature_c, precipitation_mm, wind_chill_c, snowfall_mm,
                  wind_speed_ms, is_severe_weather, cloud_cover, is_first_nice_day
    Legacy      : is_game_day, is_holiday
    Athletics   : is_football_home, is_basketball_home, is_hockey_home,
                  hours_until_game, is_rivalry_game
    Academic    : classes_in_session, is_finals_week, is_welcome_week,
                  is_break, is_summer_session, week_of_semester
    Events      : is_st_patricks, is_halloween, is_homecoming, is_bar_crawl
    Observation : cover_charge
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── Time-based feature names ─────────────────────────────────────────────────
TIME_FEATURES = [
    "hour",
    "day_of_week",
    "hour_sin",        # cyclical encoding — avoids the 23→0 discontinuity
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",      # Fri–Sun
    "is_thursday",     # Wed/Thu are the college "going-out" nights
    "month",
    "week_of_year",
    "is_late_night",   # 12 AM–2 AM (bars still open, crowd maxes)
]

# ── Signal feature names (present only when signals/obs columns are joined) ──
SIGNAL_FEATURES = [
    # Weather
    "temperature_c",
    "precipitation_mm",
    "wind_chill_c",
    "snowfall_mm",
    "wind_speed_ms",
    "is_severe_weather",
    "cloud_cover",
    "is_first_nice_day",
    # Legacy game/holiday flags
    "is_game_day",
    "is_holiday",
    # Athletics (sport-specific)
    "is_football_home",
    "is_basketball_home",
    "is_hockey_home",
    "hours_until_game",
    "is_rivalry_game",
    # Academic calendar
    "classes_in_session",
    "is_finals_week",
    "is_welcome_week",
    "is_break",
    "is_summer_session",
    "week_of_semester",
    # Events
    "is_st_patricks",
    "is_halloween",
    "is_homecoming",
    "is_bar_crawl",
    "is_blackout_wednesday",
    "is_new_years_eve",
    # Sports (external to UMN — bar TV-watching signals)
    "is_twins_home",
    "is_nfl_game_day",
    "is_nfl_playoffs",
    "is_super_bowl",
    "is_vikings_game",
    "is_cfb_saturday",
    "is_cfb_championship",
    "is_march_madness",
    "is_march_madness_elite",
    "is_nba_playoffs",
    # MN-specific pro sports (Sally's has Wild + T-Wolves specials)
    "is_wild_game",
    "is_timberwolves_game",
    "is_nhl_playoffs",
    "tv_game_hour",
    "tv_game_weight",
    # Academic (expanded)
    "is_midterms_week",
    "is_syllabus_week",
    "days_until_break",
    # Academic (further expanded)
    "is_study_days",
    "is_commencement",
    "days_since_semester_start",
    # Events (expanded)
    "is_cinco_de_mayo",
    "is_parents_weekend",
    # Observation-level
    "cover_charge",
    # Bar-specific computed signals (not stored in DB — derived from bar_id + time)
    "is_happy_hour",
    "is_bar_special",
    "minutes_into_special",
    # Continuous late-night migration draw (0 at 10pm → 1.0 at 2am, Blarney's only)
    "bar_late_draw",
    # Composite drinking-holiday intensity (0 on normal nights; higher = bigger holiday).
    # Aggregates is_st_patricks, is_halloween, etc. into a single continuous signal
    # so the RF can split strongly on holiday magnitude rather than each sparse flag.
    "drinking_holiday_weight",
    # Greek life social calendar
    "is_greek_rush_week",       # IFC/PHC recruitment week — suppresses general bar traffic
    "is_greek_bid_day",         # Bid day ± 1 day — single biggest Greek bar night
    "is_greek_formal_season",   # Oct-Nov (fall) + Mar-Apr (spring) date-party season
    "is_greek_week",            # Spring Greek Week (~2 weeks before spring finals)
    "is_greek_thursday",        # Thursday during active semester (canonical Greek bar night)
    "is_greek_pregame_window",  # 7–10 PM Thu/Fri/Sat — pre-event bar surge window
    "greek_social_intensity",   # Continuous 0–1 composite (higher = more Greek bar traffic)
    # Live ingestion signals
    "live_wait_minutes",
    "live_pct_full",
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
        # Ensure all signal features are present (default to 0.0 for live signals)
        from features.builder import SIGNAL_FEATURES
        for col in SIGNAL_FEATURES:
            if col not in df.columns:
                df[col] = 0.0 if col.startswith("live_") else np.nan
        
        df = df.copy()
        df = self._ensure_datetime(df)
        df = df.sort_values("observed_at").reset_index(drop=True)
        df = self._add_time_features(df)
        df = self._add_bar_schedule_features(df)
        df = self._add_drinking_holiday_weight(df)

        if self.add_lag_features:
            df = self._add_lag_features(df)

        return df

    def feature_columns(self, df: pd.DataFrame) -> list[str]:
        """Return the list of feature column names present in *df*."""
        candidates = TIME_FEATURES + ["bar_id"] + SIGNAL_FEATURES
        if self.add_lag_features:
            candidates = candidates + self._lag_column_names()
        return [c for c in candidates if c in df.columns]

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
        if not pd.api.types.is_datetime64_any_dtype(df["observed_at"]):
            df["observed_at"] = pd.to_datetime(df["observed_at"], format="ISO8601", utc=True)
        return df

    @staticmethod
    def _add_time_features(df: pd.DataFrame) -> pd.DataFrame:
        ts = df["observed_at"].dt

        df["hour"]        = ts.hour
        df["day_of_week"] = ts.dayofweek                              # 0=Mon … 6=Sun

        # Cyclical encodings — eliminate artificial discontinuity at period boundaries
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
        df["dow_sin"]  = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"]  = np.cos(2 * np.pi * df["day_of_week"] / 7)

        df["is_weekend"]  = (df["day_of_week"] >= 4).astype(int)     # Fri–Sun
        df["is_thursday"] = (df["day_of_week"] == 3).astype(int)     # Thu bar night
        df["month"]       = ts.month
        df["week_of_year"]= ts.isocalendar().week.astype(int)
        df["is_late_night"]= ((df["hour"] >= 0) & (df["hour"] <= 2)).astype(int)

        return df

    @staticmethod
    def _add_bar_schedule_features(df: pd.DataFrame) -> pd.DataFrame:
        """Compute happy-hour and weekly-special flags from bar_id + timestamp.

        These signals are deterministic given (bar_id, observed_at) so they
        are computed here rather than stored in the DB.
        """
        from config.settings import BAR_SCHEDULES

        df["is_happy_hour"]        = 0
        df["is_bar_special"]       = 0
        df["minutes_into_special"] = 0.0
        df["bar_late_draw"]        = 0.0

        frac = df["observed_at"].dt.hour + df["observed_at"].dt.minute / 60.0
        dow  = df["observed_at"].dt.dayofweek   # 0=Mon … 6=Sun

        for bar_id, sched in BAR_SCHEDULES.items():
            bar_mask = df["bar_id"] == bar_id
            if not bar_mask.any():
                continue

            # ── Happy hour ────────────────────────────────────────────────
            hh = sched.get("happy_hour")
            if hh:
                s_frac = hh["start"][0] + hh["start"][1] / 60.0
                e_frac = hh["end"][0]   + hh["end"][1]   / 60.0
                hh_mask = bar_mask & dow.isin(hh["days"]) & (frac >= s_frac) & (frac < e_frac)
                df.loc[hh_mask, "is_happy_hour"]       = 1
                df.loc[hh_mask, "minutes_into_special"] = (frac[hh_mask] - s_frac) * 60.0

            # ── Weekly specials ───────────────────────────────────────────
            # "days" (list) is preferred; "day" (int) is kept for back-compat
            for special in sched.get("weekly_specials", []):
                s_frac   = special["start"][0] + special["start"][1] / 60.0
                e_frac   = special["end"][0]   + special["end"][1]   / 60.0
                sp_days  = special.get("days") or [special["day"]]

                if e_frac <= 24:
                    # Same-day special
                    sp_mask = bar_mask & dow.isin(sp_days) & (frac >= s_frac) & (frac < e_frac)
                    mins    = (frac[sp_mask] - s_frac) * 60.0
                else:
                    # Overnight — spans into the next calendar day
                    e_frac_next  = e_frac - 24.0
                    next_sp_days = [(d + 1) % 7 for d in sp_days]
                    same_day = bar_mask & dow.isin(sp_days)      & (frac >= s_frac)
                    next_day = bar_mask & dow.isin(next_sp_days) & (frac <  e_frac_next)
                    sp_mask  = same_day | next_day
                    mins     = pd.Series(0.0, index=df.index)
                    mins[same_day] = (frac[same_day] - s_frac) * 60.0
                    mins[next_day] = (frac[next_day] + 24.0 - s_frac) * 60.0
                    mins = mins[sp_mask]

                df.loc[sp_mask, "is_bar_special"]      = 1
                df.loc[sp_mask, "minutes_into_special"] = np.maximum(
                    df.loc[sp_mask, "minutes_into_special"], mins
                )

            # ── Late-night migration draw (Blarney's effect) ──────────────
            # After 10pm the crowd at this bar grows because drunk people
            # migrate here from cheaper bars. Gradient: 0 at 22:00 → 1 at 02:00.
            if sched.get("late_night_draw"):
                h = df.loc[bar_mask, "observed_at"].dt.hour
                # Treat post-midnight hours as 24+h for a continuous scale
                h_adj = h.copy().astype(float)
                h_adj[h <= 2] = h[h <= 2] + 24.0   # 0→24, 1→25, 2→26
                draw = ((h_adj - 22.0) / 4.0).clip(lower=0.0, upper=1.0)
                df.loc[bar_mask, "bar_late_draw"] = draw.values

        return df

    @staticmethod
    def _add_drinking_holiday_weight(df: pd.DataFrame) -> pd.DataFrame:
        """Build a composite drinking-holiday intensity feature.

        For each row, sums the configured weights for every active holiday flag.
        Result is 0 on normal nights and scales up with holiday magnitude, giving
        the RandomForest a single continuous signal to split on instead of many
        sparse binary flags.
        """
        from config.settings import DRINKING_HOLIDAY_WEIGHTS

        weight = pd.Series(0.0, index=df.index)
        for col, w in DRINKING_HOLIDAY_WEIGHTS.items():
            if col in df.columns:
                weight += df[col].fillna(0).astype(float) * w
        df["drinking_holiday_weight"] = weight
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
                group[col] = group["wait_minutes"].shift(lag)
            lag_dfs.append(group)
        df = pd.concat(lag_dfs).sort_index().reset_index()
        return df

    def _lag_column_names(self) -> list[str]:
        return [f"wait_lag_{lag}h" for lag in self.lag_hours]

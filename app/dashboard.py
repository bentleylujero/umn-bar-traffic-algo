"""UMN Bar Line Forecasting Dashboard — Streamlit entry point.

Run with:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path when running via `streamlit run app/dashboard.py`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import altair as alt
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from config.settings import BARS
from data.db import init_db
from features.builder import FeatureBuilder
from models.train import run_training
from app.utils import (
    get_weather, get_today_signals, insert_observation,
    recent_observations, fetch_observation, update_observation,
    delete_observations
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UMN Bar Forecast",
    page_icon="🍺",
    layout="wide",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar_name_to_id(name: str, df: pd.DataFrame) -> int | None:
    rows = df[df["bar_name"] == name]
    if rows.empty:
        return None
    return int(rows.iloc[0]["bar_id"])


@st.cache_resource(show_spinner="Training models…")
def _get_models():
    """Train all 3 model pairs once per session."""
    try:
        return run_training()
    except RuntimeError as exc:
        return {"error": str(exc)}


_FACTOR_LABELS: dict[str, str] = {
    "is_weekend":             "Weekend",
    "is_thursday":            "Thursday",
    "is_late_night":          "Late night",
    "is_game_day":            "Game day",
    "is_holiday":             "Holiday",
    "is_severe_weather":      "Severe weather",
    "is_football_home":       "Football home",
    "is_basketball_home":     "Basketball home",
    "is_hockey_home":         "Hockey home",
    "is_rivalry_game":        "Rivalry game",
    "classes_in_session":     "Classes in session",
    "is_finals_week":         "Finals week",
    "is_welcome_week":        "Welcome week",
    "is_syllabus_week":       "Syllabus week",
    "is_midterms_week":       "Midterms week",
    "is_break":               "Break",
    "is_summer_session":      "Summer session",
    "is_st_patricks":         "St. Patrick's Day",
    "is_halloween":           "Halloween",
    "is_homecoming":          "Homecoming",
    "is_bar_crawl":           "Bar crawl",
    "is_blackout_wednesday":   "Blackout Wednesday",
    "is_new_years_eve":        "New Year's Eve",
    "is_twins_home":           "Twins home",
    "is_nfl_game_day":         "NFL on TV",
    "is_nfl_playoffs":         "NFL Playoffs",
    "is_super_bowl":           "Super Bowl",
    "is_vikings_game":         "Vikings game",
    "is_cfb_saturday":         "CFB Saturday",
    "is_cfb_championship":     "CFB Bowl/Championship",
    "is_march_madness":        "March Madness",
    "is_march_madness_elite":  "Final Four/Elite 8",
    "is_nba_playoffs":         "NBA Playoffs",
    "is_wild_game":            "Wild game",
    "is_timberwolves_game":    "Timberwolves game",
    "is_nhl_playoffs":         "NHL Playoffs",
    "is_first_nice_day":       "First nice spring day",
    "is_study_days":           "Study/reading days",
    "is_commencement":         "Commencement weekend",
    "is_cinco_de_mayo":        "Cinco de Mayo",
    "is_parents_weekend":      "Parents' Weekend",
    "is_happy_hour":           "Happy hour",
    "is_bar_special":          "Bar special",
}


def _active_factors_label(row: pd.Series) -> str:
    """Return a readable string of active signals for a single feature row."""
    parts: list[str] = []

    temp = row.get("temperature_c")
    if temp is not None and not pd.isna(temp):
        parts.append(f"{temp:.0f}°C")

    precip = row.get("precipitation_mm")
    if precip is not None and not pd.isna(precip) and precip > 0:
        parts.append(f"{precip:.1f} mm precip")

    snowfall = row.get("snowfall_mm")
    if snowfall is not None and not pd.isna(snowfall) and snowfall > 0:
        parts.append(f"{snowfall:.1f} mm snow")

    for col, label in _FACTOR_LABELS.items():
        val = row.get(col)
        if val is not None and not pd.isna(val) and int(val) == 1:
            # Annotate happy hour / bar special with how far in we are
            if col in ("is_happy_hour", "is_bar_special"):
                mins = row.get("minutes_into_special")
                if mins is not None and not pd.isna(mins) and mins > 0:
                    label = f"{label} ({int(mins)}min in)"
            parts.append(label)

    late_draw = row.get("bar_late_draw")
    if late_draw is not None and not pd.isna(late_draw) and late_draw > 0:
        parts.append(f"Late-night draw ({int(late_draw * 100)}%)")

    tv_w = row.get("tv_game_weight")
    tv_h = row.get("tv_game_hour")
    if tv_w is not None and not pd.isna(tv_w) and tv_w > 0:
        label = f"TV game {tv_w:.1f}/4.0"
        if tv_h is not None and not pd.isna(tv_h):
            label += f" @ {int(tv_h):02d}:00"
        parts.append(label)

    dub = row.get("days_until_break")
    if dub is not None and not pd.isna(dub) and 0 < dub <= 7:
        parts.append(f"{int(dub)}d until break")

    return " · ".join(parts) if parts else "No special factors"


def _make_prediction_row(
    bar_id: int,
    dt: datetime,
    weather: dict,
    signals: dict,
    overrides: dict | None = None,
) -> dict:
    """Construct a single feature row using auto-detected signals.

    Parameters
    ----------
    signals : dict returned by _get_today_signals — all non-weather flags.
    overrides : optional manual flag overrides (homecoming, bar crawl, etc.).
    """
    s = {**signals, **(overrides or {})}

    # hours_until_game: positive = before UMN game, negative = after
    game_hour = s.get("game_hour")
    hours_until_game = (
        round(game_hour - dt.hour, 1) if game_hour is not None else None
    )

    return {
        "bar_id": bar_id,
        "observed_at": dt,
        "wait_minutes": 0,
        "pct_full": 0,
        "drink_wait_minutes": 0,
        # Weather
        "temperature_c":     weather.get("temperature_c"),
        "precipitation_mm":  weather.get("precipitation_mm"),
        "wind_chill_c":      weather.get("wind_chill_c"),
        "snowfall_mm":       weather.get("snowfall_mm"),
        "wind_speed_ms":     weather.get("wind_speed_ms"),
        "is_severe_weather": int(bool(weather.get("is_severe_weather"))),
        # Athletics
        "is_game_day":         s.get("is_game_day",         0),
        "is_football_home":    s.get("is_football_home",    0),
        "is_basketball_home":  s.get("is_basketball_home",  0),
        "is_hockey_home":      s.get("is_hockey_home",      0),
        "hours_until_game":    hours_until_game,
        "is_rivalry_game":     s.get("is_rivalry_game",     0),
        "is_twins_home":       s.get("is_twins_home",       0),
        # Academic
        "classes_in_session":  s.get("classes_in_session",  0),
        "is_finals_week":      s.get("is_finals_week",      0),
        "is_welcome_week":     s.get("is_welcome_week",     0),
        "is_syllabus_week":    s.get("is_syllabus_week",    0),
        "is_midterms_week":    s.get("is_midterms_week",    0),
        "is_break":            s.get("is_break",            0),
        "is_summer_session":   s.get("is_summer_session",   0),
        "week_of_semester":    s.get("week_of_semester"),
        "days_until_break":    s.get("days_until_break"),
        # Events
        "is_holiday":            s.get("is_holiday",            0),
        "is_st_patricks":        s.get("is_st_patricks",        0),
        "is_halloween":          s.get("is_halloween",          0),
        "is_blackout_wednesday": s.get("is_blackout_wednesday", 0),
        "is_new_years_eve":      s.get("is_new_years_eve",      0),
        "is_homecoming":         s.get("is_homecoming",         0),
        "is_bar_crawl":          s.get("is_bar_crawl",          0),
        # TV sports
        "is_nfl_game_day":        s.get("is_nfl_game_day",        0),
        "is_nfl_playoffs":        s.get("is_nfl_playoffs",        0),
        "is_super_bowl":          s.get("is_super_bowl",          0),
        "is_vikings_game":        s.get("is_vikings_game",        0),
        "is_cfb_saturday":        s.get("is_cfb_saturday",        0),
        "is_cfb_championship":    s.get("is_cfb_championship",    0),
        "is_march_madness":       s.get("is_march_madness",       0),
        "is_march_madness_elite": s.get("is_march_madness_elite", 0),
        "is_nba_playoffs":        s.get("is_nba_playoffs",        0),
        "tv_game_hour":           s.get("tv_game_hour"),
        "tv_game_weight":         s.get("tv_game_weight",         0.0),
        # MN-specific pro sports
        "is_wild_game":           s.get("is_wild_game",           0),
        "is_timberwolves_game":   s.get("is_timberwolves_game",   0),
        "is_nhl_playoffs":        s.get("is_nhl_playoffs",        0),
        # Weather expanded
        "cloud_cover":            weather.get("cloud_cover"),
        "is_first_nice_day":      int(bool(weather.get("is_first_nice_day"))),
        # Academic expanded
        "is_study_days":          s.get("is_study_days",          0),
        "is_commencement":        s.get("is_commencement",        0),
        "days_since_semester_start": s.get("days_since_semester_start"),
        # Events expanded
        "is_cinco_de_mayo":       s.get("is_cinco_de_mayo",       0),
        "is_parents_weekend":     s.get("is_parents_weekend",     0),
        # Observation-level
        "cover_charge": None,
    }


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("🍺 UMN Bar Forecasting Dashboard")
st.caption("Predict line wait, how full the bar is, and how long to get a drink.")

# Initialise DB (safe to call repeatedly)
init_db()

# Load models
models = _get_models()

if "error" in models:
    st.error(f"Could not train models: {models['error']}")
    st.info("Run `python -m data.seed` in the project root, then refresh this page.")
    st.stop()

baseline_wait,  ml_wait  = models["wait"]
baseline_pct,   ml_pct   = models["pct_full"]
baseline_drink, ml_drink = models["drink"]
df_feat: pd.DataFrame    = models["df_feat"]

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    bar_names = [b["name"] for b in BARS]
    selected_bar = st.selectbox("Select bar", bar_names)

    st.subheader("Prediction time")
    pred_date = st.date_input("Date", value=datetime.now().date())
    pred_hour = st.slider("Hour (24h)", min_value=14, max_value=26, value=21, step=1)
    actual_hour = pred_hour % 24

    st.divider()
    st.subheader("Current weather")
    weather = get_weather()
    temp   = weather.get("temperature_c")
    precip = weather.get("precipitation_mm")
    if temp is not None:
        st.metric("Temperature", f"{temp:.1f} °C")
        st.metric("Precipitation", f"{precip:.1f} mm/h" if precip is not None else "—")
    else:
        st.warning("Weather unavailable (offline?)")

    st.divider()
    st.subheader("Auto-detected signals")
    today_signals = get_today_signals(pred_date)

    _SIGNAL_DISPLAY: list[tuple[str, str]] = [
        # Academic
        ("classes_in_session",   "Classes in session"),
        ("is_syllabus_week",     "Syllabus week"),
        ("is_midterms_week",     "Midterms week"),
        ("is_finals_week",       "Finals week"),
        ("is_welcome_week",      "Welcome week"),
        ("is_break",             "Break / no classes"),
        ("is_summer_session",    "Summer session"),
        # UMN Athletics (home games)
        ("is_game_day",          "Gopher home game"),
        ("is_football_home",     "↳ Football"),
        ("is_basketball_home",   "↳ Basketball"),
        ("is_hockey_home",       "↳ Hockey"),
        ("is_rivalry_game",      "↳ Rivalry game"),
        # TV sports (bar-watching)
        ("is_nfl_game_day",      "NFL on TV"),
        ("is_super_bowl",        "↳ Super Bowl"),
        ("is_nfl_playoffs",      "↳ NFL Playoffs"),
        ("is_vikings_game",      "↳ Vikings game"),
        ("is_cfb_saturday",      "CFB Saturday"),
        ("is_cfb_championship",  "CFB Bowl/Championship"),
        ("is_march_madness",     "March Madness"),
        ("is_march_madness_elite","↳ Elite 8 / Final Four"),
        ("is_nba_playoffs",      "NBA Playoffs"),
        ("is_wild_game",           "\u21b3 Wild game"),
        ("is_timberwolves_game",   "\u21b3 Timberwolves game"),
        ("is_nhl_playoffs",        "NHL Playoffs"),
        # Events / holidays
        ("is_holiday",           "Holiday"),
        ("is_blackout_wednesday","Blackout Wednesday"),
        ("is_new_years_eve",     "New Year's Eve"),
        ("is_st_patricks",       "St. Patrick's Day"),
        ("is_halloween",         "Halloween"),
        ("is_cinco_de_mayo",       "Cinco de Mayo"),
        ("is_parents_weekend",     "Parents' Weekend"),
        ("is_study_days",          "Study/reading days"),
        ("is_commencement",        "Commencement"),
        ("is_first_nice_day",      "First nice spring day"),
    ]
    active = [(lbl, today_signals.get(key, 0)) for key, lbl in _SIGNAL_DISPLAY]
    for lbl, val in active:
        icon = "🟢" if val else "⚪"
        st.caption(f"{icon} {lbl}")

    tv_w = today_signals.get("tv_game_weight", 0.0)
    tv_h = today_signals.get("tv_game_hour")
    if tv_w > 0 and tv_h is not None:
        st.caption(f"📺 Biggest game: {tv_h:02d}:00  weight={tv_w:.1f}/4.0")

    dub = today_signals.get("days_until_break")
    if dub is not None and dub > 0:
        st.caption(f"📅 {int(dub)} days until break")

    with st.expander("Manual overrides"):
        override_homecoming = st.checkbox("Homecoming weekend", value=False)
        override_bar_crawl  = st.checkbox("Bar crawl",          value=False)

# ── Main content ──────────────────────────────────────────────────────────────

bar_id = _bar_name_to_id(selected_bar, df_feat)
if bar_id is None:
    st.error(f"Bar '{selected_bar}' not found in database.")
    st.stop()

pred_dt = datetime(
    pred_date.year, pred_date.month, pred_date.day,
    actual_hour, 0, 0,
    tzinfo=timezone.utc,
)

overrides = {
    "is_homecoming": int(override_homecoming),
    "is_bar_crawl":  int(override_bar_crawl),
}

# Build feature row — all signals auto-detected
raw_row = _make_prediction_row(bar_id, pred_dt, weather, today_signals, overrides)

fb = FeatureBuilder()
df_single = fb.build(pd.DataFrame([raw_row]))

# Capacity threshold above which a line forms outside the bar
_WAIT_LINE_THRESHOLD = 90.0  # % full — err toward showing less line rather than more

# Predictions — clamp to sensible ranges
ml_wait_pred  = max(0.0, float(ml_wait.predict(df_single)[0]))
ml_pct_pred   = max(0.0, min(100.0, float(ml_pct.predict(df_single)[0])))
ml_drink_pred = max(0.0, float(ml_drink.predict(df_single)[0]))

# No line forms until the bar is at/above capacity threshold
if ml_pct_pred < _WAIT_LINE_THRESHOLD:
    ml_wait_pred = 0.0

# ── Today's notable factors ───────────────────────────────────────────────────

_NOTABLE_SIGNALS: list[tuple[str, str]] = [
    # UMN athletics
    ("is_football_home",       "Football home game"),
    ("is_basketball_home",     "Basketball home game"),
    ("is_hockey_home",         "Hockey home game"),
    ("is_rivalry_game",        "Rivalry game"),
    # TV sports
    ("is_super_bowl",          "Super Bowl"),
    ("is_nfl_playoffs",        "NFL Playoffs"),
    ("is_vikings_game",        "Vikings game"),
    ("is_cfb_championship",    "CFB Bowl/Championship"),
    ("is_march_madness_elite", "Final Four / Elite 8"),
    ("is_march_madness",       "March Madness"),
    ("is_nba_playoffs",        "NBA Playoffs"),
    ("is_wild_game",           "Wild game"),
    ("is_timberwolves_game",   "Timberwolves game"),
    ("is_nhl_playoffs",        "NHL Playoffs"),
    ("is_cfb_saturday",        "CFB Saturday"),
    ("is_nfl_game_day",        "NFL on TV"),
    # Academic
    ("is_finals_week",         "Finals week"),
    ("is_welcome_week",        "Welcome week"),
    ("is_syllabus_week",       "Syllabus week"),
    ("is_midterms_week",       "Midterms week"),
    ("is_break",               "Break / no classes"),
    # Events
    ("is_holiday",             "Holiday"),
    ("is_st_patricks",         "St. Patrick's Day"),
    ("is_halloween",           "Halloween"),
    ("is_cinco_de_mayo",       "Cinco de Mayo"),
    ("is_parents_weekend",     "Parents' Weekend"),
    ("is_commencement",        "Commencement weekend"),
    ("is_study_days",          "Study/reading days"),
    ("is_first_nice_day",      "First nice spring day"),
    ("is_homecoming",          "Homecoming weekend"),
    ("is_bar_crawl",           "Bar crawl"),
    ("is_blackout_wednesday",  "Blackout Wednesday"),
    ("is_new_years_eve",       "New Year's Eve"),
]

_all_signals = {**today_signals, **overrides}
_active_notable = [label for key, label in _NOTABLE_SIGNALS if _all_signals.get(key)]

if _active_notable:
    st.info("**Today:** " + " · ".join(_active_notable))
else:
    st.info("**Today:** No special factors — typical night")

# ── KPI row ───────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(
        "Line wait",
        f"{ml_wait_pred:.1f} min",
        help="Estimated wait to get inside",
    )
with col2:
    st.metric(
        "Bar fullness",
        f"{ml_pct_pred:.0f}%",
        help="Estimated % of capacity",
    )
with col3:
    st.metric(
        "Drink wait",
        f"{ml_drink_pred:.1f} min",
        help="Estimated wait to get a drink once inside",
    )

st.divider()

# ── Hourly forecast chart ─────────────────────────────────────────────────────

st.subheader("Tonight's forecast — all bars")

metric_choice = st.radio(
    "Metric",
    ["Line wait (min)", "Bar fullness (%)", "Drink wait (min)"],
    horizontal=True,
)

_metric_map = {
    "Line wait (min)":   (ml_wait,  "wait_minutes",       "Line wait (min)"),
    "Bar fullness (%)":  (ml_pct,   "pct_full",           "Fullness (%)"),
    "Drink wait (min)":  (ml_drink, "drink_wait_minutes", "Drink wait (min)"),
}
_model_for_chart, _col_for_chart, _y_label = _metric_map[metric_choice]

hours_tonight = list(range(14, 27))
rows = []
for b in BARS:
    bid = _bar_name_to_id(b["name"], df_feat)
    if bid is None:
        continue
    for h in hours_tonight:
        actual_h = h % 24
        dt_h = datetime(
            pred_date.year, pred_date.month, pred_date.day,
            actual_h, 0, 0, tzinfo=timezone.utc,
        )
        raw = _make_prediction_row(bid, dt_h, weather, today_signals, overrides)
        df_h = fb.build(pd.DataFrame([raw]))
        val = float(_model_for_chart.predict(df_h)[0])
        if _col_for_chart == "wait_minutes":
            pct_h = max(0.0, min(100.0, float(ml_pct.predict(df_h)[0])))
            val = max(0.0, val) if pct_h >= _WAIT_LINE_THRESHOLD else 0.0
        elif _col_for_chart == "pct_full":
            val = max(0.0, min(100.0, val))
        else:
            val = max(0.0, val)
        rows.append({
            "bar": b["name"],
            "hour": f"{h % 24:02d}:00",
            "hour_int": h,
            _col_for_chart: val,
            "factors": _active_factors_label(df_h.iloc[0]),
        })

df_tonight = pd.DataFrame(rows)

chart = (
    alt.Chart(df_tonight)
    .mark_line(point=True)
    .encode(
        x=alt.X("hour:N", title="Hour", sort=list(df_tonight["hour"].unique())),
        y=alt.Y(f"{_col_for_chart}:Q", title=_y_label, scale=alt.Scale(zero=True)),
        color=alt.Color(
            "bar:N",
            title="Bar",
            scale=alt.Scale(
                domain=["Blarney's Pub and Grill", "Sally's Saloon", "Kollege Klub"],
                range=["#1cb864", "#7A0019", "#CC8800"],
            ),
        ),
        tooltip=[
            alt.Tooltip("bar:N", title="Bar"),
            alt.Tooltip("hour:N", title="Hour"),
            alt.Tooltip(f"{_col_for_chart}:Q", format=".1f", title=_y_label),
            alt.Tooltip("factors:N", title="Active factors"),
        ],
    )
    .properties(height=350)
    .interactive()
)
st.altair_chart(chart, use_container_width=True)

st.divider()

# ── Feature importance ────────────────────────────────────────────────────────

st.subheader("Feature importance (line wait model)")

fi = ml_wait.feature_importances_
if fi is not None:
    fi_df = fi.reset_index()
    fi_df.columns = ["feature", "importance"]

    bar_chart = (
        alt.Chart(fi_df)
        .mark_bar()
        .encode(
            x=alt.X("importance:Q", title="Importance"),
            y=alt.Y("feature:N", sort="-x", title="Feature"),
            color=alt.Color("importance:Q", scale=alt.Scale(scheme="blues"), legend=None),
            tooltip=["feature", alt.Tooltip("importance:Q", format=".4f")],
        )
        .properties(height=max(200, len(fi_df) * 30))
    )
    st.altair_chart(bar_chart, use_container_width=True)
else:
    st.info("Feature importances not available.")

st.divider()

# ── Model performance ─────────────────────────────────────────────────────────

st.subheader("Model performance")

met_col1, met_col2 = st.columns(2)
with met_col1:
    st.caption("Training set")
    if ml_wait.train_metrics:
        st.metric("MAE", f"{ml_wait.train_metrics['mae']:.2f} min")
        st.metric("RMSE", f"{ml_wait.train_metrics['rmse']:.2f} min")
    else:
        st.info("No training metrics available.")

with met_col2:
    st.caption(f"Test set (last {ml_wait.test_split_days} days)")
    if ml_wait.test_metrics:
        st.metric("MAE", f"{ml_wait.test_metrics['mae']:.2f} min")
        st.metric("RMSE", f"{ml_wait.test_metrics['rmse']:.2f} min")
    else:
        st.info("Not enough test data for evaluation.")

st.divider()

# ── Historical data explorer ──────────────────────────────────────────────────

with st.expander("Historical observations (raw data)"):
    bar_hist = df_feat[df_feat["bar_id"] == bar_id].copy()
    bar_hist["observed_at"] = pd.to_datetime(bar_hist["observed_at"], format="ISO8601", utc=True).dt.tz_convert("US/Central")
    cols_to_show = [
        c for c in
        ["observed_at", "wait_minutes", "pct_full", "drink_wait_minutes",
         "hour", "day_of_week", "is_weekend"]
        if c in bar_hist.columns
    ]
    st.dataframe(
        bar_hist[cols_to_show].tail(200).reset_index(drop=True),
        width="stretch",
    )

st.divider()

# ── Log a real observation ────────────────────────────────────────────────────

st.subheader("Log a real observation")
st.caption("Submit what you observed. New data will retrain the models.")

with st.form("log_observation", clear_on_submit=True):
    f_col1, f_col2 = st.columns(2)

    with f_col1:
        f_bar    = st.selectbox("Bar", [b["name"] for b in BARS], key="f_bar")
        f_date   = st.date_input("Date observed", value=datetime.now().date(), key="f_date")
        f_hour   = st.slider(
            "Hour observed (24h)", min_value=0, max_value=23,
            value=datetime.now().hour, key="f_hour",
        )
        f_minute = st.selectbox("Minute", [0, 15, 30, 45], key="f_minute")

    with f_col2:
        f_wait = st.number_input(
            "Line wait (minutes)", min_value=0.0, max_value=180.0,
            value=10.0, step=0.5, key="f_wait",
        )
        f_pct_full = st.slider(
            "Bar fullness (%)", min_value=0, max_value=100, value=50, key="f_pct_full",
        )
        f_drink_wait = st.number_input(
            "Drink wait (minutes)", min_value=0.0, max_value=60.0,
            value=5.0, step=0.5, key="f_drink_wait",
        )
        f_cover = st.number_input(
            "Cover charge ($) — leave 0 if none",
            min_value=0.0, max_value=50.0, value=0.0, step=0.5, key="f_cover",
        )
        f_game_day = st.checkbox("Gopher game day?", key="f_game_day")
        f_holiday  = st.checkbox("Holiday?", key="f_holiday")

    f_notes = st.text_input(
        "Notes (optional)", placeholder="e.g. 'line wrapped around building'", key="f_notes",
    )

    st.caption("Weather at time of observation (auto-filled — adjust if needed)")
    w_col1, w_col2 = st.columns(2)
    with w_col1:
        f_temp = st.number_input(
            "Temperature (°C)",
            value=float(weather.get("temperature_c") or 0.0),
            step=0.5, key="f_temp",
        )
    with w_col2:
        f_precip = st.number_input(
            "Precipitation (mm/h)", min_value=0.0,
            value=float(weather.get("precipitation_mm") or 0.0),
            step=0.1, key="f_precip",
        )

    submitted = st.form_submit_button("Submit observation", type="primary", use_container_width=True)

if submitted:
    f_bar_id = next(
        (i + 1 for i, b in enumerate(BARS) if b["name"] == f_bar), None
    )
    if f_bar_id is None:
        st.error("Could not resolve bar ID — please try again.")
    else:
        obs_dt = datetime(
            f_date.year, f_date.month, f_date.day,
            f_hour, f_minute, 0, tzinfo=timezone.utc,
        )
        err = insert_observation(
            bar_id=f_bar_id,
            observed_at=obs_dt,
            wait_minutes=f_wait,
            pct_full=float(f_pct_full),
            drink_wait_minutes=f_drink_wait,
            cover_charge=f_cover if f_cover > 0 else None,
            notes=f_notes,
            temperature_c=f_temp,
            precipitation_mm=f_precip,
            is_game_day=f_game_day,
            is_holiday=f_holiday,
        )
        if err:
            st.error(f"Failed to save observation: {err}")
        else:
            st.success(
                f"Saved: {f_bar} at {obs_dt.strftime('%Y-%m-%d %H:%M UTC')}. "
                "Models will retrain on next refresh."
            )
            st.cache_resource.clear()

st.subheader("Recently logged observations")

if "obs_table_version" not in st.session_state:
    st.session_state["obs_table_version"] = 0

df_recent = recent_observations(15)
if df_recent.empty:
    st.info("No observations logged yet.")
else:
    df_recent["observed_at"] = pd.to_datetime(df_recent["observed_at"], format="ISO8601", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    df_recent["created_at"]  = pd.to_datetime(df_recent["created_at"], format="ISO8601", utc=True).dt.strftime("%Y-%m-%d %H:%M")

    df_display = df_recent.copy()
    df_display.insert(0, "edit",   False)
    df_display.insert(0, "delete", False)

    editable_cols = {"delete", "edit"}
    edited = st.data_editor(
        df_display,
        key=f"recent_obs_{st.session_state['obs_table_version']}",
        column_config={
            "delete":             st.column_config.CheckboxColumn("Delete?",         default=False, width="small"),
            "edit":               st.column_config.CheckboxColumn("Edit?",           default=False, width="small"),
            "observation_id":     None,
            "bar":                st.column_config.TextColumn("Bar"),
            "observed_at":        st.column_config.TextColumn("Observed at"),
            "wait_minutes":       st.column_config.NumberColumn("Line wait (min)",   format="%.1f"),
            "pct_full":           st.column_config.NumberColumn("Fullness (%)",      format="%.0f"),
            "drink_wait_minutes": st.column_config.NumberColumn("Drink wait (min)",  format="%.1f"),
            "cover_charge":       st.column_config.NumberColumn("Cover ($)",         format="%.2f"),
            "notes":              st.column_config.TextColumn("Notes"),
            "temperature_c":      st.column_config.NumberColumn("Temp (°C)",         format="%.1f"),
            "precipitation_mm":   st.column_config.NumberColumn("Precip (mm/h)",     format="%.2f"),
            "is_game_day":        st.column_config.CheckboxColumn("Game day",  disabled=True),
            "is_holiday":         st.column_config.CheckboxColumn("Holiday",   disabled=True),
            "created_at":         st.column_config.TextColumn("Logged at"),
        },
        disabled=[c for c in df_display.columns if c not in editable_cols],
        hide_index=True,
        width="stretch",
    )

    to_delete = edited.loc[edited["delete"], "observation_id"].tolist()
    to_edit   = edited.loc[edited["edit"],   "observation_id"].tolist()

    action_col1, action_col2 = st.columns(2)

    with action_col1:
        if st.button(
            f"Delete {len(to_delete)} selected" if to_delete else "Delete selected",
            type="primary",
            disabled=not to_delete,
            use_container_width=True,
        ):
            st.session_state["pending_delete"] = to_delete

    with action_col2:
        if len(to_edit) > 1:
            st.warning("Check only one row to edit.")
        edit_btn = st.button(
            "Edit selected",
            disabled=len(to_edit) != 1,
            use_container_width=True,
        )
        if edit_btn:
            st.session_state["editing_obs_id"] = to_edit[0]
            st.session_state.pop("pending_delete", None)

    if st.session_state.get("pending_delete"):
        pending = st.session_state["pending_delete"]
        with st.container(border=True):
            st.warning(
                f"Delete **{len(pending)} observation(s)**? This cannot be undone.",
                icon="⚠️",
            )
            confirm_col, cancel_col = st.columns([1, 1])
            with confirm_col:
                if st.button("Yes, delete", type="primary", use_container_width=True):
                    err = delete_observations(pending)
                    if err:
                        st.error(f"Delete failed: {err}")
                    else:
                        st.session_state.pop("pending_delete", None)
                        st.session_state["obs_table_version"] += 1
                        st.cache_resource.clear()
                        st.rerun()
            with cancel_col:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.pop("pending_delete", None)
                    st.rerun()

# ── Edit form ─────────────────────────────────────────────────────────────────

editing_id = st.session_state.get("editing_obs_id")
if editing_id:
    obs = fetch_observation(editing_id)
    if obs is None:
        st.error(f"Observation {editing_id} not found.")
        st.session_state.pop("editing_obs_id", None)
    else:
        st.divider()
        with st.container(border=True):
            st.subheader(f"Edit observation — {obs['bar_name']}")

            obs_dt = datetime.fromisoformat(obs["observed_at"]).replace(tzinfo=timezone.utc)

            with st.form("edit_observation", clear_on_submit=False):
                ef_col1, ef_col2 = st.columns(2)

                with ef_col1:
                    ef_bar = st.selectbox(
                        "Bar",
                        [b["name"] for b in BARS],
                        index=next(
                            (i for i, b in enumerate(BARS) if b["name"] == obs["bar_name"]), 0
                        ),
                        key="ef_bar",
                    )
                    ef_date   = st.date_input("Date observed", value=obs_dt.date(), key="ef_date")
                    ef_hour   = st.slider(
                        "Hour observed (24h)", min_value=0, max_value=23,
                        value=obs_dt.hour, key="ef_hour",
                    )
                    ef_minute = st.selectbox(
                        "Minute",
                        [0, 15, 30, 45],
                        index=[0, 15, 30, 45].index(
                            min([0, 15, 30, 45], key=lambda m: abs(m - obs_dt.minute))
                        ),
                        key="ef_minute",
                    )

                with ef_col2:
                    ef_wait = st.number_input(
                        "Line wait (minutes)", min_value=0.0, max_value=180.0,
                        value=float(obs["wait_minutes"]), step=0.5, key="ef_wait",
                    )
                    ef_pct_full = st.slider(
                        "Bar fullness (%)", min_value=0, max_value=100,
                        value=int(obs["pct_full"] or 50), key="ef_pct_full",
                    )
                    ef_drink_wait = st.number_input(
                        "Drink wait (minutes)", min_value=0.0, max_value=60.0,
                        value=float(obs["drink_wait_minutes"] or 5.0), step=0.5, key="ef_drink_wait",
                    )
                    ef_cover = st.number_input(
                        "Cover charge ($) — leave 0 if none",
                        min_value=0.0, max_value=50.0,
                        value=float(obs["cover_charge"] or 0.0), step=0.5, key="ef_cover",
                    )
                    ef_game_day = st.checkbox("Gopher game day?", value=bool(obs["is_game_day"]), key="ef_game_day")
                    ef_holiday  = st.checkbox("Holiday?",         value=bool(obs["is_holiday"]),  key="ef_holiday")

                ef_notes = st.text_input(
                    "Notes (optional)", value=obs["notes"] or "", key="ef_notes",
                )

                st.caption("Weather")
                ew_col1, ew_col2 = st.columns(2)
                with ew_col1:
                    ef_temp = st.number_input(
                        "Temperature (°C)",
                        value=float(obs["temperature_c"] or 0.0), step=0.5, key="ef_temp",
                    )
                with ew_col2:
                    ef_precip = st.number_input(
                        "Precipitation (mm/h)", min_value=0.0,
                        value=float(obs["precipitation_mm"] or 0.0), step=0.1, key="ef_precip",
                    )

                save_col, cancel_col2 = st.columns(2)
                with save_col:
                    ef_submitted = st.form_submit_button(
                        "Save changes", type="primary", use_container_width=True,
                    )
                with cancel_col2:
                    ef_cancelled = st.form_submit_button("Cancel", use_container_width=True)

            if ef_submitted:
                ef_bar_id = next(
                    (i + 1 for i, b in enumerate(BARS) if b["name"] == ef_bar), None
                )
                if ef_bar_id is None:
                    st.error("Could not resolve bar ID.")
                else:
                    updated_dt = datetime(
                        ef_date.year, ef_date.month, ef_date.day,
                        ef_hour, ef_minute, 0, tzinfo=timezone.utc,
                    )
                    err = update_observation(
                        obs_id=editing_id,
                        bar_id=ef_bar_id,
                        observed_at=updated_dt,
                        wait_minutes=ef_wait,
                        pct_full=float(ef_pct_full),
                        drink_wait_minutes=ef_drink_wait,
                        cover_charge=ef_cover if ef_cover > 0 else None,
                        notes=ef_notes,
                        temperature_c=ef_temp,
                        precipitation_mm=ef_precip,
                        is_game_day=ef_game_day,
                        is_holiday=ef_holiday,
                    )
                    if err:
                        st.error(f"Update failed: {err}")
                    else:
                        st.success("Observation updated.")
                        st.session_state.pop("editing_obs_id", None)
                        st.session_state["obs_table_version"] += 1
                        st.cache_resource.clear()
                        st.rerun()

            if ef_cancelled:
                st.session_state.pop("editing_obs_id", None)
                st.rerun()

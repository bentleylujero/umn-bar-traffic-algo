"""Data Pipeline Visualization Page — Shows inputs and factors.

Run with:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st
import altair as alt

from config.settings import BARS, BAR_SCHEDULES
from data.db import get_connection
from features.builder import FeatureBuilder, SIGNAL_FEATURES
from app.utils import get_weather, get_today_signals

st.set_page_config(
    page_title="Algorithm Pipeline | UMN Bar Forecast",
    page_icon="🧬",
    layout="wide",
)

st.title("🧬 Algorithm Data Pipeline")
st.markdown("""
This page visualizes the "Digital Nervous System" of the UMN Bar Traffic algorithm. 
It shows how raw data from external APIs and internal schedules are transformed into the features 
that drive our predictions.
""")

# ── Global Factors (Affecting All Bars) ───────────────────────────────────────

st.header("🌎 Global Factors")
st.caption("These environmental and cultural signals affect the entire campus ecosystem simultaneously.")

col1, col2, col3 = st.columns(3)

# 1. Weather
with col1:
    st.subheader("☁️ Physical Environment")
    weather = get_weather()
    if weather:
        st.metric("Temperature", f"{weather.get('temperature_c', 0):.1f} °C")
        st.metric("Precipitation", f"{weather.get('precipitation_mm', 0):.1f} mm/h")
        if weather.get("is_severe_weather"):
            st.warning("⚠️ Severe Weather Active")
        if weather.get("is_first_nice_day"):
            st.info("☀️ First Nice Day Effect")
    else:
        st.error("Weather data unavailable")

# 2. Sports
with col2:
    now = datetime.now(timezone.utc)
    today = now.date()
    signals = get_today_signals(today)
    
    # Sports (part of signals now)
    st.subheader("🏀 Athletics & TV")
    if signals.get("is_game_day"):
        st.success(f"🏟️ Gopher Home Game (Hr: {signals.get('game_hour')})")
        if signals.get("is_rivalry_game"):
            st.warning("🔥 Rivalry Game Intensity")
    else:
        st.info("No Gopher Home Games Today")
        
    tv_weight = signals.get("tv_game_weight", 0.0)
    st.metric("TV Sports Weight", f"{tv_weight:.1f}/4.0")
    if tv_weight > 2.0:
        st.caption("📺 High-draw TV event detected")

# 3. Calendar
with col3:
    st.subheader("📅 Academic Rhythm")
    
    if signals.get("classes_in_session"):
        st.info("📚 Classes in Session")
    else:
        st.warning("⛱️ Campus Break")
        
    if signals.get("is_finals_week"):
        st.error("📑 Finals Week — High Stress/Library Draw")
    elif signals.get("is_syllabus_week"):
        st.success("🎉 Syllabus Week — Peak Party Volume")
        
    st.metric("Days Since Semester Start", signals.get("days_since_semester_start", 0))

st.divider()

# ── Bar-Specific Factors ──────────────────────────────────────────────────────

st.header("📍 Bar-Specific Factors")
st.caption("Unique signals that attract crowds to one location while others might be empty.")

selected_bar_name = st.selectbox("Select a bar to inspect", [b["name"] for b in BARS])
bar_id = next(i+1 for i, b in enumerate(BARS) if b["name"] == selected_bar_name)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("🕒 Weekly Deals & Schedules")
    sched = BAR_SCHEDULES.get(bar_id, {})
    
    # Happy Hour
    hh = sched.get("happy_hour")
    if hh:
        st.write(f"**Happy Hour:** {hh['start'][0]}:{hh['start'][1]:02d} — {hh['end'][0]}:{hh['end'][1]:02d}")
    else:
        st.write("*No daily happy hour configured*")
        
    # Specials
    specials = sched.get("weekly_specials", [])
    if specials:
        st.write("**Weekly Specials:**")
        for s in specials:
            days = s.get("days", [s.get("day")])
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            d_str = ", ".join([day_names[d] for d in days])
            st.caption(f"• **{s['name']}** ({d_str}) — {s['traffic_boost']*100:+.0f}% predicted lift")
    else:
        st.write("*No weekly specials configured*")

with col_b:
    st.subheader("📡 Live Crowd Intelligence")
    
    # Fetch recent crowd reports
    conn = get_connection()
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(timespec="seconds")
    recent = conn.execute(
        "SELECT * FROM observations WHERE bar_id = ? AND observed_at >= ? ORDER BY observed_at DESC",
        (bar_id, one_hour_ago)
    ).fetchall()
    conn.close()
    
    if recent:
        latest = recent[0]
        st.success(f"✅ Recent report found ({latest['observed_at']})")
        st.metric("Live Wait Time", f"{latest['wait_minutes']} min")
        st.metric("Reported Fullness", f"{latest['pct_full']:.0f}%" if latest['pct_full'] is not None else "—")
    else:
        st.info("No crowd reports in the last hour")
        st.caption("Algorithm is relying on historical baselines and environmental signals.")

st.divider()

# ── Feature Vector Transformation ─────────────────────────────────────────────

st.header("⚙️ Feature Transformation")
st.caption("How the algorithm 'sees' the world right now.")

# Construct the current feature row
fb = FeatureBuilder()
row = {
    "observed_at": now,
    "bar_id": bar_id,
    "wait_minutes": 0, # placeholder
    **weather,
    **signals,
}
# Add recent crowd reports if any
if recent:
    row["live_wait_minutes"] = recent[0]["wait_minutes"]
    row["live_pct_full"] = recent[0]["pct_full"] or 0.0

df_raw = pd.DataFrame([row])
df_feat = fb.build(df_raw)
feature_cols = fb.feature_columns(df_feat)

# Create a displayable DF of features
feat_display = df_feat[feature_cols].iloc[0].to_dict()
feat_df = pd.DataFrame([
    {"Feature": k, "Value": f"{v:.4f}" if isinstance(v, float) else v}
    for k, v in feat_display.items()
])

st.dataframe(feat_df, use_container_width=True, height=400)

st.info("""
**Note on Model Scope:**
- **Global Features** (e.g. `temperature_c`, `is_game_day`) are shared across all model predictions.
- **Local Features** (e.g. `is_bar_special`, `live_wait_minutes`) only toggle 'ON' for specific bar predictions. 
- The **RandomForest** model learns the complex interactions between these signals (e.g., how a 'Gopher Game' + 'Salary Happy Hour' creates a massive crowd surge).
""")

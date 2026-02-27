"""Live Logger Page — Optimized for rapid data entry.

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

from datetime import datetime, timezone
import streamlit as st
import pandas as pd

from config.settings import BARS
from app.utils import get_weather, get_today_signals, insert_observation, recent_observations

st.set_page_config(
    page_title="Live Logger | UMN Bar Forecast",
    page_icon="📡",
    layout="centered",
)

st.title("📡 Live Logger")
st.markdown("""
Use this page to **actively log** crowd levels. 
This data directly trains the algorithm to improve accuracy.
""")

# ── Sidebar Settings ──────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")
    selected_bar_name = st.selectbox("Select Bar", [b["name"] for b in BARS])
    bar_id = next(i+1 for i, b in enumerate(BARS) if b["name"] == selected_bar_name)
    
    st.info(f"Targeting: **{selected_bar_name}**")
    
    if st.button("🔄 Refresh Data"):
        st.cache_resource.clear()
        st.cache_data.clear()
        st.rerun()

# ── Quick Log Presets ─────────────────────────────────────────────────────────

st.header("⚡ Quick Log")
st.caption("One-tap buttons for common situations. Submits current time and weather.")

col1, col2 = st.columns(2)
col3, col4 = st.columns(2)

presets = [
    {"label": "Empty / Dead", "icon": "👻", "wait": 0.0, "full": 5, "drink": 1.0, "color": "secondary"},
    {"label": "Chilled / Low", "icon": "🧊", "wait": 0.0, "full": 25, "drink": 3.0, "color": "secondary"},
    {"label": "Busy / Good", "icon": "🔥", "wait": 10.0, "full": 75, "drink": 8.0, "color": "primary"},
    {"label": "Packed / No Entry", "icon": "🚀", "wait": 35.0, "full": 100, "drink": 15.0, "color": "primary"},
]

weather = get_weather()
signals = get_today_signals(datetime.now().date())

def handle_preset(p):
    now = datetime.now(timezone.utc)
    err = insert_observation(
        bar_id=bar_id,
        observed_at=now,
        wait_minutes=p["wait"],
        pct_full=p["full"],
        drink_wait_minutes=p["drink"],
        cover_charge=None,
        notes=f"Quick log: {p['label']}",
        temperature_c=weather.get("temperature_c"),
        precipitation_mm=weather.get("precipitation_mm"),
        is_game_day=signals.get("is_game_day", 0),
        is_holiday=signals.get("is_holiday", 0),
    )
    if err:
        st.error(f"Failed to log: {err}")
    else:
        st.success(f"Logged **{p['label']}** for {selected_bar_name}!")
        st.balloons()
        st.cache_resource.clear()

with col1:
    if st.button(f"{presets[0]['icon']} {presets[0]['label']}", use_container_width=True):
        handle_preset(presets[0])

with col2:
    if st.button(f"{presets[1]['icon']} {presets[1]['label']}", use_container_width=True):
        handle_preset(presets[1])

with col3:
    if st.button(f"{presets[2]['icon']} {presets[2]['label']}", use_container_width=True):
        handle_preset(presets[2])

with col4:
    if st.button(f"{presets[3]['icon']} {presets[3]['label']}", use_container_width=True):
        handle_preset(presets[3])

st.divider()

# ── Detailed Entry ───────────────────────────────────────────────────────────

st.header("📝 Custom Entry")

with st.form("custom_log", clear_on_submit=True):
    f_col1, f_col2 = st.columns(2)
    
    with f_col1:
        f_wait = st.number_input("Line Wait (min)", min_value=0.0, value=5.0, step=1.0)
        f_pct = st.slider("Fullness (%)", 0, 100, 50)
        
    with f_col2:
        f_drink = st.number_input("Drink Wait (min)", min_value=0.0, value=5.0, step=1.0)
        f_cover = st.number_input("Cover Charge ($)", min_value=0.0, value=0.0, step=1.0)

    f_notes = st.text_input("Notes", placeholder="e.g., 'Band is playing', 'ID check is slow'")
    
    submitted = st.form_submit_button("Submit Detailed Log", type="primary", use_container_width=True)
    
    if submitted:
        now = datetime.now(timezone.utc)
        err = insert_observation(
            bar_id=bar_id,
            observed_at=now,
            wait_minutes=f_wait,
            pct_full=f_pct,
            drink_wait_minutes=f_drink,
            cover_charge=f_cover if f_cover > 0 else None,
            notes=f_notes,
            temperature_c=weather.get("temperature_c"),
            precipitation_mm=weather.get("precipitation_mm"),
            is_game_day=signals.get("is_game_day", 0),
            is_holiday=signals.get("is_holiday", 0),
        )
        if err:
            st.error(f"Failed to log: {err}")
        else:
            st.success(f"Log submitted for {selected_bar_name}!")
            st.cache_resource.clear()

st.divider()

# ── Recent Activity ──────────────────────────────────────────────────────────

st.header("🕒 Your Recent Submissions")
st.caption("Showing the last 10 entries across all bars.")

df_recent = recent_observations(10)
if not df_recent.empty:
    df_recent["observed_at"] = pd.to_datetime(df_recent["observed_at"]).dt.strftime("%H:%M")
    st.dataframe(
        df_recent[["bar", "observed_at", "wait_minutes", "pct_full", "notes"]],
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No logs found.")

st.info("""
**Training Tip:** Logging data during peak transitions (e.g., right when a game ends or when happy hour starts) is the most valuable for model accuracy.
""")

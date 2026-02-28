"""Data Pipeline Visualization Page — Factor-aware algorithm mirror.

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
import numpy as np
import streamlit as st
import altair as alt

from config.settings import BARS, BAR_SCHEDULES
from config.tuning import (
    DRINKING_HOLIDAY_WEIGHTS,
    TRAFFIC_BOOSTS,
)
from data.db import get_connection
from features.builder import FeatureBuilder, SIGNAL_FEATURES
from app.utils import get_weather, get_today_signals

st.set_page_config(
    page_title="Algorithm Pipeline | UMN Bar Forecast",
    page_icon="🧬",
    layout="wide",
)

# ── Custom CSS for polished appearance ─────────────────────────────────────────

st.markdown("""
<style>
.factor-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.badge-boost {
    background: #1a4a1a;
    color: #44dd44;
    border: 1px solid #228822;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.78em;
    font-weight: bold;
}
.badge-suppress {
    background: #4a1a1a;
    color: #ff6666;
    border: 1px solid #882222;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.78em;
    font-weight: bold;
}
.badge-neutral {
    background: #2a2a2a;
    color: #aaaaaa;
    border: 1px solid #444444;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.78em;
}
.score-big {
    font-size: 2.2em;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

st.title("🧬 Algorithm Data Pipeline")
st.markdown("""
This page is a **live mirror** of the UMN Bar Traffic algorithm.  
Every number shown here is computed from the **exact same weights and logic** as the RandomForest prediction model.
""")

# ── Time & bar selection controls ──────────────────────────────────────────────

ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 1])
with ctrl_col1:
    selected_bar_name = st.selectbox("Inspect bar", [b["name"] for b in BARS])
with ctrl_col2:
    inspect_date = st.date_input("Date", value=datetime.now().date())
with ctrl_col3:
    inspect_hour = st.slider("Hour (24h)", min_value=14, max_value=26, value=21, step=1)

bar_id = next(i + 1 for i, b in enumerate(BARS) if b["name"] == selected_bar_name)
actual_hour = inspect_hour % 24
inspect_dt = datetime(
    inspect_date.year, inspect_date.month, inspect_date.day,
    actual_hour, 0, 0, tzinfo=timezone.utc
)

# ── Data loading ───────────────────────────────────────────────────────────────

weather  = get_weather()
signals  = get_today_signals(inspect_date)

# Live crowd reports
conn = get_connection()
one_hour_ago = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat(timespec="seconds")
recent = conn.execute(
    "SELECT * FROM observations WHERE bar_id = ? AND observed_at >= ? ORDER BY observed_at DESC",
    (bar_id, one_hour_ago),
).fetchall()
conn.close()

# Build the feature row via FeatureBuilder (same as prediction code path)
fb = FeatureBuilder()
raw_row = {
    "observed_at": inspect_dt,
    "bar_id":      bar_id,
    "wait_minutes": 0,
    "pct_full":     0,
    "drink_wait_minutes": 0,
    # Weather
    "temperature_c":     weather.get("temperature_c"),
    "precipitation_mm":  weather.get("precipitation_mm"),
    "wind_chill_c":      weather.get("wind_chill_c"),
    "snowfall_mm":       weather.get("snowfall_mm"),
    "wind_speed_ms":     weather.get("wind_speed_ms"),
    "is_severe_weather": int(bool(weather.get("is_severe_weather"))),
    "cloud_cover":       weather.get("cloud_cover"),
    "is_first_nice_day": int(bool(weather.get("is_first_nice_day"))),
}
# Merge all signals
for k, v in signals.items():
    raw_row[k] = v

if recent:
    raw_row["live_wait_minutes"] = recent[0]["wait_minutes"]
    raw_row["live_pct_full"]     = recent[0]["pct_full"] or 0.0

df_raw  = pd.DataFrame([raw_row])
df_feat = fb.build(df_raw)
feat    = df_feat.iloc[0]

sched = BAR_SCHEDULES.get(bar_id, {})

# ── Helper: signed impact mapping ─────────────────────────────────────────────
# Each entry: (label, raw_value, direction, computed_weight, explanation)

def _get_factor_impacts(feat: pd.Series, sched: dict) -> list[dict]:
    """Return a list of factor-impact dicts for the current feature row."""
    impacts = []

    def _add(label: str, direction: str, weight: float, detail: str = ""):
        impacts.append({
            "label":  label,
            "dir":    direction,   # "boost" | "suppress" | "neutral"
            "weight": weight,
            "detail": detail,
        })

    # ── Time of day / week ─────────────────────────────────────────────────
    if feat.get("is_weekend", 0):
        _add("Weekend (Fri–Sun)", "boost", 1.5, "Fri–Sun multiplies bar turnout")
    elif feat.get("is_thursday", 0):
        _add("Thursday night", "boost", 0.8, "canonical college bar night")

    if feat.get("is_late_night", 0):
        _add("Late night (12–2 AM)", "boost", 0.6, "crowd peaks after midnight")

    # ── Academic calendar ──────────────────────────────────────────────────
    if feat.get("is_syllabus_week", 0):
        _add("Syllabus week", "boost", 1.2, "first week of semester — peak social energy")
    if feat.get("is_welcome_week", 0):
        _add("Welcome week", "boost", 1.0, "orientation / move-in — big party week")
    if feat.get("is_midterms_week", 0):
        _add("Midterms week", "suppress", 0.7, "exam stress decreases bar traffic")
    if feat.get("classes_in_session", 0):
        _add("Classes in session", "suppress", 0.5, "weeknight baseline suppressor")
    if feat.get("is_finals_week", 0):
        _add("Finals week", "suppress", 1.5, "library draws instead of bars")
    if feat.get("is_study_days", 0):
        _add("Study/reading days", "suppress", 0.8, "pre-finals quiet period")
    if feat.get("is_break", 0):
        _add("Campus break / no classes", "suppress", 2.0, "students leave campus — bars empty")
    if feat.get("is_summer_session", 0):
        _add("Summer session", "suppress", 1.0, "reduced campus population")
    if feat.get("is_commencement", 0):
        dw = DRINKING_HOLIDAY_WEIGHTS.get("is_commencement", 2.5)
        _add("Commencement weekend", "boost", dw, f"holiday weight = {dw}")
    if feat.get("is_parents_weekend", 0):
        dw = DRINKING_HOLIDAY_WEIGHTS.get("is_parents_weekend", 1.5)
        _add("Parents' Weekend", "boost", dw, f"holiday weight = {dw}")

    dub = feat.get("days_until_break")
    if dub is not None and not pd.isna(dub) and 0 < dub <= 7:
        boost = max(0.0, round((7 - float(dub)) / 7 * 0.8, 2))
        _add(f"Pre-break excitement ({int(dub)}d until break)", "boost", boost,
             "traffic ticks up as break approaches")

    # ── Drinking holidays ──────────────────────────────────────────────────
    for hol_col, w in DRINKING_HOLIDAY_WEIGHTS.items():
        if feat.get(hol_col, 0):
            labels_map = {
                "is_st_patricks":        "St. Patrick's Day",
                "is_new_years_eve":      "New Year's Eve",
                "is_halloween":          "Halloween",
                "is_bar_crawl":          "Bar crawl",
                "is_blackout_wednesday": "Blackout Wednesday",
                "is_homecoming":         "Homecoming weekend",
                "is_cinco_de_mayo":      "Cinco de Mayo",
                "is_commencement":       "Commencement",
                "is_parents_weekend":    "Parents' Weekend",
            }
            lbl = labels_map.get(hol_col, hol_col)
            _add(lbl, "boost", w, f"DRINKING_HOLIDAY_WEIGHTS = {w}")

    # ── UMN athletics ──────────────────────────────────────────────────────
    if feat.get("is_game_day", 0):
        base = 2.0
        if feat.get("is_football_home", 0):
            base = 2.5
            _add("Football home game", "boost", base, "biggest UMN attendance event")
        elif feat.get("is_basketball_home", 0):
            _add("Basketball home game", "boost", 2.0, "large student section attendance")
        elif feat.get("is_hockey_home", 0):
            _add("Hockey home game", "boost", 1.8, "strong student fanbase")
        else:
            _add("Gopher home game", "boost", base, "UMN home game day")

        if feat.get("is_rivalry_game", 0):
            _add("Rivalry game (additive)", "boost", 1.0, "extra intensity on top of game day")

        hug = feat.get("hours_until_game")
        if hug is not None and not pd.isna(hug):
            if 0 < float(hug) <= 2:
                _add("Pre-game window (≤2h before)", "boost", 0.5, "crowd building before tipoff/kickoff")
            elif float(hug) < 0:
                _add("Post-game surge", "boost", 0.8, "win/loss empties into bars")

    # ── TV sports ──────────────────────────────────────────────────────────
    tv_w = feat.get("tv_game_weight", 0.0)
    if tv_w and not pd.isna(tv_w) and float(tv_w) > 0:
        tv_h = feat.get("tv_game_hour")
        tv_label = f"TV sports (weight {float(tv_w):.1f}/4.0)"
        if tv_h is not None and not pd.isna(tv_h):
            tv_label += f" @ {int(tv_h):02d}:00"
        if feat.get("is_super_bowl", 0):
            _add("Super Bowl", "boost", float(tv_w), "biggest TV sports event; bars pack out")
        elif feat.get("is_march_madness_elite", 0):
            _add("March Madness Elite 8 / Final Four", "boost", float(tv_w), "high-drama viewing event")
        elif feat.get("is_cfb_championship", 0):
            _add("CFB Bowl / Championship", "boost", float(tv_w), "major bowl game watch parties")
        else:
            _add(tv_label, "boost", float(tv_w), "bar TV-watching draw")

    # MN pro sports (Sally's has Wild / T-Wolves specials)
    if feat.get("is_wild_game", 0):
        _add("Wild game", "boost", 0.5, "MN hockey draw at Sally's")
    if feat.get("is_timberwolves_game", 0):
        _add("Timberwolves game", "boost", 0.4, "NBA watch crowd")
    if feat.get("is_nhl_playoffs", 0):
        _add("NHL Playoffs", "boost", 0.7, "playoff hockey intensity")
    if feat.get("is_nba_playoffs", 0):
        _add("NBA Playoffs", "boost", 0.6, "playoff watch parties")

    # ── Weather ────────────────────────────────────────────────────────────
    temp = feat.get("temperature_c")
    if temp is not None and not pd.isna(temp):
        t = float(temp)
        if t < 0:
            penalty = round(min(2.0, abs(t) / 5.0 * 0.5), 2)
            _add(f"Cold weather ({t:.0f}°C)", "suppress", penalty,
                 "–0.5 per 5°C below freezing; people stay home")
        elif t > 22:
            _add(f"Warm weather ({t:.0f}°C)", "boost", 0.3, "nice weather draws people out")

    if feat.get("is_first_nice_day", 0):
        _add("First nice spring day", "boost", 1.0, "pent-up cabin-fever; bars and patios fill")

    precip = feat.get("precipitation_mm")
    if precip is not None and not pd.isna(precip) and float(precip) > 2:
        penalty = round(min(1.5, float(precip) / 10.0 * 1.5), 2)
        _add(f"Precipitation ({float(precip):.1f} mm/h)", "suppress", penalty,
             "rain discourages walking to bars")

    snow = feat.get("snowfall_mm")
    if snow is not None and not pd.isna(snow) and float(snow) > 5:
        _add(f"Snowfall ({float(snow):.1f} mm)", "suppress", 1.0,
             "heavy snow keeps students inside")

    if feat.get("is_severe_weather", 0):
        _add("Severe weather warning", "suppress", 2.0, "people stay home; safety concern")

    # ── Bar-specific schedule ──────────────────────────────────────────────
    if feat.get("is_happy_hour", 0):
        mins = feat.get("minutes_into_special", 0)
        _add(f"Happy hour ({int(mins)} min in)", "boost", 0.4,
             "price promotion increases early traffic")

    if feat.get("is_bar_special", 0):
        # Find which special is active
        for sp in sched.get("weekly_specials", []):
            boost_key = None
            for k in TRAFFIC_BOOSTS:
                if sp.get("name", "").lower().replace(" ", "_").replace("'", "") in k or \
                   k in sp.get("name", "").lower().replace(" ", "_").replace("'", ""):
                    boost_key = k
                    break
            if boost_key is None:
                # Try a partial match
                sp_name_lower = sp.get("name", "").lower()
                for k in TRAFFIC_BOOSTS:
                    if any(word in k for word in sp_name_lower.split() if len(word) > 3):
                        boost_key = k
                        break
            bv = TRAFFIC_BOOSTS.get(boost_key, sp.get("traffic_boost", 0.0)) if boost_key else sp.get("traffic_boost", 0.0)
            mins = int(feat.get("minutes_into_special", 0))
            _add(f"{sp['name']} ({mins} min in)", "boost", float(bv),
                 f"TRAFFIC_BOOSTS = {bv:.2f} (+{bv * 100:.0f}% over baseline)")

    # ── Late-night draw ────────────────────────────────────────────────────
    ld = feat.get("bar_late_draw", 0.0)
    if ld and not pd.isna(ld) and float(ld) > 0:
        _add(f"Late-night migration draw ({float(ld) * 100:.0f}%)", "boost", float(ld),
             "drunk crowds migrate here after cheaper bars thin out; 0 at 10 PM → 1.0 at 2 AM")

    # ── Greek life ─────────────────────────────────────────────────────────
    gsi = feat.get("greek_social_intensity", 0.0)
    if gsi and not pd.isna(gsi) and float(gsi) > 0:
        _add(f"Greek social intensity ({float(gsi):.2f})", "boost", float(gsi),
             "composite signal: rush, bid day, formals, Greek Thu")
    if feat.get("is_greek_bid_day", 0):
        _add("Greek bid day ±1d", "boost", 0.9, "single biggest Greek bar night")
    if feat.get("is_greek_rush_week", 0):
        _add("Greek rush week", "suppress", 0.5, "IFC/PHC recruitment suppresses general bar traffic")
    if feat.get("is_greek_thursday", 0) and not feat.get("is_bar_special", 0):
        _add("Greek Thursday", "boost", 0.4, "canonical Greek bar night — pre-pregame surge")
    if feat.get("is_greek_pregame_window", 0):
        _add("Greek pregame window (7–10 PM)", "boost", 0.3, "pre-event bar surge before house parties")

    return impacts


impacts = _get_factor_impacts(feat, sched)
boost_impacts    = [i for i in impacts if i["dir"] == "boost"]
suppress_impacts = [i for i in impacts if i["dir"] == "suppress"]

total_boost    = sum(i["weight"] for i in boost_impacts)
total_suppress = sum(i["weight"] for i in suppress_impacts)
net_score      = total_boost - total_suppress

# ── Section 1: Summary ─────────────────────────────────────────────────────────

st.divider()

s_col1, s_col2, s_col3 = st.columns(3)
with s_col1:
    st.metric(
        "⬆ Total Boost Score",
        f"{total_boost:.2f}",
        help="Sum of all positive factor weights for this bar/time",
    )
with s_col2:
    st.metric(
        "⬇ Total Suppress Score",
        f"−{total_suppress:.2f}",
        help="Sum of all negative factor weights for this bar/time",
    )
with s_col3:
    net_delta = f"+{net_score:.2f}" if net_score > 0 else f"{net_score:.2f}"
    st.metric(
        "⚡ Net Traffic Score",
        net_delta,
        help="Net signed sum — positive = above-average night expected",
    )

# Composite algorithm signals (from FeatureBuilder)
comp_col1, comp_col2, comp_col3 = st.columns(3)
with comp_col1:
    dhw = float(feat.get("drinking_holiday_weight", 0.0) or 0.0)
    st.metric(
        "🎉 Drinking Holiday Weight",
        f"{dhw:.2f}",
        help="Exact value from FeatureBuilder._add_drinking_holiday_weight — same as what the model sees",
    )
    if dhw > 0:
        max_dhw = max(DRINKING_HOLIDAY_WEIGHTS.values())
        st.progress(min(1.0, dhw / max_dhw), text=f"{dhw:.1f} / {max_dhw:.1f} (max)")
with comp_col2:
    gsi = float(feat.get("greek_social_intensity", 0.0) or 0.0)
    st.metric(
        "🏛️ Greek Social Intensity",
        f"{gsi:.2f}",
        help="0–1 composite from Greek signals (rush, bid day, formals, Greek Thu)",
    )
    st.progress(min(1.0, gsi))
with comp_col3:
    tvw = float(feat.get("tv_game_weight", 0.0) or 0.0)
    st.metric(
        "📺 TV Game Weight",
        f"{tvw:.1f} / 4.0",
        help="Weighted TV sports draw (Super Bowl = 4.0, regular game ≈ 1–2)",
    )
    st.progress(min(1.0, tvw / 4.0))

# ── Section 2: Factor Waterfall Chart ─────────────────────────────────────────

st.divider()
st.subheader("📊 Factor Waterfall — How This Night Is Built")
st.caption(
    "Every active factor is shown with its signed impact. "
    "Green bars are boosts; red bars are suppressors. "
    "These weights feed directly into the feature vector that the RandomForest model uses."
)

if impacts:
    waterfall_rows = []
    for imp in impacts:
        sign = 1.0 if imp["dir"] == "boost" else -1.0
        waterfall_rows.append({
            "Factor":  imp["label"],
            "Impact":  round(sign * imp["weight"], 4),
            "Weight":  imp["weight"],
            "Direction": "Boost ⬆" if imp["dir"] == "boost" else "Suppress ⬇",
            "Detail":  imp["detail"],
        })

    wf_df = pd.DataFrame(waterfall_rows).sort_values("Impact", ascending=False)

    wf_chart = (
        alt.Chart(wf_df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                  cornerRadiusBottomLeft=4, cornerRadiusBottomRight=4)
        .encode(
            y=alt.Y("Factor:N", sort="-x", title=None),
            x=alt.X("Impact:Q", title="Signed Impact", scale=alt.Scale(domainMin=-3.0)),
            color=alt.condition(
                alt.datum.Impact > 0,
                alt.value("#22cc66"),
                alt.value("#cc3333"),
            ),
            tooltip=[
                alt.Tooltip("Factor:N",    title="Factor"),
                alt.Tooltip("Direction:N", title="Direction"),
                alt.Tooltip("Weight:Q",    title="Weight", format=".3f"),
                alt.Tooltip("Detail:N",    title="Why"),
            ],
        )
        .properties(height=max(200, len(wf_df) * 30))
    )

    zero_rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#666", strokeDash=[4, 4]).encode(x="x:Q")
    st.altair_chart((wf_chart + zero_rule).interactive(), use_container_width=True)
else:
    st.info("No active factors for this bar / time combination — baseline prediction only.")

# ── Section 3: Boost vs Suppress Tables ───────────────────────────────────────

st.divider()
st.subheader("⚖️ Factors Helping vs. Hurting Tonight")

t_col1, t_col2 = st.columns(2)

with t_col1:
    st.markdown("### ⬆ Boosts")
    if boost_impacts:
        for imp in sorted(boost_impacts, key=lambda x: -x["weight"]):
            st.markdown(
                f"<div class='factor-row'>"
                f"<span class='badge-boost'>+{imp['weight']:.2f}</span>"
                f" <strong>{imp['label']}</strong>"
                f"</div>"
                f"<small style='color:#888;padding-left:48px'>{imp['detail']}</small>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    else:
        st.info("No active boost factors.")

with t_col2:
    st.markdown("### ⬇ Suppressors")
    if suppress_impacts:
        for imp in sorted(suppress_impacts, key=lambda x: -x["weight"]):
            st.markdown(
                f"<div class='factor-row'>"
                f"<span class='badge-suppress'>−{imp['weight']:.2f}</span>"
                f" <strong>{imp['label']}</strong>"
                f"</div>"
                f"<small style='color:#888;padding-left:48px'>{imp['detail']}</small>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    else:
        st.success("No active suppressors — nothing is holding this bar back.")

# ── Section 4: Global Environment ─────────────────────────────────────────────

st.divider()
st.subheader("🌎 Global Environment")
st.caption("These signals affect all bars simultaneously — the shared ecosystem.")

g_col1, g_col2, g_col3 = st.columns(3)

with g_col1:
    st.markdown("##### ☁️ Physical Environment")
    temp_val = weather.get("temperature_c")
    precip_val = weather.get("precipitation_mm", 0)
    snow_val = weather.get("snowfall_mm", 0)
    st.metric("Temperature", f"{temp_val:.1f} °C" if temp_val is not None else "—")
    st.metric("Precipitation", f"{precip_val:.1f} mm/h" if precip_val is not None else "—")
    if weather.get("is_severe_weather"):
        st.error("⚠️ Severe Weather Active")
    if weather.get("is_first_nice_day"):
        st.success("☀️ First Nice Spring Day")

with g_col2:
    st.markdown("##### 🏟️ Athletics & TV")
    if signals.get("is_game_day"):
        sport = (
            "Football" if signals.get("is_football_home") else
            "Basketball" if signals.get("is_basketball_home") else
            "Hockey" if signals.get("is_hockey_home") else "Gopher"
        )
        game_hr = signals.get("game_hour")
        st.success(f"🏟️ {sport} Home Game" + (f" @ {game_hr}:00" if game_hr else ""))
        if signals.get("is_rivalry_game"):
            st.warning("🔥 Rivalry Game +1.0 boost")
    else:
        st.info("No Gopher Home Games")

    tv_w = signals.get("tv_game_weight", 0.0)
    if tv_w > 0:
        tv_icon = "📺🔥" if tv_w >= 3.0 else "📺"
        st.metric(f"{tv_icon} TV Sports Weight", f"{tv_w:.1f} / 4.0",
                  help="Super Bowl = 4.0 · Playoffs = 2–3 · Regular game = 1–2")

with g_col3:
    st.markdown("##### 📅 Academic Rhythm")
    in_session = signals.get("classes_in_session", 0)
    if in_session:
        st.info("📚 Classes in Session")
    else:
        st.warning("⛱️ Campus Break")

    if signals.get("is_finals_week"):
        st.error("📑 Finals Week — suppressor –1.5")
    elif signals.get("is_syllabus_week"):
        st.success("🎉 Syllabus Week — boost +1.2")
    elif signals.get("is_midterms_week"):
        st.warning("📖 Midterms Week — suppressor –0.7")

    dss = signals.get("days_since_semester_start")
    if dss is not None:
        st.metric("Days Since Semester Start", int(dss))

# ── Section 5: Bar-Specific Schedule ──────────────────────────────────────────

st.divider()
st.subheader(f"📍 {selected_bar_name} — Schedule & Specials")
st.caption("Bar-specific recurring deals and their configured traffic boosts.")

sch_col1, sch_col2 = st.columns(2)

with sch_col1:
    st.markdown("##### 🕒 Recurring Deals")
    hh = sched.get("happy_hour")
    if hh:
        days_str = "Every day" if hh["days"] == list(range(7)) else \
            ", ".join(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d] for d in hh["days"])
        active_hh = "✅" if feat.get("is_happy_hour", 0) else "⚫"
        st.markdown(
            f"{active_hh} **Happy Hour** ({days_str})  \n"
            f"🕒 {hh['start'][0]}:{hh['start'][1]:02d}–{hh['end'][0]}:{hh['end'][1]:02d}"
        )
    else:
        st.write("*No daily happy hour*")

    specials = sched.get("weekly_specials", [])
    if specials:
        st.markdown("**Weekly Specials:**")
        day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        for sp in specials:
            days = sp.get("days", [sp.get("day")])
            d_str = ", ".join(day_names[d] for d in days if d is not None)
            boost_v = sp.get("traffic_boost", 0.0)
            # Check if this special is currently active
            is_active = bool(feat.get("is_bar_special", 0))
            icon = "🟢" if is_active else "⚪"
            st.caption(f"{icon} **{sp['name']}** ({d_str}) — **+{boost_v * 100:.0f}%** traffic lift")

with sch_col2:
    st.markdown("##### 🌙 Late-Night Migration Draw")
    if sched.get("late_night_draw"):
        ld_val = float(feat.get("bar_late_draw", 0.0) or 0.0)
        st.markdown(
            "This bar has a **late-night migration draw**: drunk crowds relocate here "
            "from cheaper bars starting at 10 PM. The draw ramps from 0.0 → 1.0 between 10 PM and 2 AM."
        )
        st.metric("Current Draw Value", f"{ld_val:.2f} / 1.00")
        # Small gradient chart
        hours_range = [22, 23, 0, 1, 2]
        hours_adj   = [22, 23, 24, 25, 26]
        draw_vals   = [max(0.0, min(1.0, (h - 22) / 4.0)) for h in hours_adj]
        ld_df = pd.DataFrame({"Hour": [f"{h%24:02d}:00" for h in hours_range], "Draw": draw_vals})
        ld_chart = (
            alt.Chart(ld_df)
            .mark_area(color="#8844aa", opacity=0.7, line=True)
            .encode(
                x=alt.X("Hour:N", sort=list(ld_df["Hour"])),
                y=alt.Y("Draw:Q", scale=alt.Scale(domain=[0, 1.05])),
                tooltip=["Hour", alt.Tooltip("Draw:Q", format=".2f")],
            )
            .properties(height=120)
        )
        current_hr_str = f"{actual_hour:02d}:00"
        marker_data = ld_df[ld_df["Hour"] == current_hr_str]
        if not marker_data.empty:
            marker = (
                alt.Chart(marker_data)
                .mark_point(size=150, color="#ffcc00", filled=True)
                .encode(
                    x=alt.X("Hour:N", sort=list(ld_df["Hour"])),
                    y="Draw:Q",
                    tooltip=[alt.Tooltip("Hour:N", title="Current hour")],
                )
            )
            st.altair_chart((ld_chart + marker), use_container_width=True)
        else:
            st.altair_chart(ld_chart, use_container_width=True)
    else:
        st.info("This bar does not have a late-night migration draw.")

# ── Section 6: Live Crowd Signal ──────────────────────────────────────────────

st.divider()
st.subheader("📡 Live Crowd Intelligence")

lc_col1, lc_col2 = st.columns(2)
with lc_col1:
    if recent:
        latest = recent[0]
        st.success(f"✅ Recent crowd report ({latest['observed_at']})")
        st.metric("Reported Wait Time",  f"{latest['wait_minutes']} min")
        pct = latest['pct_full']
        st.metric("Reported Fullness",    f"{pct:.0f}%" if pct is not None else "—")
        st.caption("These live values are injected as `live_wait_minutes` / `live_pct_full` features in the model.")
    else:
        st.info("No crowd reports in the last hour.")
        st.caption("Model is falling back to historical baselines and environmental signals.")

with lc_col2:
    live_w = float(feat.get("live_wait_minutes", 0.0) or 0.0)
    live_p = float(feat.get("live_pct_full", 0.0) or 0.0)
    st.metric("live_wait_minutes (feature)", f"{live_w:.0f} min")
    st.metric("live_pct_full (feature)",     f"{live_p:.0f}%")

# ── Section 7: Raw Feature Vector (collapsible) ────────────────────────────────

st.divider()
with st.expander("🔬 Raw Feature Vector (what the model sees)", expanded=False):
    st.markdown("""
    This is the complete, unmodified feature vector passed to the RandomForest.
    Every column here is exactly what the model receives — no manual overrides.
    """)
    feature_cols = fb.feature_columns(df_feat)
    feat_display = df_feat[feature_cols].iloc[0].to_dict()
    feat_df = pd.DataFrame([
        {"Feature": k, "Value": f"{v:.6f}" if isinstance(v, float) else v, "Type": type(v).__name__}
        for k, v in feat_display.items()
    ])
    st.dataframe(feat_df, use_container_width=True, height=400)

    st.info("""
    **Model scope:**
    - **Global Features** (e.g. `temperature_c`, `is_game_day`) are shared across all bars.
    - **Local Features** (e.g. `is_bar_special`, `bar_late_draw`, `live_wait_minutes`) toggle independently per bar.
    - `drinking_holiday_weight` is a composite signal — the RF splits on holiday magnitude rather than sparse binary flags.
    """)

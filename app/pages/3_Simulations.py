"""Simulation Engine Page — Monte Carlo, Sensitivity, Scenario Comparison, Time-of-Night.

Run with:
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import datetime, timezone

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from config.settings import BARS, BAR_SCHEDULES
from config.tuning import DRINKING_HOLIDAY_WEIGHTS, TRAFFIC_BOOSTS
from features.builder import FeatureBuilder
from app.utils import get_weather, get_today_signals

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Simulations | UMN Bar Forecast",
    page_icon="🎲",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.sim-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 12px;
    backdrop-filter: blur(6px);
}
.sim-kpi-big {
    font-size: 2.6em;
    font-weight: 700;
    line-height: 1.1;
}
.sim-kpi-label {
    font-size: 0.82em;
    color: #aaa;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-boost {
    background: #1a4a1a; color: #44dd44;
    border: 1px solid #228822; border-radius: 4px;
    padding: 2px 8px; font-size: 0.78em; font-weight: bold;
}
.badge-suppress {
    background: #4a1a1a; color: #ff6666;
    border: 1px solid #882222; border-radius: 4px;
    padding: 2px 8px; font-size: 0.78em; font-weight: bold;
}
.risk-high   { color: #ff4444; font-weight: 700; }
.risk-medium { color: #ffaa33; font-weight: 700; }
.risk-low    { color: #44dd44; font-weight: 700; }

.tab-intro {
    padding: 8px 0 16px 0;
    color: #aaa;
    font-size: 0.9em;
    line-height: 1.6;
}
</style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────────────
# SIMULATION ENGINE
# ────────────────────────────────────────────────────────────────────────────

def _get_factor_impacts_raw(feat: pd.Series, sched: dict) -> list[dict]:
    """Return factor impacts identical to Data Pipeline page logic."""
    impacts = []

    def add(label, direction, weight, detail=""):
        impacts.append({"label": label, "dir": direction, "weight": float(weight), "detail": detail})

    if feat.get("is_weekend", 0):
        add("Weekend (Fri–Sun)", "boost", 1.5)
    elif feat.get("is_thursday", 0):
        add("Thursday night", "boost", 0.8)
    if feat.get("is_late_night", 0):
        add("Late night (12–2 AM)", "boost", 0.6)

    if feat.get("is_syllabus_week", 0): add("Syllabus week", "boost", 1.2)
    if feat.get("is_welcome_week", 0):  add("Welcome week", "boost", 1.0)
    if feat.get("is_midterms_week", 0): add("Midterms week", "suppress", 0.7)
    if feat.get("classes_in_session", 0): add("Classes in session", "suppress", 0.5)
    if feat.get("is_finals_week", 0):   add("Finals week", "suppress", 1.5)
    if feat.get("is_study_days", 0):    add("Study/reading days", "suppress", 0.8)
    if feat.get("is_break", 0):         add("Campus break", "suppress", 2.0)
    if feat.get("is_summer_session", 0): add("Summer session", "suppress", 1.0)

    dub = feat.get("days_until_break")
    if dub is not None and not pd.isna(dub) and 0 < float(dub) <= 7:
        boost = max(0.0, round((7 - float(dub)) / 7 * 0.8, 2))
        add(f"Pre-break excitement ({int(dub)}d)", "boost", boost)

    for hol_col, w in DRINKING_HOLIDAY_WEIGHTS.items():
        if feat.get(hol_col, 0):
            lbl = hol_col.replace("is_", "").replace("_", " ").title()
            add(lbl, "boost", w)

    if feat.get("is_game_day", 0):
        if feat.get("is_football_home", 0):   add("Football home game", "boost", 2.5)
        elif feat.get("is_basketball_home", 0): add("Basketball home game", "boost", 2.0)
        elif feat.get("is_hockey_home", 0):   add("Hockey home game", "boost", 1.8)
        else:                                  add("Gopher home game", "boost", 2.0)
        if feat.get("is_rivalry_game", 0):    add("Rivalry game", "boost", 1.0)
        hug = feat.get("hours_until_game")
        if hug is not None and not pd.isna(hug):
            if 0 < float(hug) <= 2: add("Pre-game window", "boost", 0.5)
            elif float(hug) < 0:    add("Post-game surge", "boost", 0.8)

    tv_w = feat.get("tv_game_weight", 0.0)
    if tv_w and not pd.isna(tv_w) and float(tv_w) > 0:
        add(f"TV sports ({float(tv_w):.1f}/4.0)", "boost", float(tv_w))

    if feat.get("is_wild_game", 0):        add("Wild game", "boost", 0.5)
    if feat.get("is_timberwolves_game", 0): add("Timberwolves game", "boost", 0.4)
    if feat.get("is_nhl_playoffs", 0):     add("NHL Playoffs", "boost", 0.7)
    if feat.get("is_nba_playoffs", 0):     add("NBA Playoffs", "boost", 0.6)

    temp = feat.get("temperature_c")
    if temp is not None and not pd.isna(temp):
        t = float(temp)
        if t < 0:
            add(f"Cold weather ({t:.0f}°C)", "suppress", round(min(2.0, abs(t) / 5.0 * 0.5), 2))
        elif t > 22:
            add(f"Warm weather ({t:.0f}°C)", "boost", 0.3)

    if feat.get("is_first_nice_day", 0): add("First nice spring day", "boost", 1.0)

    precip = feat.get("precipitation_mm")
    if precip is not None and not pd.isna(precip) and float(precip) > 2:
        add(f"Precipitation ({float(precip):.1f} mm/h)", "suppress",
            round(min(1.5, float(precip) / 10.0 * 1.5), 2))

    snow = feat.get("snowfall_mm")
    if snow is not None and not pd.isna(snow) and float(snow) > 5:
        add(f"Snowfall ({float(snow):.1f} mm)", "suppress", 1.0)

    if feat.get("is_severe_weather", 0): add("Severe weather", "suppress", 2.0)
    if feat.get("is_happy_hour", 0):
        add(f"Happy hour", "boost", 0.4)
    if feat.get("is_bar_special", 0):
        for sp in sched.get("weekly_specials", []):
            bv = sp.get("traffic_boost", 0.0)
            add(f"{sp['name']}", "boost", float(bv))

    ld = feat.get("bar_late_draw", 0.0)
    if ld and not pd.isna(ld) and float(ld) > 0:
        add(f"Late-night draw ({float(ld)*100:.0f}%)", "boost", float(ld))

    gsi = feat.get("greek_social_intensity", 0.0)
    if gsi and not pd.isna(gsi) and float(gsi) > 0:
        add(f"Greek social intensity ({float(gsi):.2f})", "boost", float(gsi))
    if feat.get("is_greek_bid_day", 0):       add("Greek bid day", "boost", 0.9)
    if feat.get("is_greek_rush_week", 0):     add("Greek rush week", "suppress", 0.5)
    if feat.get("is_greek_thursday", 0):      add("Greek Thursday", "boost", 0.4)
    if feat.get("is_greek_pregame_window", 0): add("Greek pregame window", "boost", 0.3)

    return impacts


class MonteCarloSimulator:
    """Fast, pure-NumPy Monte Carlo over factor scores.

    Strategy: perturb each active factor's weight by Normal(0, sigma),
    clamp to [0, max_w], recompute net_score, map to pct_full via a linear
    anchor calibrated to (0 → 30%, 6 → 100%).
    """

    PCT_FULL_BASE  = 30.0   # expected fullness at net_score = 0
    PCT_FULL_SCALE = 11.0   # each +1.0 net_score adds ~11 pp of fullness

    def __init__(self, impacts: list[dict], point_net_score: float):
        self.impacts = impacts
        self.point_net_score = point_net_score
        self._pct_point = self._score_to_pct(point_net_score)

    def _score_to_pct(self, score):
        """Works for both scalar and numpy array inputs."""
        return np.clip(self.PCT_FULL_BASE + score * self.PCT_FULL_SCALE, 0, 100)

    def run(self, n_sims: int, sigma: float, seed: int = 42) -> np.ndarray:
        rng = np.random.default_rng(seed)
        weights = np.array([i["weight"] for i in self.impacts], dtype=float)
        signs   = np.array([1.0 if i["dir"] == "boost" else -1.0 for i in self.impacts])

        # Shape: (n_sims, n_factors)
        noise = rng.normal(0, sigma, size=(n_sims, len(weights)))
        perturbed = np.clip(weights + noise, 0, weights * 3 + 0.01)
        net_scores = (perturbed * signs).sum(axis=1)
        return self._score_to_pct(net_scores)

    @property
    def point_pct(self) -> float:
        return float(self._pct_point)


def _build_feat_for_bar(bar_id: int, dt: datetime, weather: dict, signals: dict) -> tuple[pd.Series, dict]:
    fb = FeatureBuilder()
    raw = {
        "observed_at": dt, "bar_id": bar_id,
        "wait_minutes": 0, "pct_full": 0, "drink_wait_minutes": 0,
        "temperature_c": weather.get("temperature_c"),
        "precipitation_mm": weather.get("precipitation_mm"),
        "wind_chill_c": weather.get("wind_chill_c"),
        "snowfall_mm": weather.get("snowfall_mm"),
        "wind_speed_ms": weather.get("wind_speed_ms"),
        "is_severe_weather": int(bool(weather.get("is_severe_weather"))),
        "cloud_cover": weather.get("cloud_cover"),
        "is_first_nice_day": int(bool(weather.get("is_first_nice_day"))),
    }
    for k, v in signals.items():
        raw[k] = v
    df = fb.build(pd.DataFrame([raw]))
    sched = BAR_SCHEDULES.get(bar_id, {})
    return df.iloc[0], sched


# ── SCENARIO PRESETS ─────────────────────────────────────────────────────────

_SCENARIOS: dict[str, dict] = {
    "Normal Thursday": {
        "is_thursday": 1, "classes_in_session": 1, "hour": 21,
        "is_weekend": 0, "is_game_day": 0,
    },
    "Football Saturday": {
        "is_weekend": 1, "is_football_home": 1, "is_game_day": 1,
        "is_rivalry_game": 0, "classes_in_session": 1, "hour": 22,
    },
    "St. Patrick's Day": {
        "is_st_patricks": 1, "is_weekend": 1, "is_game_day": 0,
        "classes_in_session": 1, "hour": 21,
    },
    "Finals Week Night": {
        "is_finals_week": 1, "classes_in_session": 1,
        "is_thursday": 1, "hour": 20,
    },
    "Blackout Wednesday": {
        "is_blackout_wednesday": 1, "is_thursday": 0, "is_weekend": 0,
        "classes_in_session": 0, "hour": 22,
    },
    "KK Tuesday (normal)": {
        "classes_in_session": 1, "hour": 22,
    },
    "Dead of Winter Break": {
        "is_break": 1, "is_weekend": 0, "classes_in_session": 0, "hour": 21,
    },
}


def _build_scenario_impacts(scenario_flags: dict) -> list[dict]:
    """Build impacts list purely from a scenario flag dict (no DB/weather needed)."""

    class _FakeSeries(dict):
        def get(self, key, default=None):
            return self[key] if key in self else default

    feat = _FakeSeries({
        "is_weekend": 0, "is_thursday": 0, "is_late_night": 0,
        "is_syllabus_week": 0, "is_welcome_week": 0, "is_midterms_week": 0,
        "classes_in_session": 0, "is_finals_week": 0, "is_study_days": 0,
        "is_break": 0, "is_summer_session": 0, "is_game_day": 0,
        "is_football_home": 0, "is_basketball_home": 0, "is_hockey_home": 0,
        "is_rivalry_game": 0, "is_tv_sports": 0, "tv_game_weight": 0.0,
        "is_wild_game": 0, "is_timberwolves_game": 0, "is_nhl_playoffs": 0,
        "is_nba_playoffs": 0, "is_severe_weather": 0, "is_first_nice_day": 0,
        "is_happy_hour": 0, "is_bar_special": 0, "bar_late_draw": 0.0,
        "greek_social_intensity": 0.0, "is_greek_bid_day": 0,
        "is_greek_rush_week": 0, "is_greek_thursday": 0,
        "is_greek_pregame_window": 0, "is_holiday": 0,
        "hours_until_game": None, "days_until_break": None,
        "temperature_c": None, "precipitation_mm": None, "snowfall_mm": None,
    })
    for k, v in DRINKING_HOLIDAY_WEIGHTS.items():
        feat[k] = 0
    feat.update(scenario_flags)

    # If late night flag depends on hour
    hour = scenario_flags.get("hour", 21)
    if 0 <= hour <= 2:
        feat["is_late_night"] = 1

    return _get_factor_impacts_raw(feat, {})


# ── PAGE LAYOUT ───────────────────────────────────────────────────────────────

st.title("🎲 Simulation Engine")
st.markdown("""
<div class='tab-intro'>
Run stochastic simulations against the bar traffic factor system.
Every chart mirrors the exact weights and logic used by the prediction algorithm.
</div>
""", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Simulation Settings")

    bar_names = [b["name"] for b in BARS]
    selected_bar = st.selectbox("Bar", bar_names)
    bar_id = next(i + 1 for i, b in enumerate(BARS) if b["name"] == selected_bar)

    sim_date = st.date_input("Date", value=datetime.now().date())
    sim_hour = st.slider("Hour (24h)", min_value=14, max_value=26, value=21, step=1)
    actual_hour = sim_hour % 24

    st.divider()
    n_sims = st.select_slider(
        "Monte Carlo iterations",
        options=[500, 1_000, 2_000, 5_000, 10_000],
        value=2_000,
    )
    sigma = st.slider(
        "Factor uncertainty σ",
        min_value=0.05, max_value=1.0, value=0.25, step=0.05,
        help="Standard deviation of noise added to each factor weight per iteration. "
             "Higher = more spread-out distribution.",
    )

# Load live data
weather  = get_weather()
signals  = get_today_signals(sim_date)
sim_dt   = datetime(sim_date.year, sim_date.month, sim_date.day, actual_hour, 0, 0, tzinfo=timezone.utc)

feat, sched = _build_feat_for_bar(bar_id, sim_dt, weather, signals)
impacts = _get_factor_impacts_raw(feat, sched)

boost_sum    = sum(i["weight"] for i in impacts if i["dir"] == "boost")
suppress_sum = sum(i["weight"] for i in impacts if i["dir"] == "suppress")
net_score    = boost_sum - suppress_sum

sim = MonteCarloSimulator(impacts, net_score)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🎲 Monte Carlo",
    "🌪️ Sensitivity",
    "🔀 Scenarios",
    "⏱️ Time-of-Night",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — MONTE CARLO
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("""
    <div class='tab-intro'>
    Runs <strong>N random iterations</strong> where each active factor's weight is perturbed by
    Gaussian noise (σ configured in the sidebar). Shows the resulting distribution of
    predicted bar fullness so you can see best-case, worst-case, and most-likely outcomes.
    </div>
    """, unsafe_allow_html=True)

    # Cache key for session state
    cache_key = f"mc_{bar_id}_{sim_date}_{sim_hour}_{n_sims}_{sigma}"
    if cache_key not in st.session_state:
        with st.spinner(f"Running {n_sims:,} Monte Carlo iterations…"):
            st.session_state[cache_key] = sim.run(n_sims, sigma)

    pct_samples = st.session_state[cache_key]

    p05  = float(np.percentile(pct_samples, 5))
    p25  = float(np.percentile(pct_samples, 25))
    p50  = float(np.percentile(pct_samples, 50))
    p75  = float(np.percentile(pct_samples, 75))
    p95  = float(np.percentile(pct_samples, 95))
    prob_packed = float(np.mean(pct_samples >= 90)) * 100
    prob_busy   = float(np.mean(pct_samples >= 70)) * 100

    # ── KPI row ──────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Median Fullness", f"{p50:.0f}%", help="50th percentile of simulation")
    with k2:
        st.metric("90% CI Range", f"{p05:.0f}% – {p95:.0f}%", help="5th–95th percentile")
    with k3:
        risk_class = "risk-high" if prob_packed > 40 else "risk-medium" if prob_packed > 15 else "risk-low"
        st.markdown(
            f"<div class='sim-card'>"
            f"<div class='sim-kpi-label'>P(bar &gt; 90% full)</div>"
            f"<div class='sim-kpi-big {risk_class}'>{prob_packed:.0f}%</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with k4:
        risk_class2 = "risk-high" if prob_busy > 60 else "risk-medium" if prob_busy > 30 else "risk-low"
        st.markdown(
            f"<div class='sim-card'>"
            f"<div class='sim-kpi-label'>P(bar &gt; 70% full)</div>"
            f"<div class='sim-kpi-big {risk_class2}'>{prob_busy:.0f}%</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Histogram with KDE overlay ────────────────────────────────────────────
    st.subheader("📊 Fullness Distribution")

    # Bin the samples into a histogram
    bins = np.arange(0, 105, 5)
    counts, edges = np.histogram(pct_samples, bins=bins)
    hist_df = pd.DataFrame({
        "pct_full": (edges[:-1] + edges[1:]) / 2,
        "count": counts,
        "freq": counts / n_sims,
    })

    hist_chart = (
        alt.Chart(hist_df)
        .mark_bar(color="#3377ff", opacity=0.75, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("pct_full:Q", bin=False, title="Simulated Bar Fullness (%)",
                    scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("freq:Q", title="Frequency", axis=alt.Axis(format=".0%")),
            tooltip=[
                alt.Tooltip("pct_full:Q",  title="Fullness %", format=".0f"),
                alt.Tooltip("freq:Q",       title="Frequency",  format=".1%"),
                alt.Tooltip("count:Q",      title="Iterations"),
            ],
        )
        .properties(height=300)
    )

    # Percentile vertical rules
    pct_rules_df = pd.DataFrame([
        {"x": p05,  "label": "5th pct",  "color": "#aaaaff"},
        {"x": p50,  "label": "Median",   "color": "#ffffff"},
        {"x": p95,  "label": "95th pct", "color": "#aaaaff"},
        {"x": sim._pct_point, "label": "Point estimate", "color": "#ffcc00"},
    ])
    rules = (
        alt.Chart(pct_rules_df)
        .mark_rule(strokeDash=[6, 3], strokeWidth=2)
        .encode(
            x="x:Q",
            color=alt.Color("color:N", scale=None),
            tooltip=[alt.Tooltip("label:N", title=""), alt.Tooltip("x:Q", format=".1f", title="Fullness %")],
        )
    )

    st.altair_chart((hist_chart + rules).interactive(), use_container_width=True)

    # Legend
    leg_col1, leg_col2, leg_col3, leg_col4 = st.columns(4)
    leg_col1.markdown("🟡 **Point estimate** (ML model)")
    leg_col2.markdown("⬜ **Median** of simulation")
    leg_col3.markdown("🔵 **5th / 95th** percentile")
    leg_col4.markdown(f"*σ = {sigma}  ·  N = {n_sims:,}*")

    st.divider()

    # ── IQR box-and-whisker summary ───────────────────────────────────────────
    st.subheader("📦 Quartile Summary")

    box_df = pd.DataFrame([{
        "Bar": selected_bar,
        "min":  float(pct_samples.min()),
        "q1":   p25,
        "median": p50,
        "q3":   p75,
        "max":  float(pct_samples.max()),
    }])

    box_chart = (
        alt.Chart(box_df)
        .mark_boxplot(color="#3377ff", median={"color": "white"}, size=60)
        .encode(
            x=alt.X("Bar:N", title=None),
            y=alt.Y("median:Q", title="Fullness (%)", scale=alt.Scale(domain=[0, 100])),
        )
        .properties(height=200)
    )

    # Use a manual box via layers since altair boxplot needs raw data
    raw_sample_df = pd.DataFrame({"Bar": selected_bar, "pct_full": pct_samples})
    box2 = (
        alt.Chart(raw_sample_df)
        .mark_boxplot(extent="min-max", color="#3377ff",
                      median={"color": "white"}, size=50)
        .encode(
            x=alt.X("Bar:N", title=None),
            y=alt.Y("pct_full:Q", title="Fullness (%)", scale=alt.Scale(domain=[0, 100])),
        )
        .properties(height=220)
    )
    st.altair_chart(box2, use_container_width=True)

    # Stats table
    stats_df = pd.DataFrame([{
        "Min": f"{pct_samples.min():.1f}%",
        "5th pct": f"{p05:.1f}%",
        "25th pct": f"{p25:.1f}%",
        "Median": f"{p50:.1f}%",
        "75th pct": f"{p75:.1f}%",
        "95th pct": f"{p95:.1f}%",
        "Max": f"{pct_samples.max():.1f}%",
        "Std Dev": f"{pct_samples.std():.1f}pp",
    }])
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Factor net-score decomposition ────────────────────────────────────────
    st.subheader("⚡ Current Factor Decomposition")
    st.caption(f"Net score = **{net_score:+.2f}** → point estimate **{sim._pct_point:.0f}% full**")

    dec_col1, dec_col2, dec_col3 = st.columns(3)
    with dec_col1:
        st.metric("⬆ Total Boost", f"+{boost_sum:.2f}")
    with dec_col2:
        st.metric("⬇ Total Suppress", f"−{suppress_sum:.2f}")
    with dec_col3:
        delta_color = "normal" if net_score > 0 else "inverse"
        st.metric("⚡ Net Score", f"{net_score:+.2f}")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — SENSITIVITY / TORNADO
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("""
    <div class='tab-intro'>
    For each active factor, the algorithm swings it from <strong>+σ above</strong> its nominal weight
    to <strong>−σ below</strong> (clamped to zero) while holding all others constant.
    The resulting change in predicted fullness is the factor's <em>sensitivity swing</em>.
    Factors are ranked by absolute swing — the wider the bar, the more influential the factor.
    </div>
    """, unsafe_allow_html=True)

    if not impacts:
        st.info("No active factors for this bar/time — all predictions are baseline only.")
    else:
        tornado_rows = []
        for idx, imp in enumerate(impacts):
            base_weights = [i["weight"] for i in impacts]
            signs_all    = [1.0 if i["dir"] == "boost" else -1.0 for i in impacts]

            # High: factor weight + sigma
            w_high = base_weights.copy()
            w_high[idx] = base_weights[idx] + sigma
            score_high = sum(w * s for w, s in zip(w_high, signs_all))
            pct_high   = sim._score_to_pct(score_high)

            # Low: factor weight - sigma (clamped to 0)
            w_low = base_weights.copy()
            w_low[idx] = max(0.0, base_weights[idx] - sigma)
            score_low = sum(w * s for w, s in zip(w_low, signs_all))
            pct_low   = sim._score_to_pct(score_low)

            swing = abs(pct_high - pct_low)
            tornado_rows.append({
                "Factor":    imp["label"],
                "Direction": imp["dir"],
                "Swing":     round(swing, 2),
                "High":      round(pct_high, 1),
                "Low":       round(pct_low, 1),
                "Nominal":   round(imp["weight"], 3),
            })

        tornado_df = (
            pd.DataFrame(tornado_rows)
            .sort_values("Swing", ascending=False)
            .reset_index(drop=True)
        )

        # Keep top 20 for clarity
        top_n = st.slider("Show top N factors", min_value=5, max_value=len(tornado_df), value=min(20, len(tornado_df)))
        tornado_top = tornado_df.head(top_n).copy()

        # Color by direction
        tornado_top["Color"] = tornado_top["Direction"].map({"boost": "#22cc66", "suppress": "#cc3333"})

        # Tornado bars: each factor gets one bar showing [Low, High] range, centered on nominal
        tornado_chart = (
            alt.Chart(tornado_top)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                      cornerRadiusBottomLeft=4, cornerRadiusBottomRight=4)
            .encode(
                y=alt.Y("Factor:N", sort=list(tornado_top["Factor"]), title=None),
                x=alt.X("Low:Q",   title="Fullness % Range (Low → High)", scale=alt.Scale(domain=[0, 100])),
                x2="High:Q",
                color=alt.Color("Color:N", scale=None, legend=None),
                tooltip=[
                    alt.Tooltip("Factor:N"),
                    alt.Tooltip("Low:Q",    title="Low (−σ)",  format=".1f"),
                    alt.Tooltip("High:Q",   title="High (+σ)", format=".1f"),
                    alt.Tooltip("Swing:Q",  title="Swing pp",  format=".1f"),
                    alt.Tooltip("Nominal:Q",title="Nominal wt",format=".3f"),
                ],
            )
            .properties(height=max(280, top_n * 28))
        )

        # Point-estimate rule
        point_rule = (
            alt.Chart(pd.DataFrame({"x": [sim._pct_point]}))
            .mark_rule(color="#ffcc00", strokeDash=[6, 3], strokeWidth=2)
            .encode(x="x:Q")
        )

        st.altair_chart((tornado_chart + point_rule).interactive(), use_container_width=True)
        st.caption("🟡 Dashed line = point estimate (ML model). Bars show ±σ swing around that.")

        st.divider()
        st.subheader("📋 Ranked Sensitivity Table")
        display_cols = ["Factor", "Direction", "Swing", "Low", "High", "Nominal"]
        st.dataframe(
            tornado_top[display_cols].rename(columns={
                "Swing":   "Swing (pp)",
                "Low":     "Low % (−σ)",
                "High":    "High % (+σ)",
                "Nominal": "Factor Weight",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — SCENARIO COMPARISON
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("""
    <div class='tab-intro'>
    Compare how different night-types would score. Select up to 4 preset scenarios or
    build a custom scenario with manual flags. Each scenario's factor impacts are scored
    independently using the same algorithm logic.
    </div>
    """, unsafe_allow_html=True)

    preset_names = list(_SCENARIOS.keys())
    sc_col1, sc_col2 = st.columns([2, 1])
    with sc_col1:
        selected_scenarios = st.multiselect(
            "Choose scenarios to compare",
            preset_names,
            default=["Normal Thursday", "Football Saturday", "St. Patrick's Day", "Finals Week Night"],
            max_selections=6,
        )
    with sc_col2:
        show_custom = st.checkbox("Add custom scenario")

    # Custom scenario builder
    custom_flags: dict = {}
    if show_custom:
        st.markdown("#### 🛠️ Custom Scenario Builder")
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            custom_flags["is_weekend"]       = int(st.checkbox("Weekend"))
            custom_flags["is_thursday"]      = int(st.checkbox("Thursday"))
            custom_flags["is_late_night"]    = int(st.checkbox("Late night (12-2 AM)"))
        with cc2:
            custom_flags["is_game_day"]      = int(st.checkbox("Gopher game day"))
            custom_flags["is_football_home"] = int(st.checkbox("Football home"))
            custom_flags["is_rivalry_game"]  = int(st.checkbox("Rivalry game"))
        with cc3:
            custom_flags["classes_in_session"] = int(st.checkbox("Classes in session", value=True))
            custom_flags["is_finals_week"]   = int(st.checkbox("Finals week"))
            custom_flags["is_break"]         = int(st.checkbox("Campus break"))
        with cc4:
            custom_flags["is_st_patricks"]   = int(st.checkbox("St. Patrick's Day"))
            custom_flags["is_halloween"]     = int(st.checkbox("Halloween"))
            custom_flags["is_bar_crawl"]     = int(st.checkbox("Bar crawl"))
            custom_flags["is_blackout_wednesday"] = int(st.checkbox("Blackout Wednesday"))
        custom_hour = st.slider("Hour for custom scenario", 14, 26, 21)
        custom_flags["hour"] = custom_hour
        custom_flags["is_late_night"] = int(custom_hour % 24 <= 2)
        selected_scenarios = selected_scenarios + ["⭐ Custom"]

    if not selected_scenarios:
        st.info("Select at least one scenario above.")
    else:
        # Compute scores for each scenario
        scenario_data = []
        for sc_name in selected_scenarios:
            if sc_name == "⭐ Custom":
                sc_flags = custom_flags
            else:
                sc_flags = _SCENARIOS[sc_name]

            sc_impacts = _build_scenario_impacts(sc_flags)
            sc_boost = sum(i["weight"] for i in sc_impacts if i["dir"] == "boost")
            sc_supp  = sum(i["weight"] for i in sc_impacts if i["dir"] == "suppress")
            sc_net   = sc_boost - sc_supp
            sc_pct   = MonteCarloSimulator(sc_impacts, sc_net)._pct_point

            scenario_data.append({
                "Scenario":   sc_name,
                "Boost":      round(sc_boost, 2),
                "Suppress":   round(sc_supp, 2),
                "Net Score":  round(sc_net, 2),
                "Est. Fullness %": round(sc_pct, 1),
                "_impacts":   sc_impacts,
            })

        sc_df = pd.DataFrame(scenario_data).drop(columns=["_impacts"])

        # ── Summary metric cards ──────────────────────────────────────────────
        st.subheader("📊 Scenario Summary")

        metric_cols = st.columns(len(scenario_data))
        for col, row in zip(metric_cols, scenario_data):
            pct = row["Est. Fullness %"]
            color = "#ff4444" if pct >= 85 else "#ffaa33" if pct >= 65 else "#44dd44"
            col.markdown(
                f"<div class='sim-card' style='text-align:center'>"
                f"<div class='sim-kpi-label'>{row['Scenario']}</div>"
                f"<div class='sim-kpi-big' style='color:{color}'>{pct:.0f}%</div>"
                f"<div style='font-size:0.78em;color:#aaa'>Net: {row['Net Score']:+.2f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.divider()

        # ── Grouped bar chart: Boost vs Suppress per scenario ────────────────
        st.subheader("⚖️ Boost vs Suppress by Scenario")

        long_rows = []
        for row in scenario_data:
            long_rows.append({"Scenario": row["Scenario"], "Type": "Boost ⬆",    "Value":  row["Boost"]})
            long_rows.append({"Scenario": row["Scenario"], "Type": "Suppress ⬇", "Value": -row["Suppress"]})
        long_df = pd.DataFrame(long_rows)

        grouped_chart = (
            alt.Chart(long_df)
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4,
                      cornerRadiusBottomLeft=4, cornerRadiusBottomRight=4)
            .encode(
                x=alt.X("Scenario:N", title=None),
                y=alt.Y("Value:Q",    title="Score",
                        scale=alt.Scale(domainMin=-4)),
                color=alt.Color(
                    "Type:N",
                    scale=alt.Scale(
                        domain=["Boost ⬆", "Suppress ⬇"],
                        range=["#22cc66", "#cc3333"],
                    ),
                ),
                xOffset="Type:N",
                tooltip=["Scenario:N", "Type:N", alt.Tooltip("Value:Q", format=".2f")],
            )
            .properties(height=350)
        )
        zero_rule = (
            alt.Chart(pd.DataFrame({"y": [0]}))
            .mark_rule(color="#666", strokeDash=[4, 4])
            .encode(y="y:Q")
        )
        st.altair_chart((grouped_chart + zero_rule).interactive(), use_container_width=True)

        st.divider()

        # ── Factor heatmap across scenarios ───────────────────────────────────
        st.subheader("🔥 Factor Heatmap")
        st.caption("Shows which factors are active (and at what weight) for each scenario.")

        hm_rows = []
        all_factor_labels = set()
        for row in scenario_data:
            for imp in row["_impacts"]:
                all_factor_labels.add(imp["label"])

        for row in scenario_data:
            active_map = {i["label"]: i["weight"] * (1 if i["dir"] == "boost" else -1)
                          for i in row["_impacts"]}
            for factor in all_factor_labels:
                hm_rows.append({
                    "Scenario": row["Scenario"],
                    "Factor":   factor,
                    "Score":    round(active_map.get(factor, 0.0), 2),
                })

        hm_df = pd.DataFrame(hm_rows)
        # Sort factors by mean absolute score
        factor_order = (
            hm_df.groupby("Factor")["Score"]
            .apply(lambda x: x.abs().mean())
            .sort_values(ascending=False)
            .index.tolist()
        )

        heatmap = (
            alt.Chart(hm_df)
            .mark_rect()
            .encode(
                x=alt.X("Scenario:N", title=None),
                y=alt.Y("Factor:N", sort=factor_order, title=None),
                color=alt.Color(
                    "Score:Q",
                    scale=alt.Scale(scheme="redblue", domainMid=0),
                    legend=alt.Legend(title="Signed weight"),
                ),
                tooltip=["Scenario:N", "Factor:N", alt.Tooltip("Score:Q", format=".2f")],
            )
            .properties(height=max(200, len(factor_order) * 22))
        )
        st.altair_chart(heatmap.interactive(), use_container_width=True)

        st.divider()

        # ── Summary table ─────────────────────────────────────────────────────
        st.subheader("📋 Summary Table")
        st.dataframe(sc_df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — TIME-OF-NIGHT SIMULATION
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("""
    <div class='tab-intro'>
    Runs a mini Monte Carlo for <strong>each hour between 2 PM and 2 AM</strong>.
    The median line shows the most likely fullness trajectory; the shaded band shows
    the 10th–90th percentile range. Wider bands = higher uncertainty at that hour.
    The 🔴 risk window highlights periods where P(bar &gt; 90% full) exceeds the threshold.
    </div>
    """, unsafe_allow_html=True)

    ton_col1, ton_col2 = st.columns([2, 1])
    with ton_col1:
        selected_bars_ton = st.multiselect(
            "Bars to simulate",
            bar_names,
            default=bar_names,
        )
    with ton_col2:
        risk_threshold = st.slider("Risk threshold (%)", 20, 80, 30, step=5,
                                   help="P(bar > 90% full) above this → flagged as risk window")

    ton_n_sims = 500  # fixed for hourly loop — keep fast

    hours_range = list(range(14, 27))  # 2 PM → 2 AM

    @st.cache_data(show_spinner=False, ttl=300)
    def _run_hourly_simulation(bar_id: int, date_str: str, n_per_hour: int, sigma: float) -> pd.DataFrame:
        weather_loc  = get_weather()
        signals_loc  = get_today_signals(datetime.fromisoformat(date_str).date())
        rows = []
        for h in hours_range:
            ah = h % 24
            dt = datetime(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]),
                          ah, 0, 0, tzinfo=timezone.utc)
            f, sc = _build_feat_for_bar(bar_id, dt, weather_loc, signals_loc)
            imps = _get_factor_impacts_raw(f, sc)
            bs = sum(i["weight"] for i in imps if i["dir"] == "boost")
            ss = sum(i["weight"] for i in imps if i["dir"] == "suppress")
            ns = bs - ss
            sim_h = MonteCarloSimulator(imps, ns)
            if n_per_hour > 0:
                samples = sim_h.run(n_per_hour, sigma, seed=h * 7 + bar_id)
            else:
                samples = np.array([sim_h._pct_point])
            rows.append({
                "hour_int":   h,
                "hour_label": f"{h % 24:02d}:00",
                "p10":  float(np.percentile(samples, 10)),
                "p25":  float(np.percentile(samples, 25)),
                "p50":  float(np.percentile(samples, 50)),
                "p75":  float(np.percentile(samples, 75)),
                "p90":  float(np.percentile(samples, 90)),
                "point":float(sim_h._pct_point),
                "prob_packed": float(np.mean(samples >= 90)) * 100,
            })
        return pd.DataFrame(rows)

    if not selected_bars_ton:
        st.info("Select at least one bar above.")
    else:
        date_str = sim_date.isoformat()

        BAR_COLORS = {
            "Blarney's Pub and Grill": "#1cb864",
            "Sally's Saloon":          "#9944cc",
            "Kollege Klub":            "#CC8800",
        }

        all_ton_layers = []

        with st.spinner("Running hourly simulations for all bars…"):
            for b in BARS:
                if b["name"] not in selected_bars_ton:
                    continue
                bid = next(i + 1 for i, bb in enumerate(BARS) if bb["name"] == b["name"])
                df_h = _run_hourly_simulation(bid, date_str, ton_n_sims, sigma)
                df_h["bar"] = b["name"]
                df_h["color"] = BAR_COLORS.get(b["name"], "#ffffff")
                all_ton_layers.append(df_h)

        if all_ton_layers:
            all_df = pd.concat(all_ton_layers, ignore_index=True)
            hour_order = [f"{h%24:02d}:00" for h in hours_range]

            bar_color_domain = [b for b in BAR_COLORS if b in selected_bars_ton]
            bar_color_range  = [BAR_COLORS[b] for b in bar_color_domain]

            base = alt.Chart(all_df).encode(
                x=alt.X("hour_label:N", sort=hour_order, title="Hour"),
                color=alt.Color(
                    "bar:N", title="Bar",
                    scale=alt.Scale(domain=bar_color_domain, range=bar_color_range),
                ),
            )

            # Shaded band p10–p90
            band = base.mark_area(opacity=0.18).encode(
                y=alt.Y("p10:Q", title="Fullness (%)", scale=alt.Scale(domain=[0, 105])),
                y2="p90:Q",
            )
            # IQR band p25–p75
            band_iqr = base.mark_area(opacity=0.28).encode(
                y="p25:Q",
                y2="p75:Q",
            )
            # Median line
            median_line = base.mark_line(strokeWidth=2.5, point=True).encode(
                y=alt.Y("p50:Q", title="Fullness (%)"),
                tooltip=[
                    alt.Tooltip("bar:N",          title="Bar"),
                    alt.Tooltip("hour_label:N",   title="Hour"),
                    alt.Tooltip("p10:Q",          title="10th pct %", format=".1f"),
                    alt.Tooltip("p50:Q",          title="Median %",   format=".1f"),
                    alt.Tooltip("p90:Q",          title="90th pct %", format=".1f"),
                    alt.Tooltip("prob_packed:Q",  title="P(>90%)",    format=".0f"),
                ],
            )
            # 90% full reference line
            ref_90 = (
                alt.Chart(pd.DataFrame({"y": [90]}))
                .mark_rule(color="#ff4444", strokeDash=[4, 3], strokeWidth=1.5)
                .encode(y="y:Q")
            )

            st.subheader("📈 Full-Night Trajectory with Uncertainty Bands")
            st.caption("Dark band = 10–90 pct · Light band = 25–75 pct · Line = median · 🔴 dashed = 90% capacity")
            st.altair_chart(
                (band + band_iqr + median_line + ref_90).interactive().properties(height=360),
                use_container_width=True,
            )

            st.divider()

            # ── Risk window table ─────────────────────────────────────────────
            st.subheader(f"🚨 Risk Windows — P(>90% full) > {risk_threshold}%")

            risk_rows = all_df[all_df["prob_packed"] >= risk_threshold][
                ["bar", "hour_label", "p50", "p90", "prob_packed"]
            ].rename(columns={
                "bar":          "Bar",
                "hour_label":   "Hour",
                "p50":          "Median Fullness %",
                "p90":          "90th Pct Fullness %",
                "prob_packed":  "P(>90% full) %",
            }).sort_values(["Bar", "Hour"])

            if risk_rows.empty:
                st.success(f"No risk windows detected (P threshold = {risk_threshold}%). Should be a chill night!")
            else:
                st.dataframe(risk_rows, use_container_width=True, hide_index=True)

            st.divider()

            # ── Probability heat lane ─────────────────────────────────────────
            st.subheader("🌡️ Packed-Bar Probability Heat Lane")
            st.caption("Color = P(bar > 90% full) at each hour. Red = high risk.")

            heat_chart = (
                alt.Chart(all_df)
                .mark_rect()
                .encode(
                    x=alt.X("hour_label:N", sort=hour_order, title="Hour"),
                    y=alt.Y("bar:N", title=None),
                    color=alt.Color(
                        "prob_packed:Q",
                        scale=alt.Scale(scheme="reds", domain=[0, 100]),
                        legend=alt.Legend(title="P(>90%) %"),
                    ),
                    tooltip=[
                        alt.Tooltip("bar:N",          title="Bar"),
                        alt.Tooltip("hour_label:N",   title="Hour"),
                        alt.Tooltip("prob_packed:Q",  title="P(>90%)", format=".0f"),
                        alt.Tooltip("p50:Q",          title="Median %", format=".1f"),
                    ],
                )
                .properties(height=130)
            )
            st.altair_chart(heat_chart.interactive(), use_container_width=True)

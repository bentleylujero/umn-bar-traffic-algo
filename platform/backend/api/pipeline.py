"""Generic pipeline execution endpoint + semantic topology definitions."""

from __future__ import annotations

from fastapi import APIRouter

from platform.backend.schemas import PipelineDef, PipelineRunResult

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResult)
def run_pipeline(pipeline: PipelineDef) -> PipelineRunResult:
    """Execute a user-defined pipeline DAG.

    Accepts a full PipelineDef (nodes + edges) and runs it in topological
    order, returning per-node results and any predictions generated.
    """
    from platform.backend.engine.executor import execute_pipeline

    return execute_pipeline(pipeline)


@router.get("/definitions")
def list_pipeline_definitions() -> list[dict]:
    """Return pre-built named pipelines available for execution."""
    return [
        {
            "id": "live_prediction",
            "name": "Live Bar Traffic Prediction",
            "description": (
                "Full real-time causal pipeline: "
                "Raw Sources → Context Inference → Bar Intent → Features → ML Model"
            ),
            "nodes": [
                "weather", "sports", "calendar", "events", "popular_times", "greek_life",
                "greek_social_ctx", "game_day_ctx", "specials_clock", "academic_pressure",
                "sallys_intent", "blarneys_intent", "kk_intent",
                "feature_extractor", "predictor",
            ],
        },
        {
            "id": "signals_only",
            "name": "Signal Aggregation Only",
            "description": "Collect all live signals without running predictions",
            "nodes": [
                "weather", "sports", "calendar", "events", "popular_times", "greek_life",
                "greek_social_ctx", "game_day_ctx", "specials_clock", "academic_pressure",
            ],
        },
    ]


@router.get("/topology")
def get_pipeline_topology() -> dict:
    """Return the full semantic DAG topology with causal edge labels and story paths.

    The topology describes five layers:
      0  Raw Sources    — live data providers (weather, sports, calendar, greek_life, events)
      1  Context Nodes  — cross-signal inference (game day dynamics, Greek social context, etc.)
      2  Bar Intent     — bar-specific demand aggregation (Sally's, Blarney's, KK)
      3  Features       — unified feature vector for ML model
      4  Predictor      — RandomForest wait/occupancy predictions

    Each edge carries:
      label     — short human-readable signal name
      semantic  — full causal explanation ("why does this connection exist?")
      story     — list of story IDs this edge participates in
      type      — "data" | "causal_inference" | "passthrough"
      weight    — "high" | "medium" | "low"
    """
    nodes = [
        # ── Layer 0: Raw Sources ──────────────────────────────────────────────
        {
            "id": "weather", "label": "Weather", "layer": 0, "type": "raw",
            "source": "Open-Meteo API",
            "signals": ["temperature_c", "precipitation_mm", "wind_speed_ms", "cloud_cover", "is_severe_weather"],
            "description": "Real-time Minneapolis weather from Open-Meteo (free, no key). Cached 10 min.",
            "color": "cyan",
        },
        {
            "id": "sports", "label": "Sports", "layer": 0, "type": "raw",
            "source": "ESPN unofficial API",
            "signals": ["is_football_home", "is_basketball_home", "hours_until_game", "is_rivalry_game", "is_nfl_game_day"],
            "description": "UMN home game schedule + TV sports (NFL, CFB, March Madness) from ESPN.",
            "color": "cyan",
        },
        {
            "id": "calendar", "label": "Academic Calendar", "layer": 0, "type": "raw",
            "source": "Static + computed",
            "signals": ["classes_in_session", "is_finals_week", "is_welcome_week", "week_of_semester", "days_until_break"],
            "description": "UMN semester schedule: finals, welcome week, breaks, midterms. Updated annually.",
            "color": "cyan",
        },
        {
            "id": "greek_life", "label": "Greek Life", "layer": 0, "type": "raw",
            "source": "Computed (FSL calendar)",
            "signals": ["is_greek_formal_season", "is_greek_bid_day", "is_greek_thursday", "greek_social_intensity"],
            "description": "IFC (24 chapters) + PHC (13 sororities) + NPHC social calendar. ~3,000 members.",
            "color": "cyan",
        },
        {
            "id": "events", "label": "Local Events", "layer": 0, "type": "raw",
            "source": "SeatGeek API",
            "signals": ["nearby_events_count", "event_type", "event_capacity"],
            "description": "Concerts, sporting events, and venues near UMN bars from SeatGeek.",
            "color": "cyan",
        },
        {
            "id": "popular_times", "label": "Popular Times", "layer": 0, "type": "raw",
            "source": "Google Places",
            "signals": ["busyness_score", "current_popularity"],
            "description": "Google Popular Times baseline busyness heuristic for each bar.",
            "color": "cyan",
        },

        # ── Layer 1: Context Inference ────────────────────────────────────────
        {
            "id": "greek_social_ctx", "label": "Greek Social Context", "layer": 1, "type": "context",
            "signals": ["date_party_tonight", "sallys_pregame_boost", "kk_after_party_draw", "blarneys_greek_draw", "greek_social_driver"],
            "description": (
                "Infers whether a date party / formal is happening tonight and models the full "
                "causal chain: formal season + Thu/Fri/Sat → date_party_tonight → Sally's "
                "pre-game surge 3-6 PM (cheap HH before event) → KK after-party 10 PM+."
            ),
            "color": "purple",
        },
        {
            "id": "game_day_ctx", "label": "Game Day Context", "layer": 1, "type": "context",
            "signals": ["pregame_bar_draw", "post_game_migration", "blarneys_postgame_boost", "tv_anchor_strength", "game_day_mood"],
            "description": (
                "Models three crowd patterns: pre-game bar draw (fans drink 1-3 hrs before kickoff), "
                "post-game migration into Dinkytown, and TV sports anchor (big games keep people at bars)."
            ),
            "color": "purple",
        },
        {
            "id": "specials_clock", "label": "Specials Clock", "layer": 1, "type": "context",
            "signals": ["sallys_happy_hour_active", "blarneys_karaoke_thursday", "kk_tuesday_special", "kk_thursday_special", "active_deals_count"],
            "description": (
                "Real-time deal status per bar based on BAR_SCHEDULES × current time. "
                "Tells each bar intent node exactly which cheap-drink windows are open right now."
            ),
            "color": "purple",
        },
        {
            "id": "academic_pressure", "label": "Academic Pressure", "layer": 1, "type": "context",
            "signals": ["social_mode_score", "semester_phase", "finals_suppression", "pre_break_surge", "thirsty_thursday_factor"],
            "description": (
                "Converts raw academic flags into a social_mode_score (0=finals crunch, 1=welcome week). "
                "Finals suppression (0.30×) kills traffic; pre-break surge adds +35% two days before break."
            ),
            "color": "purple",
        },

        # ── Layer 2: Bar Intent ───────────────────────────────────────────────
        {
            "id": "sallys_intent", "label": "Sally's Intent", "layer": 2, "type": "intent",
            "bar": "sallys", "bar_id": 2,
            "signals": ["sallys_demand_multiplier", "sallys_primary_driver", "sallys_greek_contribution", "sallys_expected_peak"],
            "description": (
                "Aggregates Sally's Saloon demand. Key story: date party tonight + happy hour active (3-6 PM) "
                "= Greeks pre-gaming before event → biggest Sally's signal on formal nights. "
                "Also: $2 Tuesday student draw, football foot traffic (Stadium Village)."
            ),
            "color": "amber",
        },
        {
            "id": "blarneys_intent", "label": "Blarney's Intent", "layer": 2, "type": "intent",
            "bar": "blarneys", "bar_id": 1,
            "signals": ["blarneys_demand_multiplier", "blarneys_primary_driver", "blarneys_karaoke_boost", "blarneys_postgame_boost"],
            "description": (
                "Aggregates Blarney's Pub demand. Post-game migration into Dinkytown is the biggest driver on "
                "home game days. Karaoke Thursday (+55%) is the biggest weekly special. "
                "Greek proximity 0.75× provides a consistent baseline."
            ),
            "color": "amber",
        },
        {
            "id": "kk_intent", "label": "KK Intent", "layer": 2, "type": "intent",
            "bar": "kk", "bar_id": 3,
            "signals": ["kk_demand_multiplier", "kk_primary_driver", "kk_after_party_draw", "kk_tue_boost", "kk_expected_peak_hour"],
            "description": (
                "Aggregates Kollege Klub demand. KK is the primary Greek destination (0.90× proximity). "
                "After-party draw 10 PM+ on formal nights is a massive signal. "
                "KK Tuesday (+70%) and KK Thursday (+40%) are campus institutions."
            ),
            "color": "amber",
        },

        # ── Layer 3: Features ─────────────────────────────────────────────────
        {
            "id": "feature_extractor", "label": "Feature Extractor", "layer": 3, "type": "ml",
            "signals": ["68 features", "hour_cos", "classes_in_session", "is_break"],
            "description": "Builds the 68-feature vector from all upstream signals. Top features: hour_cos, classes_in_session, is_break, wind_speed_ms, cloud_cover.",
            "color": "green",
        },

        # ── Layer 4: Output ───────────────────────────────────────────────────
        {
            "id": "predictor", "label": "Predictor", "layer": 4, "type": "output",
            "signals": ["wait_minutes", "pct_full", "drink_wait_minutes"],
            "description": "RandomForest model (WaitTimeModel) trained on 60 days of synthetic observations. Predicts wait time, % full, and drink wait for each bar.",
            "color": "green",
        },
    ]

    edges = [
        # ── Raw → Context ─────────────────────────────────────────────────────
        {"from": "weather",    "to": "game_day_ctx",      "label": "temp · precip · wind",
         "semantic": "Weather shifts crowd indoor/outdoor behavior. Severe cold/weather pushes people inside (bars).",
         "story": ["game_day"], "type": "data", "weight": "medium"},
        {"from": "sports",     "to": "game_day_ctx",      "label": "UMN home games · TV schedule",
         "semantic": "Home game schedule determines pregame bar draw and post-game migration timing.",
         "story": ["game_day"], "type": "data", "weight": "high"},
        {"from": "calendar",   "to": "game_day_ctx",      "label": "academic gating",
         "semantic": "Game attendance patterns vary by semester phase (welcome week vs finals).",
         "story": ["game_day"], "type": "data", "weight": "low"},
        {"from": "greek_life", "to": "greek_social_ctx",  "label": "formal season · bid days · rush",
         "semantic": "Greek social calendar: formal season Oct-Nov/Mar-Apr, bid days, Greek Thursday, rush week suppression.",
         "story": ["date_party"], "type": "data", "weight": "high"},
        {"from": "calendar",   "to": "greek_social_ctx",  "label": "semester phase gating",
         "semantic": "Greek events only occur during active semester. Rush week suppresses general bar traffic.",
         "story": ["date_party"], "type": "data", "weight": "medium"},
        {"from": "calendar",   "to": "specials_clock",    "label": "day of week · time",
         "semantic": "Which bar specials are active is entirely determined by day of week and current hour.",
         "story": ["date_party", "kk_tuesday"], "type": "data", "weight": "high"},
        {"from": "calendar",   "to": "academic_pressure", "label": "finals · welcome week · breaks",
         "semantic": "Academic calendar determines student social mode (0=finals crunch, 1=welcome week).",
         "story": ["finals"], "type": "data", "weight": "high"},

        # ── Context → Bar Intent ──────────────────────────────────────────────

        # Sally's — the date party pregame story
        {"from": "greek_social_ctx", "to": "sallys_intent", "label": "pre-party HH push 3-6 PM",
         "semantic": (
             "DATE PARTY STORY: Date parties start 9-10 PM. Greek members pregame at Sally's "
             "Happy Hour (3-6 PM) for cheap drinks before the event. "
             "Sally's proximity to Greek row: 0.45×. When formal season + HH active + date party tonight: "
             "greek_pregame_contribution = sallys_pregame_boost × 1.4."
         ),
         "story": ["date_party"], "type": "causal_inference", "weight": "high"},
        {"from": "specials_clock",   "to": "sallys_intent", "label": "happy hour · late HH · $2 Tue",
         "semantic": "Sally's 3-6 PM happy hour, 10 PM-midnight late HH, and $2 Tuesday all drive distinct demand spikes.",
         "story": ["date_party", "kk_tuesday"], "type": "data", "weight": "high"},
        {"from": "academic_pressure","to": "sallys_intent", "label": "student social mode",
         "semantic": "Finals suppression (0.30×) kills Sally's traffic. Welcome week (0.90 mode) drives max turnout.",
         "story": ["finals"], "type": "data", "weight": "medium"},
        {"from": "game_day_ctx",     "to": "sallys_intent", "label": "football foot traffic",
         "semantic": "Stadium Village gets pre-game foot traffic from fans walking to TCF Bank Stadium. UMN football only.",
         "story": ["game_day"], "type": "causal_inference", "weight": "medium"},
        {"from": "weather",          "to": "sallys_intent", "label": "patio weather boost",
         "semantic": "Sally's has outdoor patio space in Stadium Village. Nice days (15-28°C, 2-8 PM) add +15% demand.",
         "story": [], "type": "data", "weight": "low"},

        # Blarney's
        {"from": "game_day_ctx",     "to": "blarneys_intent", "label": "post-game migration into Dinkytown",
         "semantic": (
             "GAME DAY STORY: After UMN home games, crowds migrate north into Dinkytown. "
             "Blarney's is the first major bar they hit. Post-game migration × 0.75 = blarneys_postgame_boost. "
             "Rivalry games get a 1.5× multiplier."
         ),
         "story": ["game_day"], "type": "causal_inference", "weight": "high"},
        {"from": "greek_social_ctx", "to": "blarneys_intent", "label": "Greek row proximity (0.75×)",
         "semantic": "Blarney's is 0.2 mi from Phi Gam, Chi Psi, and other Greek houses in Dinkytown. Consistent Greek spillover.",
         "story": ["date_party"], "type": "data", "weight": "medium"},
        {"from": "specials_clock",   "to": "blarneys_intent", "label": "karaoke Thu +55% · HH 3:17 PM",
         "semantic": "Karaoke Thursday (9 PM - 2 AM) is the biggest Blarney's night. Their HH starts at 3:17 PM (their quirky signature time).",
         "story": [], "type": "data", "weight": "high"},
        {"from": "academic_pressure","to": "blarneys_intent", "label": "social baseline · finals kill",
         "semantic": "Social mode sets the Dinkytown baseline. Finals suppression hits Blarney's hard — it depends on discretionary going-out.",
         "story": ["finals"], "type": "data", "weight": "medium"},

        # KK
        {"from": "greek_social_ctx", "to": "kk_intent",     "label": "primary Greek dest (0.90×) · after-party draw",
         "semantic": (
             "DATE PARTY STORY (continued): KK is THE primary Greek destination at UMN — adjacent to Greek row "
             "(0.90× proximity). After-party draw 10 PM+: kk_after_party_draw = 0.80 × 0.90 = 0.72 when "
             "date party tonight + after midnight. Bid day = biggest KK night of the semester."
         ),
         "story": ["date_party"], "type": "causal_inference", "weight": "high"},
        {"from": "specials_clock",   "to": "kk_intent",     "label": "KK Tue +70% · KK Thu +40%",
         "semantic": "KK Tuesday (9 PM - 2 AM, +70%) and KK Thursday (9 PM - 2 AM, +40%) are campus institutions. When Greek Thursday overlaps KK Thursday, thu_boost × 1.25.",
         "story": ["kk_tuesday"], "type": "data", "weight": "high"},
        {"from": "academic_pressure","to": "kk_intent",     "label": "semester social cycle",
         "semantic": "Greek social patterns are tightly linked to semester phase. Mid-semester peak (weeks 3-8) = KK's busiest baseline period.",
         "story": ["finals"], "type": "data", "weight": "medium"},

        # ── Bar Intent → Feature Extractor ────────────────────────────────────
        {"from": "sallys_intent",    "to": "feature_extractor", "label": "Sally's demand vector",
         "semantic": "sallys_demand_multiplier, primary_driver, greek_contribution, deal_boost feed into the feature matrix.",
         "story": ["date_party", "game_day", "finals", "kk_tuesday"], "type": "data", "weight": "high"},
        {"from": "blarneys_intent",  "to": "feature_extractor", "label": "Blarney's demand vector",
         "semantic": "blarneys_demand_multiplier, karaoke_boost, postgame_boost feed into feature matrix.",
         "story": ["date_party", "game_day", "finals"], "type": "data", "weight": "high"},
        {"from": "kk_intent",        "to": "feature_extractor", "label": "KK demand vector",
         "semantic": "kk_demand_multiplier, after_party_draw, tue/thu_boost, greek_baseline feed into feature matrix.",
         "story": ["date_party", "finals", "kk_tuesday"], "type": "data", "weight": "high"},

        # ── Raw → Feature (numeric pass-through) ─────────────────────────────
        {"from": "weather",       "to": "feature_extractor", "label": "raw weather features",
         "semantic": "temperature_c, precipitation_mm, wind_speed_ms, cloud_cover, is_severe_weather passed directly to ML model.",
         "story": [], "type": "passthrough", "weight": "medium"},
        {"from": "sports",        "to": "feature_extractor", "label": "raw sports flags",
         "semantic": "is_football_home, hours_until_game, tv_game_weight passed directly as numeric features.",
         "story": [], "type": "passthrough", "weight": "medium"},
        {"from": "events",        "to": "feature_extractor", "label": "local events (SeatGeek)",
         "semantic": "Nearby event count and capacity signal baseline crowd draw in the neighborhood.",
         "story": [], "type": "passthrough", "weight": "low"},
        {"from": "popular_times", "to": "feature_extractor", "label": "Google baseline busyness",
         "semantic": "Popular Times busyness score provides a time-of-week baseline independent of special events.",
         "story": [], "type": "passthrough", "weight": "low"},

        # ── Feature → Predictor ───────────────────────────────────────────────
        {"from": "feature_extractor", "to": "predictor",     "label": "68-feature vector",
         "semantic": "Full feature matrix including time features (hour_cos, dow_sin), signal features, and bar intent demand vectors.",
         "story": ["date_party", "game_day", "finals", "kk_tuesday"], "type": "data", "weight": "high"},
    ]

    stories = [
        {
            "id": "date_party",
            "name": "Date Party Night",
            "color": "#f472b6",
            "description": "Greek formal season → date parties → early Sally's surge (3-6 PM) → KK after-party (10 PM+)",
            "nodes": ["greek_life", "calendar", "greek_social_ctx", "specials_clock", "sallys_intent", "kk_intent", "feature_extractor", "predictor"],
            "narrative": (
                "Oct-Nov & Mar-Apr is Greek formal season. Date parties start at 9-10 PM. "
                "Before the event, Greek members pre-game at Sally's 3-6 PM Happy Hour — "
                "cheap drinks ($3 domestic) vs $8+ at the venue. "
                "By 10 PM they migrate to KK, the primary Greek destination (0.90× proximity). "
                "Tonight signal: date_party_tonight → sallys_pregame_boost → kk_after_party_draw."
            ),
        },
        {
            "id": "game_day",
            "name": "Game Day",
            "color": "#fb923c",
            "description": "UMN home game → Stadium Village pre-game surge → post-game Dinkytown migration",
            "nodes": ["weather", "sports", "calendar", "game_day_ctx", "sallys_intent", "blarneys_intent", "feature_extractor", "predictor"],
            "narrative": (
                "Home football games create two waves: (1) fans walk through Stadium Village before kickoff "
                "→ Sally's surge 2-4 hrs pre-game. (2) After the game, crowds stream north into Dinkytown "
                "→ Blarney's post-game migration. Rivalry games get a 1.5× multiplier on both. "
                "TV sports (NFL Sunday, CFB Saturday) anchor people at bars all afternoon."
            ),
        },
        {
            "id": "kk_tuesday",
            "name": "KK Tuesday",
            "color": "#e8a020",
            "description": "KK Tuesday institution: 9 PM - 2 AM, +70% boost every Tuesday",
            "nodes": ["calendar", "specials_clock", "academic_pressure", "kk_intent", "feature_extractor", "predictor"],
            "narrative": (
                "KK Tuesday is a campus institution — has been since the 1990s. "
                "9 PM - 2 AM every Tuesday, +70% traffic boost. "
                "Mid-semester (weeks 3-8) social mode peaks at 0.80, making this the "
                "busiest non-Greek-event night of the week. "
                "KK Thursday (+40%) is also an institution, and when Greek Thursday overlaps → thu_boost × 1.25."
            ),
        },
        {
            "id": "finals",
            "name": "Finals Week",
            "color": "#60a5fa",
            "description": "Academic pressure suppresses all bar traffic — finals_suppression = 0.30×",
            "nodes": ["calendar", "academic_pressure", "sallys_intent", "blarneys_intent", "kk_intent", "feature_extractor", "predictor"],
            "narrative": (
                "Finals suppression: social_mode_score drops to 0.15, finals_suppression = 0.30×. "
                "Every bar intent node's total demand gets multiplied down. "
                "Exception: the day BEFORE finals (study days) still sees a surge — 'last night out' effect. "
                "Pre-break surge: +35% two days before semester break starts. "
                "Welcome week (0.90 social mode) is the inverse — maximum traffic."
            ),
        },
    ]

    return {
        "layers": [
            {"id": 0, "label": "RAW SOURCES",       "description": "Live data providers — no computation"},
            {"id": 1, "label": "CONTEXT INFERENCE", "description": "Cross-signal causal reasoning"},
            {"id": 2, "label": "BAR INTENT",        "description": "Bar-specific demand aggregation"},
            {"id": 3, "label": "FEATURES",          "description": "ML feature vector construction"},
            {"id": 4, "label": "PREDICTOR",         "description": "RandomForest output"},
        ],
        "nodes":   nodes,
        "edges":   edges,
        "stories": stories,
        "metadata": {
            "total_nodes":     len(nodes),
            "total_edges":     len(edges),
            "causal_edges":    sum(1 for e in edges if e["type"] == "causal_inference"),
            "total_signals":   68,
        },
    }

# CLAUDE.md — UMN Bar Traffic + Open Foundry Platform

## Project Overview
A Palantir Foundry-style data pipeline platform for predicting bar traffic at Blarney's, Sally's, and Kollege Klub near UMN. The existing ML models and feature engineering are wrapped by a FastAPI platform backend that ingests real data from live sources.

## Existing ML System (DO NOT MODIFY without approval)
- `config/settings.py` — bars config, BAR_SCHEDULES, model params
- `data/db.py` — SQLite helpers (get_connection, init_db)
- `providers/weather.py` — Open-Meteo live weather (fetch_current_weather)
- `providers/sports.py` — ESPN live sports (fetch_umn_games, fetch_tv_sports)
- `providers/calendar.py` — UMN academic calendar (compute_academic_flags, compute_event_flags)
- `features/builder.py` — FeatureBuilder class (TIME_FEATURES + SIGNAL_FEATURES)
- `models/baseline.py` — BaselineModel (median fallback)
- `models/ml_model.py` — WaitTimeModel (RandomForest)
- `models/train.py` — run_training() returns {"wait": (BaselineModel, WaitTimeModel), "df_feat": df, ...}

## NEW: Real Data Providers
- `providers/events.py` — SeatGeek API + UMN Events (local events near bars)
- `providers/popular_times.py` — Google Popular Times busyness baseline

## NEW: Platform Layer (Palantir-style)
- `platform/backend/main.py` — FastAPI app (run: uvicorn platform.backend.main:app --reload --port 8001)
- `platform/backend/schemas.py` — Pydantic models (PredictionResult, LiveSignals, etc.)
- `platform/backend/engine/dag.py` — DAG topological sort
- `platform/backend/engine/executor.py` — Node-by-node pipeline execution
- `platform/backend/engine/nodes/data_source.py` — WeatherNode, SportsNode, CalendarNode, EventsNode, PopularTimesNode
- `platform/backend/engine/nodes/feature_node.py` — FeatureExtractorNode (wraps features/builder.py)
- `platform/backend/engine/nodes/predictor_node.py` — PredictorNode (wraps models/)
- `platform/backend/api/predict.py` — GET /api/v1/predict/all, /api/v1/predict/{bar_id}
- `platform/backend/api/signals.py` — GET /api/v1/signals/live
- `platform/backend/api/pipeline.py` — POST /api/v1/pipeline/run, GET /api/v1/pipeline/definitions

## Standard Pipeline: DataSource → Features → Predictor
```
WeatherNode ──┐
SportsNode ───┤
CalendarNode ─┼──► FeatureExtractorNode ──► PredictorNode
EventsNode ───┤
PopularTimesNode┘
```

## Tech Stack
- Existing: Python 3.9+, Streamlit, pandas, scikit-learn, SQLite, requests
- New platform: FastAPI, Pydantic v2, uvicorn
- Real data: Open-Meteo (weather), ESPN (sports), SeatGeek (events), Google Places (popular times)

## Run commands
1. `python -m data.seed` — populate DB with synthetic data
2. `streamlit run app/dashboard.py` — Streamlit dashboard (port 8501)
3. `uvicorn platform.backend.main:app --reload --port 8001` — FastAPI platform (port 8001)

## Architecture Rules
1. NEVER modify models/ or features/ without explicit approval
2. Platform nodes CALL existing code — never duplicate prediction logic
3. All new data providers go in providers/
4. Platform backend lives entirely in platform/ — zero overlap with existing code
5. Degrade gracefully: every provider must return safe defaults on network failure
6. Cache aggressively: provider data changes slowly (weather=10min, sports=1hr, events=1hr)

## Important API notes
- `models/train.py` exports `run_training()` — returns dict with "wait", "pct_full", "drink" keys
  Each key maps to a (BaselineModel, WaitTimeModel) tuple, plus "df_feat" DataFrame
- `BaselineModel.predict_one(bar_id, day_of_week, hour)` — takes int args, NOT a datetime
- `WaitTimeModel.predict_one(feature_dict)` — dict must cover model.feature_cols
- There are NO standalone `_apply_holiday_weights` or `_get_feature_cols` functions
  (that logic is inlined in run_training())

## HARD RULES
- Do NOT add imports that create circular dependencies (platform → models is fine, models → platform is not)
- Provider functions must return dicts with consistent key names
- All API responses use Pydantic models
- BaselineModel.predict_one takes (bar_id: int, day_of_week: int, hour: int) — not a datetime

# UMN Bar Traffic Algo

Predicts wait times at **Blarney's**, **Sally's**, and **Kollege Klub** near the University of Minnesota. Combines a RandomForest ML model with live data from weather, sports, academic calendar, and local events — all wrapped in a Palantir Foundry-style pipeline API and a real-time dashboard.

---

## Architecture

```
providers/          Real data (weather, sports, calendar, events, popular times)
features/           Feature engineering (time + signal features → 68 columns)
models/             Baseline (median) + ML (RandomForest) models
platform/           FastAPI backend — DAG execution engine + REST API
frontend/           Crowd Intel dashboard (HTML/CSS/JS)
app/                Legacy Streamlit dashboard
data/               SQLite DB, schema, synthetic data seeder
config/             Central config (bars, schedules, model params)
```

### Pipeline DAG

```
WeatherNode ──┐
SportsNode ───┤
CalendarNode ─┼──► FeatureExtractorNode ──► PredictorNode
EventsNode ───┤
PopularTimesNode┘
```

Each pipeline run fetches live signals, assembles per-bar feature vectors, and produces ML predictions with baseline fallback.

---

## Quick Start

```bash
# 1. Create virtualenv and install deps
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Seed DB with synthetic data
python -m data.seed

# 3. Start the API backend  (terminal 1)
python -m uvicorn platform.backend.main:app --reload --port 8001

# 4. Start the frontend     (terminal 2)
python -m http.server 3000 --directory frontend
```

Open **http://localhost:3000** for the Crowd Intel dashboard.
Open **http://localhost:8001/docs** for the interactive API docs.

> **Note:** Use `python -m uvicorn`, not bare `uvicorn`. The `platform/` package
> name shadows Python's stdlib `platform` module; `python -m uvicorn` adds CWD
> to `sys.path` first and resolves the conflict.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/predict/all` | Predictions for all 3 bars |
| `GET` | `/api/v1/predict/{bar_id}` | Prediction for one bar |
| `GET` | `/api/v1/signals/live` | All live signals aggregated |
| `POST` | `/api/v1/pipeline/run` | Run a custom pipeline DAG |
| `GET` | `/api/v1/pipeline/definitions` | List built-in pipelines |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Example response — `GET /api/v1/predict/all`

```json
[
  {
    "bar_id": 3,
    "bar_name": "Kollege Klub",
    "predicted_wait_minutes": 35.7,
    "predicted_pct_full": 0.794,
    "confidence": "high",
    "model_used": "ml",
    "signals_used": {}
  }
]
```

---

## Data Sources

| Source | Provider | Key |
|--------|----------|-----|
| Weather | [Open-Meteo](https://open-meteo.com/) | None required |
| UMN + TV sports | ESPN (unofficial) | None required |
| Academic calendar | Hardcoded semester dates | — |
| Local events | SeatGeek API | None for basic queries |
| Popular times baseline | Google Places API | Optional (`GOOGLE_PLACES_API_KEY`) |

All providers degrade gracefully — safe defaults are returned on network failure. Results are cached in-memory (weather: 10 min, sports/events: 1 hr).

---

## Bars

| ID | Name | Notable nights |
|----|------|----------------|
| 1 | Blarney's Pub and Grill | Karaoke Thu (+55%), Thirsty Wed (+25%) |
| 2 | Sally's Saloon | $2 Tuesday (+30%), Late HH nightly 10pm–midnight (+20%) |
| 3 | Kollege Klub | KK Tuesday (+70%), KK Thursday (+40%), Friday After Class (+35%) |

---

## Feature Engineering

68 features across six groups:

- **Time** — hour, day_of_week, cyclical sin/cos encodings, is_weekend, is_late_night
- **Weather** — temperature, wind chill, precipitation, snowfall, cloud cover, severe weather flag
- **Athletics** — Gophers football/basketball/hockey home games, rivalry flag, hours until game
- **TV sports** — NFL, Vikings, CFB, March Madness, NBA/NHL playoffs, weighted TV game signal
- **Academic** — classes in session, finals/midterms/welcome week, days until break, semester week
- **Events** — St. Patrick's, Halloween, homecoming, bar crawl, Blackout Wednesday, drinking holiday weight

---

## Models

**Baseline** — median wait time by `(bar_id, day_of_week, hour)` with 3-level cascade fallback.

**ML** — `RandomForestRegressor` trained on a time-based split (last 14 days held out). Holiday rows are up-weighted 10× during training. The platform calls `run_training()` once per pipeline execution and reuses the fitted model across all bars.

---

## Project Structure

```
umn-bar-traffic-algo/
├── frontend/
│   └── index.html                  # Crowd Intel dashboard
├── platform/
│   └── backend/
│       ├── main.py                 # FastAPI app
│       ├── schemas.py              # Pydantic models
│       ├── api/                    # predict, signals, pipeline routers
│       └── engine/                 # DAG, executor, nodes
├── providers/
│   ├── weather.py                  # Open-Meteo
│   ├── sports.py                   # ESPN
│   ├── calendar.py                 # UMN academic calendar
│   ├── events.py                   # SeatGeek + UMN Events
│   └── popular_times.py            # Google Places / calibrated fallback
├── features/
│   └── builder.py                  # FeatureBuilder
├── models/
│   ├── baseline.py                 # BaselineModel
│   ├── ml_model.py                 # WaitTimeModel (RandomForest)
│   └── train.py                    # run_training()
├── data/
│   ├── schema.sql
│   ├── db.py
│   └── seed.py
├── config/
│   └── settings.py                 # BARS, BAR_SCHEDULES, model params
└── app/
    └── dashboard.py                # Legacy Streamlit dashboard
```

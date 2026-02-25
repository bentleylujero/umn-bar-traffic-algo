# UMN Bar Line Forecasting Dashboard

Predicts wait times at bars near the University of Minnesota using historical observations, weather data, and machine learning.

---

## Project structure

```
umn-bar-traffic-algo/
├── app/
│   └── dashboard.py        # Streamlit dashboard (entry point)
├── config/
│   └── settings.py         # Central config (paths, bar list, model params)
├── data/
│   ├── schema.sql          # SQLite table definitions
│   ├── db.py               # Connection helper + schema init
│   └── seed.py             # Synthetic data generator (dev/demo)
├── features/
│   └── builder.py          # Time features + optional lag features
├── models/
│   ├── baseline.py         # Median wait by (bar, day_of_week, hour)
│   ├── ml_model.py         # RandomForest regressor (time-split eval)
│   └── train.py            # Full training pipeline
├── providers/
│   └── weather.py          # Open-Meteo weather fetcher (no API key needed)
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Seed the database with synthetic data

```bash
python -m data.seed
```

This writes 60 days of synthetic observations for 5 Dinkytown bars into `data/bar_traffic.db`.

### 4. (Optional) Verify model training

```bash
python -m models.train
```

### 5. Launch the dashboard

```bash
streamlit run app/dashboard.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Adding real observations

Insert rows directly via SQLite or write a collection script:

```python
from data.db import get_connection

conn = get_connection()
with conn:
    conn.execute(
        "INSERT INTO observations (bar_id, observed_at, wait_minutes) VALUES (?,?,?)",
        (1, "2026-02-25T22:00:00+00:00", 12.0),
    )
conn.close()
```

---

## Database schema

| Table        | Key columns                                           |
|--------------|-------------------------------------------------------|
| `bars`       | `id`, `name`, `neighborhood`                          |
| `observations` | `bar_id`, `observed_at`, `wait_minutes`, `cover_charge` |
| `signals`    | `observation_id`, `temperature_c`, `precipitation_mm`, `is_game_day`, `is_holiday` |

---

## Configuration

Edit `config/settings.py` to:
- Add/remove bars (`BARS` list)
- Change the train/test split window (`TEST_SPLIT_DAYS`)
- Tune the RandomForest (`RF_N_ESTIMATORS`, `RF_MAX_DEPTH`)
- Adjust the location for weather fetching (`LATITUDE`, `LONGITUDE`)

---

## Weather data

Weather is fetched from [Open-Meteo](https://open-meteo.com/) — free, no API key required. Results are cached in-memory for 10 minutes.

---

## Extending the model

### Adding lag features

```python
from features.builder import FeatureBuilder

fb = FeatureBuilder(add_lag_features=True, lag_hours=[1, 2, 4, 168])
df = fb.build(df_raw)
```

### Swapping in a different regressor

Replace `RandomForestRegressor` in `models/ml_model.py` with any scikit-learn compatible estimator.

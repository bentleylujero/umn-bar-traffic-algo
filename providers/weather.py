"""Weather provider — fetches temperature & precipitation from Open-Meteo.

Open-Meteo is free and requires no API key.
Docs: https://open-meteo.com/en/docs

WMO weather codes used for is_severe_weather:
  75-77 : heavy snowfall / snow grains
  82    : heavy rain showers
  85-86 : heavy snow showers
  95-99 : thunderstorms
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from config.settings import LATITUDE, LONGITUDE, WEATHER_BASE_URL

log = logging.getLogger(__name__)

# How long to cache a response (seconds) — avoids hammering the API
_CACHE_TTL = 600  # 10 minutes
_cache: dict[str, tuple[float, dict]] = {}  # key → (timestamp, payload)

# WMO codes that indicate severe weather for bar-traffic purposes
_SEVERE_CODES = {75, 77, 82, 85, 86, 95, 96, 99}


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, payload = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            return payload
    return None


def _cache_set(key: str, payload: dict) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), payload)


def _is_severe(code: Optional[int]) -> int:
    return int(code in _SEVERE_CODES) if code is not None else 0


def _is_first_nice_day(temp_c: Optional[float]) -> int:
    """Heuristic: warm spring emergence day in Minneapolis (Feb–Apr, temp >= 10 °C)."""
    if temp_c is None:
        return 0
    now = datetime.now(timezone.utc)
    return int(now.month in (2, 3, 4) and temp_c >= 10.0)


def fetch_current_weather(
    lat: float = LATITUDE,
    lon: float = LONGITUDE,
) -> dict:
    """Return current weather conditions for a location.

    Returns
    -------
    dict with keys:
        temperature_c     : float
        precipitation_mm  : float
        wind_chill_c      : float   (apparent/feels-like temperature)
        snowfall_mm       : float   (snowfall in last hour)
        wind_speed_ms     : float   (wind speed in m/s)
        is_severe_weather : int     (0 or 1)
        cloud_cover       : float   (% cloud coverage 0-100)
        is_first_nice_day : int     (0 or 1)
        fetched_at        : str     (ISO-8601 UTC)
    """
    cache_key = f"current_{lat}_{lon}"
    cached = _cache_get(cache_key)
    if cached:
        log.debug("Weather: cache hit")
        return cached

    params = {
        "latitude":  lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "snowfall",
            "wind_speed_10m",
            "weather_code",
            "cloud_cover",
        ],
        "wind_speed_unit": "ms",
        "timezone": "America/Chicago",
    }

    try:
        resp = requests.get(WEATHER_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data    = resp.json()
        current = data.get("current", {})
        result = {
            "temperature_c":    current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "wind_chill_c":     current.get("apparent_temperature"),
            "snowfall_mm":      _cm_to_mm(current.get("snowfall")),
            "wind_speed_ms":    current.get("wind_speed_10m"),
            "is_severe_weather": _is_severe(current.get("weather_code")),
            "cloud_cover":       current.get("cloud_cover"),
            "is_first_nice_day": _is_first_nice_day(current.get("temperature_2m")),
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        }
    except requests.RequestException as exc:
        log.warning("Weather fetch failed: %s — returning nulls", exc)
        result = {
            "temperature_c":    None,
            "precipitation_mm": None,
            "wind_chill_c":     None,
            "snowfall_mm":      None,
            "wind_speed_ms":    None,
            "is_severe_weather": 0,
            "cloud_cover":       None,
            "is_first_nice_day": 0,
            "fetched_at":       datetime.now(timezone.utc).isoformat(),
        }

    _cache_set(cache_key, result)
    return result


def fetch_hourly_forecast(
    lat: float = LATITUDE,
    lon: float = LONGITUDE,
    days: int = 1,
) -> list[dict]:
    """Return an hourly forecast for the next *days* days.

    Each item has:
        hour                     : str    (ISO-8601 local time)
        temperature_c            : float
        precipitation_mm         : float
        wind_chill_c             : float
        snowfall_mm              : float
        wind_speed_ms            : float
        is_severe_weather        : int
        cloud_cover              : float  (% cloud coverage 0-100)
        precipitation_probability: int    (% probability 0-100)
    """
    cache_key = f"forecast_{lat}_{lon}_{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached  # type: ignore[return-value]

    params = {
        "latitude":  lat,
        "longitude": lon,
        "hourly": [
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "snowfall",
            "wind_speed_10m",
            "weather_code",
            "cloud_cover",
            "precipitation_probability",
        ],
        "wind_speed_unit":  "ms",
        "forecast_days":    days,
        "timezone":         "America/Chicago",
    }

    try:
        resp = requests.get(WEATHER_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data   = resp.json()
        hourly = data.get("hourly", {})
        times         = hourly.get("time", [])
        temps         = hourly.get("temperature_2m", [])
        apparent      = hourly.get("apparent_temperature", [])
        precip        = hourly.get("precipitation", [])
        snowfall      = hourly.get("snowfall", [])
        wind_speed    = hourly.get("wind_speed_10m", [])
        weather_codes = hourly.get("weather_code", [])
        cloud_cover   = hourly.get("cloud_cover", [])
        precip_prob   = hourly.get("precipitation_probability", [])

        result = [
            {
                "hour":                      t,
                "temperature_c":             temp,
                "precipitation_mm":          prec,
                "wind_chill_c":              app,
                "snowfall_mm":               _cm_to_mm(snow),
                "wind_speed_ms":             ws,
                "is_severe_weather":         _is_severe(code),
                "cloud_cover":               cc,
                "precipitation_probability": pp,
            }
            for t, temp, app, prec, snow, ws, code, cc, pp in zip(
                times, temps, apparent, precip, snowfall, wind_speed, weather_codes,
                cloud_cover or ([None] * len(times)),
                precip_prob  or ([None] * len(times)),
            )
        ]
    except requests.RequestException as exc:
        log.warning("Hourly forecast fetch failed: %s", exc)
        result = []

    _cache_set(cache_key, result)
    return result


def _cm_to_mm(value: Optional[float]) -> Optional[float]:
    """Open-Meteo returns snowfall in cm; convert to mm."""
    return round(value * 10, 1) if value is not None else None

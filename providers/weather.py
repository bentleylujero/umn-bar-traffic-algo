"""Weather provider — fetches temperature & precipitation from Open-Meteo.

Open-Meteo is free and requires no API key.
Docs: https://open-meteo.com/en/docs
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


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, payload = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            return payload
    return None


def _cache_set(key: str, payload: dict) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), payload)


def fetch_current_weather(
    lat: float = LATITUDE,
    lon: float = LONGITUDE,
) -> dict:
    """Return current temperature (°C) and precipitation (mm/h) for a location.

    Returns
    -------
    dict with keys:
        temperature_c  : float
        precipitation_mm : float
        fetched_at     : str  (ISO-8601 UTC)
    """
    cache_key = f"current_{lat}_{lon}"
    cached = _cache_get(cache_key)
    if cached:
        log.debug("Weather: cache hit")
        return cached

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "precipitation"],
        "timezone": "America/Chicago",
    }

    try:
        resp = requests.get(WEATHER_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        result = {
            "temperature_c": current.get("temperature_2m"),
            "precipitation_mm": current.get("precipitation"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except requests.RequestException as exc:
        log.warning("Weather fetch failed: %s — returning nulls", exc)
        result = {
            "temperature_c": None,
            "precipitation_mm": None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
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
        hour           : str  (ISO-8601 local time)
        temperature_c  : float
        precipitation_mm : float
    """
    cache_key = f"forecast_{lat}_{lon}_{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached  # type: ignore[return-value]

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation"],
        "forecast_days": days,
        "timezone": "America/Chicago",
    }

    try:
        resp = requests.get(WEATHER_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        precip = hourly.get("precipitation", [])
        result = [
            {
                "hour": t,
                "temperature_c": temp,
                "precipitation_mm": prec,
            }
            for t, temp, prec in zip(times, temps, precip)
        ]
    except requests.RequestException as exc:
        log.warning("Hourly forecast fetch failed: %s", exc)
        result = []

    _cache_set(cache_key, result)
    return result

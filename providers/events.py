"""Local events provider — SeatGeek public API + UMN Events calendar.

SeatGeek endpoint (no API key required for basic queries):
  https://api.seatgeek.com/2/events?lat=44.9778&lon=-93.2650&range=3mi
  &per_page=25&datetime_local.gte={date}T00:00:00&datetime_local.lte={date}T23:59:59

UMN Events endpoint (public, no key):
  https://events.umn.edu/api/2/events?start={date}&end={date}&pp=20&format=json

All functions degrade gracefully on network failure.
1-hour in-process cache on all results.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

_CACHE_TTL = 3600  # 1 hour
_cache: dict[str, tuple[float, dict]] = {}

# Coordinates for the UMN / Dinkytown / Stadium Village area
_LAT = 44.9778
_LON = -93.2650

# Venue capacity threshold for "major concert" classification
_MAJOR_CONCERT_CAPACITY = 500

_SEATGEEK_BASE = "https://api.seatgeek.com/2/events"
_UMN_EVENTS_BASE = "https://events.umn.edu/api/2/events"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, payload = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            log.debug("events: cache hit for %s", key)
            return payload
    return None


def _cache_set(key: str, payload: dict) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), payload)


# ── Safe default ──────────────────────────────────────────────────────────────

def _empty_result() -> dict:
    return {
        "event_count_nearby":   0,
        "is_major_concert":     0,
        "is_umn_campus_event":  0,
        "max_event_capacity":   0,
        "event_names":          [],
    }


# ── SeatGeek fetch ────────────────────────────────────────────────────────────

def _fetch_seatgeek(target_date: date) -> list[dict]:
    """Fetch events from SeatGeek within 3 miles of UMN on target_date.

    Returns a list of raw event dicts, or [] on failure.
    """
    date_str = target_date.isoformat()
    params = {
        "lat":                     _LAT,
        "lon":                     _LON,
        "range":                   "3mi",
        "per_page":                25,
        "datetime_local.gte":      f"{date_str}T00:00:00",
        "datetime_local.lte":      f"{date_str}T23:59:59",
    }
    try:
        resp = requests.get(
            _SEATGEEK_BASE,
            params=params,
            timeout=10,
            headers={"User-Agent": "umn-bar-traffic/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("events", [])
    except Exception as exc:
        log.warning("SeatGeek fetch failed for %s: %s", target_date, exc)
        return []


def _parse_seatgeek_events(events: list[dict]) -> dict:
    """Parse raw SeatGeek event list into signal fields."""
    if not events:
        return {
            "event_count_nearby": 0,
            "is_major_concert":   0,
            "max_event_capacity": 0,
            "event_names":        [],
            "nearest_event_venue": None,
        }

    event_names: list[str] = []
    max_capacity = 0
    is_major = 0
    nearest_venue: Optional[str] = None

    for event in events:
        # Event name
        title = event.get("title") or event.get("short_title") or ""
        if title:
            event_names.append(title)

        # Venue capacity
        venue = event.get("venue") or {}
        capacity = venue.get("capacity") or 0
        if capacity > max_capacity:
            max_capacity = capacity
            nearest_venue = venue.get("name")

        # Major concert check
        category = (event.get("type") or "").lower()
        if category == "concert" and capacity > _MAJOR_CONCERT_CAPACITY:
            is_major = 1
        # Also check performers — headline acts at large venues
        for performer in event.get("performers") or []:
            if (performer.get("type") or "").lower() == "band":
                if capacity > _MAJOR_CONCERT_CAPACITY:
                    is_major = 1

    return {
        "event_count_nearby":  len(events),
        "is_major_concert":    is_major,
        "max_event_capacity":  max_capacity,
        "event_names":         event_names[:10],  # cap list length
        "nearest_event_venue": nearest_venue,
    }


# ── UMN Events fetch ──────────────────────────────────────────────────────────

def _fetch_umn_events(target_date: date) -> int:
    """Fetch UMN campus events for target_date.

    Returns 1 if any campus events found, 0 otherwise.
    Degrades gracefully to 0 on failure.
    """
    date_str = target_date.isoformat()
    params = {
        "start":  date_str,
        "end":    date_str,
        "pp":     20,
        "format": "json",
    }
    try:
        resp = requests.get(
            _UMN_EVENTS_BASE,
            params=params,
            timeout=10,
            headers={"User-Agent": "umn-bar-traffic/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        # UMN Events API returns {"events": [...]} or a top-level list
        if isinstance(data, list):
            events = data
        else:
            events = data.get("events") or data.get("data") or []
        return int(len(events) > 0)
    except Exception as exc:
        log.warning("UMN Events fetch failed for %s: %s", target_date, exc)
        return 0


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_local_events(target_date: date) -> dict:
    """Fetch and aggregate local event signals for target_date.

    Returns
    -------
    dict with keys:
        event_count_nearby   : int   — total nearby events on this date
        is_major_concert     : int   — 1 if any concert with capacity > 500
        is_umn_campus_event  : int   — 1 if any UMN campus event today
        max_event_capacity   : int   — largest venue capacity found
        event_names          : list  — up to 10 event titles
    """
    cache_key = f"events_{target_date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Fetch from both sources concurrently (sequential is fine at 1hr TTL)
    seatgeek_events = _fetch_seatgeek(target_date)
    sg_parsed = _parse_seatgeek_events(seatgeek_events)
    umn_campus = _fetch_umn_events(target_date)

    result = {
        "event_count_nearby":  sg_parsed["event_count_nearby"],
        "is_major_concert":    sg_parsed["is_major_concert"],
        "is_umn_campus_event": umn_campus,
        "max_event_capacity":  sg_parsed["max_event_capacity"],
        "event_names":         sg_parsed["event_names"],
    }

    _cache_set(cache_key, result)
    log.info(
        "events: %d nearby, major_concert=%d, umn_campus=%d",
        result["event_count_nearby"],
        result["is_major_concert"],
        result["is_umn_campus_event"],
    )
    return result

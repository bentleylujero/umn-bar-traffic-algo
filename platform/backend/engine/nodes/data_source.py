"""Data source pipeline nodes — each wraps a real data provider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class WeatherNode:
    """Fetches live weather signals from Open-Meteo."""

    node_type = "weather"

    def execute(self, config: dict, inputs: dict) -> dict:
        from providers.weather import fetch_current_weather

        return fetch_current_weather()


class SportsNode:
    """Fetches UMN + TV sports signals from ESPN."""

    node_type = "sports"

    def execute(self, config: dict, inputs: dict) -> dict:
        from datetime import date

        from providers.sports import fetch_tv_sports, fetch_umn_games

        target = config.get("date") or date.today()
        if isinstance(target, str):
            target = date.fromisoformat(target)

        umn = fetch_umn_games(target)
        tv = fetch_tv_sports(target)
        return {**umn, **tv}


class CalendarNode:
    """Computes UMN academic calendar + event flags."""

    node_type = "calendar"

    def execute(self, config: dict, inputs: dict) -> dict:
        from providers.calendar import compute_academic_flags, compute_event_flags

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        return {**compute_academic_flags(dt), **compute_event_flags(dt)}


class EventsNode:
    """Fetches local events near UMN bars from SeatGeek."""

    node_type = "events"

    def execute(self, config: dict, inputs: dict) -> dict:
        from datetime import date

        from providers.events import fetch_local_events

        target = config.get("date") or date.today()
        if isinstance(target, str):
            target = date.fromisoformat(target)

        return fetch_local_events(target)


class PopularTimesNode:
    """Fetches Google Popular Times baseline busyness for all bars."""

    node_type = "popular_times"

    def execute(self, config: dict, inputs: dict) -> dict:
        from providers.popular_times import fetch_all_popular_times

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        return fetch_all_popular_times(dt)


class GreekLifeNode:
    """Computes Greek life social calendar signals — no network calls required.

    Signals cover the full IFC (24 fraternities) + PHC (13 sororities) + NPHC
    community at UMN (~3,000 members). Key events modelled:

    - Rush week (IFC Welcome-Week informal + PHC 2-week formal recruitment)
    - Bid Day (single biggest Greek bar night each semester, ± 1 day window)
    - Formal / date-party season (Oct-Nov fall, Mar-Apr spring)
    - Greek Week (last 2 weeks before spring finals)
    - Greek Thursday (canonical weekly mixer/bar night for IFC chapters)
    - Pregame window (7–10 PM Thu/Fri/Sat — pre-event bar surge)
    - Composite social intensity (0–1 continuous)

    Bar proximity weights (GREEK_BAR_PROXIMITY) reflect physical distance to
    the Dinkytown fraternity corridor:
        Blarney's 0.75 · Sally's 0.45 · Kollege Klub 0.90
    """

    node_type = "greek_life"

    def execute(self, config: dict, inputs: dict) -> dict:
        from providers.greek_life import compute_greek_life_flags

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        return compute_greek_life_flags(dt)


# Registry maps node_type string → class
NODE_REGISTRY: dict[str, type] = {
    "weather":       WeatherNode,
    "sports":        SportsNode,
    "calendar":      CalendarNode,
    "events":        EventsNode,
    "popular_times": PopularTimesNode,
    "greek_life":    GreekLifeNode,
}

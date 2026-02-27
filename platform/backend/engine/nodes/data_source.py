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


# Registry maps node_type string → class
NODE_REGISTRY: dict[str, type] = {
    "weather":       WeatherNode,
    "sports":        SportsNode,
    "calendar":      CalendarNode,
    "events":        EventsNode,
    "popular_times": PopularTimesNode,
}

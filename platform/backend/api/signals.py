"""Live signal aggregation endpoint."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter

from platform.backend.schemas import LiveSignals

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/live", response_model=LiveSignals)
def get_live_signals():
    """Fetch all live signals from real data providers.

    Aggregates weather, sports, academic calendar, local events, and
    popular times busyness for the current moment.
    """
    from providers.calendar import compute_academic_flags, compute_event_flags
    from providers.events import fetch_local_events
    from providers.popular_times import fetch_all_popular_times
    from providers.sports import fetch_tv_sports, fetch_umn_games
    from providers.weather import fetch_current_weather

    now = datetime.now(timezone.utc)
    today = date.today()

    weather = fetch_current_weather()
    umn_games = fetch_umn_games(today)
    tv_sports = fetch_tv_sports(today)
    academic = compute_academic_flags(now)
    events_flags = compute_event_flags(now)
    local_events = fetch_local_events(today)
    pop_times = fetch_all_popular_times(now)

    return LiveSignals(
        fetched_at=now.isoformat(),
        weather=weather,
        sports={**umn_games, **tv_sports},
        calendar={**academic, **events_flags},
        events=local_events,
        popular_times=pop_times,
    )

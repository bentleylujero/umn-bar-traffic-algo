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

@router.get("/insights")
def get_live_insights() -> dict:
    """Dynamically generate text insights from current provider data."""
    from providers.calendar import compute_academic_flags
    from providers.greek_life import compute_greek_life_flags
    from providers.weather import fetch_current_weather
    from providers.sports import fetch_umn_games, fetch_tv_sports
    now = datetime.now(timezone.utc)
    today = date.today()
    
    acad = compute_academic_flags(now)
    greek = compute_greek_life_flags(now)
    weather = fetch_current_weather()
    sports_umn = fetch_umn_games(today)
    sports_tv = fetch_tv_sports(today)
    
    # Academic
    if acad.get("classes_in_session"):
        ac_str = f"Classes in session, Week {acad.get('week_of_semester', '?')} of 16. Typical mid-semester baseline."
    else:
        ac_str = "Classes are not in session (weekend or break). Expect different traffic patterns as students focus on socializing rather than studies."
        
    # Greek
    if greek.get("is_greek_formal_season") and greek.get("active_date_party"):
        gr_str = f"Greek formal season is active. Tonight's date party host: {greek['active_date_party']}. Expect a major pregame surge and after-party spillover at Kollege Klub."
    elif greek.get("is_greek_thursday"):
        gr_str = "Greek Thursday is active. IFC chapter mixers are running tonight. Pregame window will drive Kollege Klub toward peak capacity."
    else:
        gr_str = "No major Greek events tonight. Greek social intensity is tracking at standard baseline levels for this day of the week."
        
    # Weather
    temp = weather.get("temperature_c", "N/A")
    if weather.get("is_severe_weather"):
        we_str = f"Severe weather active. Temperature: {temp}°C. Cold/severe weather drives massive indoor foot traffic and extends late-night stays."
    elif weather.get("is_first_nice_day"):
        we_str = f"First nice day of spring! Temperature: {temp}°C. Expect patios and outdoor areas to be packed early."
    else:
        we_str = f"Standard weather conditions. Temperature: {temp}°C, Wind chill: {weather.get('wind_chill_c', 'N/A')}°C. Normal traffic expectations."
        
    # Athletics — with opponent name and multi-game support
    opp = sports_umn.get("opponent_name")
    opp_str = f" vs. {opp}" if opp else ""
    game_hr  = sports_umn.get("game_hour")
    time_str = f" (tipoff ~{game_hr}:00 CT)" if game_hr else ""
    rivalry_note = " Rivalry multiplier active — bar intensity +30–50% above baseline." if sports_umn.get("is_rivalry_game") else ""

    if sports_umn.get("is_football_home"):
        ath_str = f"Gopher Football home game{opp_str}{time_str}! Expect massive Stadium Village pregame foot traffic, followed by Dinkytown postgame migration.{rivalry_note}"
    elif sports_umn.get("is_basketball_home") and sports_umn.get("is_hockey_home"):
        ath_str = f"Double-header day! Basketball{opp_str}{time_str} AND Hockey both at home. Stacked sports draw elevates bar traffic all evening.{rivalry_note}"
    elif sports_umn.get("is_basketball_home"):
        ath_str = f"Men's Basketball home game{opp_str}{time_str}. Sally's TV crowd will build through the 2nd half (8–10 PM peak). KK and Blarney's get pregame foot traffic 2h before tipoff.{rivalry_note}"
    elif sports_umn.get("is_hockey_home"):
        ath_str = f"Hockey home game{opp_str}{time_str}. Strong student fanbase drives Dinkytown pregame traffic.{rivalry_note}"
    else:
        ath_str = "No major UMN home games today. Traffic will not be driven by local athletics."
        
    # TV Sports
    if sports_tv.get("is_vikings_game"):
        tv_str = "Vikings game today. Strongest weekly MN correlation for TV sports; expect sustained afternoon crowds."
    elif sports_tv.get("is_march_madness_elite"):
        tv_str = "March Madness Elite 8! One of the largest TV-driven bar nights of the year."
    else:
        tv_str = "No major national TV sports anchoring crowds today. Normal rotation of patrons expected without TV anchors."
        
    # Outlook
    out_str = "Model executing dynamically. True Context shifts are driven by the real-time API integrations listed above."

    return {
        "academic": ac_str,
        "greek_life": gr_str,
        "weather": we_str,
        "athletics": ath_str,
        "tv_sports": tv_str,
        "outlook": out_str
    }

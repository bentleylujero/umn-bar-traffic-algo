"""Sports-schedule providers — UMN Gophers + Minnesota Twins.

Data sources (both free, no API key):
  UMN Athletics : ESPN unofficial site API
  Twins         : MLB Stats API (statsapi.mlb.com)

Results are cached in-process with a 1-hour TTL to avoid hammering APIs.
All functions degrade gracefully — a network failure returns safe defaults.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ── In-process cache ──────────────────────────────────────────────────────────
_CACHE_TTL = 3600  # 1 hour
_cache: dict[str, tuple[float, object]] = {}


def _cache_get(key: str) -> Optional[object]:
    if key in _cache:
        ts, val = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            return val
    return None


def _cache_set(key: str, val: object) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), val)


def _get(url: str, timeout: int = 8) -> Optional[dict]:
    """GET JSON with timeout; returns None on any error."""
    try:
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "umn-bar-traffic/1.0"})
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("Sports fetch failed: %s — %s", url, exc)
        return None


# ── UMN Gophers ───────────────────────────────────────────────────────────────

_ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

_GOPHER_SPORTS: list[tuple[str, str, str]] = [
    ("football",   "college-football",        "minnesota"),
    ("basketball", "mens-college-basketball", "minnesota"),
    ("hockey",     "mens-college-hockey",     "minnesota"),
]

# Rival programs — a game against any of these is flagged is_rivalry_game
_RIVALS: frozenset[str] = frozenset({
    "wisconsin", "iowa", "michigan", "ohio-state", "penn-state",
    "north-dakota", "michigan-state",
})

_SPORT_FLAG: dict[str, str] = {
    "football":   "is_football_home",
    "basketball": "is_basketball_home",
    "hockey":     "is_hockey_home",
}


def fetch_umn_games(target_date: date) -> dict:
    """Return UMN home-game flags for *target_date*.

    Returns
    -------
    dict with keys:
        is_game_day, is_football_home, is_basketball_home, is_hockey_home,
        is_rivalry_game, game_hour  (local 24-h int or None)
    """
    cache_key = f"umn_{target_date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    result: dict = {
        "is_game_day":         0,
        "is_football_home":    0,
        "is_basketball_home":  0,
        "is_hockey_home":      0,
        "is_rivalry_game":     0,
        "game_hour":           None,
    }

    date_str = target_date.isoformat()

    for sport, league, team in _GOPHER_SPORTS:
        url  = f"{_ESPN_BASE}/{sport}/{league}/teams/{team}/schedule"
        data = _get(url)
        if not data:
            continue

        for event in data.get("events", []):
            # ESPN dates are ISO-8601 UTC; compare only the date portion
            event_date = event.get("date", "")[:10]
            if event_date != date_str:
                continue

            for comp in event.get("competitions", []):
                competitors = comp.get("competitors", [])
                home_team   = next(
                    (c for c in competitors if c.get("homeAway") == "home"),
                    None,
                )
                if home_team is None:
                    continue
                team_slug = home_team.get("team", {}).get("slug", "")
                if "minnesota" not in team_slug.lower():
                    continue

                # It's a UMN home game
                result[_SPORT_FLAG[sport]] = 1
                result["is_game_day"]      = 1

                # Tip-off / kick-off hour (UTC → local approximation: UTC-6)
                try:
                    utc_dt   = datetime.fromisoformat(
                        event["date"].replace("Z", "+00:00")
                    )
                    local_hr = (utc_dt.hour - 6) % 24   # CDT offset
                    result["game_hour"] = local_hr
                except Exception:
                    result["game_hour"] = 19  # default: 7 PM

                # Rivalry check — look at the away team's slug
                for c in competitors:
                    if c.get("homeAway") == "away":
                        away_slug = c.get("team", {}).get("slug", "")
                        if any(r in away_slug.lower() for r in _RIVALS):
                            result["is_rivalry_game"] = 1

    _cache_set(cache_key, result)
    return result


# ── Minnesota Twins ───────────────────────────────────────────────────────────

_MLB_URL  = "https://statsapi.mlb.com/api/v1/schedule"
_TWINS_ID = 142  # MLB team ID


def fetch_twins_game(target_date: date) -> dict:
    """Return Twins home-game flag and game hour for *target_date*.

    Returns
    -------
    dict with keys:
        is_twins_home : int (0 or 1)
        twins_game_hour : int or None
    """
    cache_key = f"twins_{target_date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    date_str = target_date.isoformat()
    url  = (
        f"{_MLB_URL}?teamId={_TWINS_ID}&sportId=1"
        f"&startDate={date_str}&endDate={date_str}"
    )
    data = _get(url)

    result: dict = {"is_twins_home": 0, "twins_game_hour": None}

    if data:
        for game_date in data.get("dates", []):
            for game in game_date.get("games", []):
                home_id = (
                    game.get("teams", {})
                        .get("home", {})
                        .get("team", {})
                        .get("id")
                )
                if home_id == _TWINS_ID:
                    result["is_twins_home"] = 1
                    try:
                        game_time_str = game.get("gameDate", "")
                        utc_dt   = datetime.fromisoformat(
                            game_time_str.replace("Z", "+00:00")
                        )
                        result["twins_game_hour"] = (utc_dt.hour - 6) % 24
                    except Exception:
                        result["twins_game_hour"] = 19
                    break

    _cache_set(cache_key, result)
    return result

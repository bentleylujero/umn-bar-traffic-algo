"""Sports-schedule providers — UMN Gophers + major watchable TV events.

Data source: ESPN unofficial site API (free, no key required).
All functions degrade gracefully on network failure.
1-hour in-process cache on all results.

TV weight scale
---------------
0.0  nothing on
0.6  CFB regular season Saturday (moderate draw)
1.0  NFL regular season / NBA playoffs (early rounds) / CFB bowl
1.5  NFL regular-season Vikings game / CFB major bowl / March Madness
2.0  NFL playoffs / CFB Championship / March Madness Final Four
2.5+ Super Bowl (4.0) / combined events
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)

_ESPN = "https://site.api.espn.com/apis/site/v2/sports"
_CACHE_TTL = 3600
_cache: dict[str, tuple[float, object]] = {}

# ── Internal helpers ──────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[object]:
    if key in _cache:
        ts, val = _cache[key]
        if (datetime.now(timezone.utc).timestamp() - ts) < _CACHE_TTL:
            return val
    return None


def _cache_set(key: str, val: object) -> None:
    _cache[key] = (datetime.now(timezone.utc).timestamp(), val)


def _get(url: str, timeout: int = 8) -> Optional[dict]:
    try:
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "umn-bar-traffic/1.0"})
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("ESPN fetch failed: %s — %s", url, exc)
        return None


def _scoreboard(sport: str, league: str, target_date: date,
                extra: str = "") -> list[dict]:
    """Fetch ESPN scoreboard events for a sport/league on target_date."""
    date_str = target_date.strftime("%Y%m%d")
    url  = f"{_ESPN}/{sport}/{league}/scoreboard?dates={date_str}{extra}"
    data = _get(url)
    return (data or {}).get("events", [])


def _season_type(event: dict) -> int:
    """1=preseason 2=regular 3=postseason."""
    return event.get("season", {}).get("type", 2)


def _kickoff_local(event: dict) -> Optional[int]:
    """Return local (CDT, UTC-5 in winter / UTC-6 in summer) kickoff hour."""
    try:
        utc_dt = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        # Minneapolis is UTC-6 standard / UTC-5 daylight; use -6 as approximation
        return (utc_dt.hour - 6) % 24
    except Exception:
        return None


def _has_slug(event: dict, fragment: str) -> bool:
    for comp in event.get("competitions", []):
        for c in comp.get("competitors", []):
            if fragment in c.get("team", {}).get("slug", "").lower():
                return True
    return False


def _is_home_slug(event: dict, fragment: str) -> bool:
    for comp in event.get("competitions", []):
        for c in comp.get("competitors", []):
            if (fragment in c.get("team", {}).get("slug", "").lower()
                    and c.get("homeAway") == "home"):
                return True
    return False


def _away_slugs(event: dict) -> list[str]:
    slugs = []
    for comp in event.get("competitions", []):
        for c in comp.get("competitors", []):
            if c.get("homeAway") == "away":
                slugs.append(c.get("team", {}).get("slug", "").lower())
    return slugs


# ── UMN Gophers home games ────────────────────────────────────────────────────

_UMN_SPORTS = [
    ("football",   "college-football",        "&groups=80"),
    ("basketball", "mens-college-basketball", "&groups=50"),
    ("hockey",     "mens-college-hockey",     ""),
]

_UMN_FLAG = {
    "football":   "is_football_home",
    "basketball": "is_basketball_home",
    "hockey":     "is_hockey_home",
}

_UMN_RIVALS: frozenset[str] = frozenset({
    "wisconsin", "iowa", "michigan", "ohio-state", "penn-state",
    "north-dakota", "michigan-state", "minnesota-duluth",
})


def fetch_umn_games(target_date: date) -> dict:
    """Return UMN home-game flags for target_date via ESPN scoreboard."""
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

    for sport, league, extra in _UMN_SPORTS:
        for event in _scoreboard(sport, league, target_date, extra):
            if not _has_slug(event, "minnesota"):
                continue
            if not _is_home_slug(event, "minnesota"):
                continue

            result[_UMN_FLAG[sport]] = 1
            result["is_game_day"]    = 1
            result["game_hour"]      = result["game_hour"] or _kickoff_local(event)

            for slug in _away_slugs(event):
                if any(r in slug for r in _UMN_RIVALS):
                    result["is_rivalry_game"] = 1

    _cache_set(cache_key, result)
    return result


# ── Major TV sports — the bar-watching driver ─────────────────────────────────

# Name fragments that indicate elite bowl / championship games
_MAJOR_BOWLS = frozenset({
    "rose bowl", "sugar bowl", "fiesta bowl", "orange bowl",
    "cotton bowl", "peach bowl", "semifinal", "national championship",
    "playoff", "cfp",
})

# ESPN NCAAB event names for elite rounds
_MM_ELITE = frozenset({
    "elite eight", "elite 8", "final four", "semifinal",
    "national championship", "championship",
})


def fetch_tv_sports(target_date: date) -> dict:
    """Return TV-watchability signals for target_date.

    Returns
    -------
    dict with keys:
        is_nfl_game_day       : 0/1 — any NFL game today
        is_nfl_playoffs       : 0/1 — NFL playoff game today
        is_super_bowl         : 0/1 — it's Super Bowl Sunday
        is_vikings_game       : 0/1 — Vikings playing (home or away)
        is_cfb_saturday       : 0/1 — CFB regular-season Saturday
        is_cfb_championship   : 0/1 — major bowl or national championship
        is_march_madness      : 0/1 — NCAA tournament game
        is_march_madness_elite: 0/1 — Elite 8 / Final Four / Championship
        is_nba_playoffs       : 0/1 — NBA playoff game
        tv_game_hour          : int | None — kickoff of biggest game (local hr)
        tv_game_weight        : float — magnitude 0–4
    """
    cache_key = f"tv_{target_date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    result: dict = {
        "is_nfl_game_day":        0,
        "is_nfl_playoffs":        0,
        "is_super_bowl":          0,
        "is_vikings_game":        0,
        "is_cfb_saturday":        0,
        "is_cfb_championship":    0,
        "is_march_madness":       0,
        "is_march_madness_elite": 0,
        "is_nba_playoffs":        0,
        "tv_game_hour":           None,
        "tv_game_weight":         0.0,
    }

    best_w = 0.0
    best_h: Optional[int] = None

    def _update_best(weight: float, hour: Optional[int]) -> None:
        nonlocal best_w, best_h
        if weight > best_w:
            best_w = weight
            best_h = hour

    # ── NFL ──────────────────────────────────────────────────────────────────
    for event in _scoreboard("football", "nfl", target_date):
        stype = _season_type(event)
        if stype == 1:          # preseason — no bar draw
            continue

        name  = event.get("name", "").lower()
        hour  = _kickoff_local(event)
        result["is_nfl_game_day"] = 1

        if stype == 3:          # postseason
            result["is_nfl_playoffs"] = 1
            if "super bowl" in name:
                result["is_super_bowl"] = 1
                w = 4.0
            else:
                w = 2.0         # Wild Card / Divisional / Conference
        else:
            w = 1.0             # regular season

        if _has_slug(event, "minnesota"):
            result["is_vikings_game"] = 1
            w = min(w + 0.5, 4.0)

        _update_best(w, hour)

    # ── College football ─────────────────────────────────────────────────────
    for event in _scoreboard("football", "college-football", target_date,
                             "&groups=80"):
        stype = _season_type(event)
        name  = event.get("name", "").lower()
        hour  = _kickoff_local(event)

        if stype == 3:          # bowl season / postseason
            result["is_cfb_championship"] = 1
            if any(b in name for b in _MAJOR_BOWLS):
                w = 2.5 if "national championship" in name else 2.0
            else:
                w = 1.0         # regular bowl
        else:
            result["is_cfb_saturday"] = 1
            w = 0.6             # regular-season CFB

        _update_best(w, hour)

    # ── March Madness (NCAAB tournament) ─────────────────────────────────────
    for event in _scoreboard("basketball", "mens-college-basketball",
                             target_date, "&groups=100"):
        if _season_type(event) != 3:
            continue            # only tournament games

        result["is_march_madness"] = 1
        name = event.get("name", "").lower()
        hour = _kickoff_local(event)

        if any(e in name for e in _MM_ELITE):
            result["is_march_madness_elite"] = 1
            w = 2.5 if "championship" in name else 2.0
        else:
            w = 0.8

        _update_best(w, hour)

    # ── NBA playoffs ─────────────────────────────────────────────────────────
    for event in _scoreboard("basketball", "nba", target_date):
        if _season_type(event) != 3:
            continue            # regular season doesn't drive bar traffic

        result["is_nba_playoffs"] = 1
        name = event.get("name", "").lower()
        hour = _kickoff_local(event)
        w    = 2.0 if "final" in name else 1.2

        _update_best(w, hour)

    result["tv_game_weight"] = best_w
    result["tv_game_hour"]   = best_h

    _cache_set(cache_key, result)
    return result

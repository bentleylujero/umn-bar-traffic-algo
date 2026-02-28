"""Greek life social event calendar and bar traffic signals for UMN.

All signals are derived purely from the date/time — no network calls required.
Update _GREEK_EVENT_DATES each academic year as needed.

Signal overview
---------------
is_greek_rush_week        IFC informal rush (Welcome Week) OR PHC formal recruitment (weeks 2-3)
is_greek_bid_day          Day fraternities/sororities release bids (~day 28 each semester)
is_greek_formal_season    Date-party/formal season: Oct-Nov (fall) + Mar-Apr (spring)
is_greek_week             Spring Greek Week (late April, ~week 15 of spring semester)
is_greek_thursday         Thursday during active semester outside finals/rush — biggest Greek bar night
is_greek_pregame_window   7 PM–10 PM on Thu/Fri/Sat in active semester — pre-event bar spike
greek_social_intensity    Continuous 0–1 composite signal (higher = more Greek bar traffic)
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

# ── Semester definitions (mirrors providers/calendar.py _SEMESTERS) ───────────
# Each tuple: (label, start, finals_start)
# Greek events are anchored to semester start dates.
_SEMESTERS: list[tuple[str, date, date]] = [
    ("Fall 2024",   date(2024,  9,  3), date(2024, 12, 16)),
    ("Spring 2025", date(2025,  1, 21), date(2025,  4, 28)),
    ("Fall 2025",   date(2025,  9,  2), date(2025, 12, 15)),
    ("Spring 2026", date(2026,  1, 20), date(2026,  4, 27)),
    ("Fall 2026",   date(2026,  9,  1), date(2026, 12, 14)),
    ("Spring 2027", date(2027,  1, 19), date(2027,  4, 26)),
]

# ── Greek-specific calendar events (hand-curated each year) ──────────────────
# Bid days are the single biggest Greek bar nights of the semester.
# Dates come from UMN FSL announcements and Panhellenic Instagram.
_BID_DAYS: list[date] = [
    date(2024,  9, 28),   # Fall 2024 IFC/PHC bid day
    date(2025,  2, 14),   # Spring 2025 bid day (Valentine's weekend)
    date(2025,  9, 27),   # Fall 2025
    date(2026,  2, 13),   # Spring 2026
    date(2026,  9, 26),   # Fall 2026
    date(2027,  2, 12),   # Spring 2027
]

# Greek Week: typically the last full week of April before spring finals.
# Derived automatically below from spring semester finals_start − 2 weeks.

# Homecoming is already covered by the academic calendar provider.
# We add it here only as a Greek-activity weight, not a new flag.

# ── Bar proximity to Greek houses ─────────────────────────────────────────────
# Based on physical distance to the Dinkytown/Como fraternity corridor.
#   bar_id 1 = Blarney's Pub    (Dinkytown — ~0.2 mi from Phi Gam, Chi Psi, etc.)
#   bar_id 2 = Sally's Saloon   (Stadium Village — fewer frat houses)
#   bar_id 3 = Kollege Klub     (Dinkytown — adjacent to Greek row, institution)
GREEK_BAR_PROXIMITY: dict[int, float] = {
    1: 0.75,   # Blarney's — high Greek foot traffic
    2: 0.45,   # Sally's   — moderate (sorority houses south of campus)
    3: 0.90,   # Kollege Klub — very high, primary Greek destination
}

# ── UMN IFC fraternities (24 chapters, all IFC-affiliated) ───────────────────
IFC_FRATERNITIES: list[str] = [
    "Alpha Delta Phi", "Alpha Epsilon Pi", "Alpha Gamma Rho", "Alpha Tau Omega",
    "Beta Theta Pi", "Chi Psi", "Delta Chi", "Delta Kappa Epsilon",
    "Delta Tau Delta", "FarmHouse", "Phi Gamma Delta (FIJI)", "Kappa Sigma",
    "Phi Kappa Psi", "Phi Sigma Kappa", "Pi Kappa Alpha", "Sigma Alpha Epsilon",
    "Sigma Alpha Mu", "Sigma Chi", "Sigma Nu", "Sigma Phi Epsilon",
    "Sigma Pi", "Tau Kappa Epsilon", "Theta Chi", "Triangle",
]

# ── UMN Panhellenic sororities (13 chapters, PHC-affiliated) ─────────────────
PHC_SORORITIES: list[str] = [
    "Alpha Chi Omega", "Alpha Omicron Pi", "Alpha Sigma Kappa",
    "Delta Gamma", "Kappa Alpha Theta", "Lambda Delta Phi",
    "Phi Mu", "Alpha Gamma Delta", "Alpha Phi", "Chi Omega",
    "Gamma Phi Beta",
    # Associate chapters (year-round informal recruitment):
    "Kappa Kappa Gamma", "Pi Beta Phi", "Sigma Alpha Epsilon Pi",
]

# Total active Greek members at UMN: ~3,000 across 55 organizations
GREEK_MEMBERSHIP_ESTIMATE = 3_000


# ── Helper: find current semester context ────────────────────────────────────

def _semester_context(d: date) -> dict | None:
    """Return context dict for the semester containing *d*, or None if off-semester."""
    for label, start, finals_start in _SEMESTERS:
        if start <= d < finals_start:
            days_since = (d - start).days
            week = days_since // 7 + 1
            is_fall = "Fall" in label
            is_spring = "Spring" in label
            return {
                "label": label,
                "start": start,
                "finals_start": finals_start,
                "days_since": days_since,
                "week": week,
                "is_fall": is_fall,
                "is_spring": is_spring,
            }
    return None


def _greek_week_range(finals_start: date) -> tuple[date, date]:
    """Return (start, end) of Greek Week = 2 weeks before spring finals."""
    gw_start = finals_start - timedelta(weeks=2)
    gw_end   = gw_start + timedelta(days=6)
    return gw_start, gw_end


# ── Main signal computation ───────────────────────────────────────────────────

def compute_greek_life_flags(dt: datetime) -> dict:
    """Return all Greek life signal flags for the given datetime.

    Parameters
    ----------
    dt : datetime
        The observation timestamp (tz-aware or naive).

    Returns
    -------
    dict with keys:
        is_greek_rush_week        : int  (0/1)
        is_greek_bid_day          : int  (0/1) — also includes day before/after
        is_greek_formal_season    : int  (0/1)
        is_greek_week             : int  (0/1)
        is_greek_thursday         : int  (0/1)
        is_greek_pregame_window   : int  (0/1)
        greek_social_intensity    : float (0.0–1.0)
    """
    d   = dt.date()
    dow = d.weekday()     # 0=Mon … 6=Sun
    hr  = dt.hour

    ctx = _semester_context(d)
    in_semester = ctx is not None

    # ── 1. Rush week ──────────────────────────────────────────────────────────
    # IFC informal rush: Welcome Week = days 0–13 of fall semester
    # PHC formal recruitment: days 14–27 of fall semester (2-week structured rush)
    # Spring: both councils run 2-week informal rush in weeks 1-2
    is_greek_rush_week = 0
    if in_semester:
        ds = ctx["days_since"]
        if ctx["is_fall"] and ds < 28:
            is_greek_rush_week = 1
        elif ctx["is_spring"] and ds < 14:
            is_greek_rush_week = 1

    # ── 2. Bid day ────────────────────────────────────────────────────────────
    # Bid day ± 1 day counts (pre-bid celebration + aftermath bar night)
    is_greek_bid_day = int(
        any(abs((d - bd).days) <= 1 for bd in _BID_DAYS)
    )

    # ── 3. Formal / date-party season ────────────────────────────────────────
    # Fall: October + November (frat/sorority formals every weekend)
    # Spring: March + April (spring formals, date dashes)
    is_greek_formal_season = int(
        (in_semester and d.month in (10, 11)) or
        (in_semester and d.month in (3, 4))
    )

    # ── 4. Greek Week (spring only) ───────────────────────────────────────────
    # The last 2 full weeks before spring finals — competitions + socials every night
    is_greek_week = 0
    if in_semester and ctx["is_spring"]:
        gw_start, gw_end = _greek_week_range(ctx["finals_start"])
        is_greek_week = int(gw_start <= d <= gw_end)

    # ── 5. Greek Thursday ────────────────────────────────────────────────────
    # Thursday is the canonical Greek bar night at UMN (IFC mixers, sorority
    # "thirsty Thursday" events, pregame before Friday date parties).
    # Exclude: finals week, rush week (dry period for some chapters), summer.
    is_greek_thursday = int(
        dow == 3 and               # Thursday
        in_semester and
        not is_greek_rush_week and
        ctx["week"] <= 15          # not study days / finals
    )

    # ── 6. Pregame window ─────────────────────────────────────────────────────
    # Greeks go to bars 7–10 PM before events (date parties, formals, mixers).
    # Peak pregame: Thu/Fri/Sat during formal season or after bid day.
    is_high_social_night = (
        dow in (3, 4, 5) and       # Thu / Fri / Sat
        in_semester and
        (is_greek_formal_season or is_greek_bid_day or is_greek_thursday)
    )
    is_greek_pregame_window = int(
        is_high_social_night and 19 <= hr <= 22
    )

    # ── 7. Composite social intensity ────────────────────────────────────────
    # Continuous 0–1 signal: aggregates all flags + time-of-night weighting.
    score = 0.0

    if in_semester:
        # Base: weekly recurring social pattern
        # Thu night is king, Wed/Fri secondary, Sat tertiary
        weekly_draw = {0: 0.05, 1: 0.05, 2: 0.15, 3: 0.55, 4: 0.35, 5: 0.30, 6: 0.15}
        score += weekly_draw.get(dow, 0.0)

        # Semester position bonus: weeks 3–8 and 11–14 are peak social (avoid midterms)
        week = ctx["week"]
        if 3 <= week <= 8:
            score += 0.15
        elif 11 <= week <= 14:
            score += 0.12

        # Rush week suppresses general social bar traffic (chapters are busy recruiting)
        if is_greek_rush_week:
            score *= 0.5

        # Bid day is massive — single biggest Greek night
        if is_greek_bid_day:
            score = max(score, 0.85)

        # Formal season: every weekend has a date party or formal
        if is_greek_formal_season:
            score += 0.20

        # Greek Week: sustained elevated activity all week
        if is_greek_week:
            score += 0.25

        # Hour-of-night weighting (pregame 7–10, late-night spillback 11–2)
        if 19 <= hr <= 22:
            score *= 1.30    # pregame ramp
        elif 23 == hr or hr <= 2:
            score *= 1.10    # post-event spillback to bars

    score = min(score, 1.0)

    return {
        "is_greek_rush_week":      is_greek_rush_week,
        "is_greek_bid_day":        is_greek_bid_day,
        "is_greek_formal_season":  is_greek_formal_season,
        "is_greek_week":           is_greek_week,
        "is_greek_thursday":       is_greek_thursday,
        "is_greek_pregame_window": is_greek_pregame_window,
        "greek_social_intensity":  round(score, 3),
    }


def get_greek_bar_affinity(bar_id: int) -> float:
    """Return 0–1 proximity weight for how much Greek traffic this bar receives.

    Based on physical distance to the Dinkytown fraternity corridor.
    Blarney's and Kollege Klub are on/adjacent to Greek row;
    Sally's is in Stadium Village with fewer fraternity houses nearby.
    """
    return GREEK_BAR_PROXIMITY.get(bar_id, 0.5)

"""UMN academic-calendar and holiday signal computation.

All signals are derived purely from the date — no network calls required.
Update _SEMESTERS each academic year as UMN publishes official dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


# ── UMN semester schedule ─────────────────────────────────────────────────────
# Each tuple: (label, start, syllabus_end, midterms_start, midterms_end,
#              finals_start, end)
_SEMESTERS: list[tuple[str, date, date, date, date, date, date]] = [
    ("Fall 2024",
     date(2024,  9,  3), date(2024,  9,  9),
     date(2024, 10, 14), date(2024, 11,  1),
     date(2024, 12, 16), date(2024, 12, 21)),
    ("Spring 2025",
     date(2025,  1, 21), date(2025,  1, 27),
     date(2025,  3,  3), date(2025,  3, 21),
     date(2025,  4, 28), date(2025,  5, 16)),
    ("Fall 2025",
     date(2025,  9,  2), date(2025,  9,  8),
     date(2025, 10, 13), date(2025, 10, 31),
     date(2025, 12, 15), date(2025, 12, 20)),
    ("Spring 2026",
     date(2026,  1, 20), date(2026,  1, 26),
     date(2026,  3,  2), date(2026,  3, 20),
     date(2026,  4, 27), date(2026,  5, 15)),
    ("Fall 2026",
     date(2026,  9,  1), date(2026,  9,  7),
     date(2026, 10, 12), date(2026, 10, 30),
     date(2026, 12, 14), date(2026, 12, 19)),
    ("Spring 2027",
     date(2027,  1, 19), date(2027,  1, 25),
     date(2027,  3,  1), date(2027,  3, 19),
     date(2027,  4, 26), date(2027,  5, 14)),
]


def _thanksgiving(year: int) -> date:
    """4th Thursday of November."""
    nov1 = date(year, 11, 1)
    first_thu = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thu + timedelta(weeks=3)


def compute_academic_flags(dt: datetime) -> dict:
    """Return all academic-calendar signal flags for the given datetime."""
    d = dt.date()
    is_summer = 5 <= d.month <= 8

    for _label, start, syl_end, mid_s, mid_e, fin_s, end in _SEMESTERS:
        if start <= d < fin_s:
            week = (d - start).days // 7 + 1
            return {
                "classes_in_session": 1,
                "is_finals_week":     0,
                "is_welcome_week":    int(d <= syl_end),
                "is_syllabus_week":   int(d <= syl_end),
                "is_midterms_week":   int(mid_s <= d <= mid_e),
                "is_break":           0,
                "is_summer_session":  0,
                "week_of_semester":   week,
                "days_until_break":   float((fin_s - d).days),
            }
        if fin_s <= d <= end:
            return {
                "classes_in_session": 0,
                "is_finals_week":     1,
                "is_welcome_week":    0,
                "is_syllabus_week":   0,
                "is_midterms_week":   0,
                "is_break":           0,
                "is_summer_session":  0,
                "week_of_semester":   16,
                "days_until_break":   0.0,
            }

    # Between semesters / summer / break
    return {
        "classes_in_session": 0,
        "is_finals_week":     0,
        "is_welcome_week":    0,
        "is_syllabus_week":   0,
        "is_midterms_week":   0,
        "is_break":           int(not is_summer),
        "is_summer_session":  int(is_summer),
        "week_of_semester":   None,
        "days_until_break":   None,
    }


def compute_event_flags(dt: datetime) -> dict:
    """Return holiday / special-event flags for the given datetime."""
    d   = dt.date()
    tg  = _thanksgiving(d.year)

    return {
        "is_holiday":            int(
            (d.month == 1  and d.day == 1)   or  # New Year's Day
            (d.month == 7  and d.day == 4)   or  # Independence Day
            (d.month == 11 and d == tg)      or  # Thanksgiving
            (d.month == 12 and d.day == 25)       # Christmas
        ),
        "is_st_patricks":        int(d.month == 3  and d.day == 17),
        "is_halloween":          int(d.month == 10 and d.day == 31),
        "is_blackout_wednesday": int(d == tg - timedelta(days=1)),
        "is_new_years_eve":      int(d.month == 12 and d.day == 31),
    }

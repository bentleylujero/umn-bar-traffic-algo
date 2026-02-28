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


# ── UMN Parents' Weekends (early October each fall) ──────────────────────────
_PARENTS_WEEKENDS: list[tuple[date, date]] = [
    (date(2025, 10, 17), date(2025, 10, 19)),
    (date(2026, 10, 16), date(2026, 10, 18)),
    (date(2027, 10, 15), date(2027, 10, 17)),
]


def compute_academic_flags(dt: datetime) -> dict:
    """Return all academic-calendar signal flags for the given datetime."""
    d = dt.date()
    is_summer = 5 <= d.month <= 8

    for _label, start, syl_end, mid_s, mid_e, fin_s, end in _SEMESTERS:
        if start <= d < fin_s:
            days_since = (d - start).days
            week       = days_since // 7 + 1
            is_study   = int(fin_s - timedelta(days=3) <= d < fin_s)
            is_weekend = d.weekday() >= 5
            return {
                "classes_in_session":       0 if is_weekend else 1,
                "is_finals_week":           0,
                "is_welcome_week":          int(d <= syl_end),
                "is_syllabus_week":         int(d <= syl_end),
                "is_midterms_week":         int(mid_s <= d <= mid_e),
                "is_break":                 0,
                "is_summer_session":        0,
                "week_of_semester":         week,
                "days_until_break":         float((fin_s - d).days),
                "is_study_days":            is_study,
                "days_since_semester_start": days_since,
                "is_commencement":          0,
            }
        if fin_s <= d <= end:
            return {
                "classes_in_session":       0,
                "is_finals_week":           1,
                "is_welcome_week":          0,
                "is_syllabus_week":         0,
                "is_midterms_week":         0,
                "is_break":                 0,
                "is_summer_session":        0,
                "week_of_semester":         16,
                "days_until_break":         0.0,
                "is_study_days":            0,
                "days_since_semester_start": (d - start).days,
                "is_commencement":          0,
            }

    # Between semesters / summer / break
    # Commencement: within 3 days after a spring semester end
    is_commencement = int(
        any(
            end.month == 5 and end < d <= end + timedelta(days=3)
            for _, _, _, _, _, _, end in _SEMESTERS
        )
    )
    return {
        "classes_in_session":       0,
        "is_finals_week":           0,
        "is_welcome_week":          0,
        "is_syllabus_week":         0,
        "is_midterms_week":         0,
        "is_break":                 int(not is_summer and not is_commencement),
        "is_summer_session":        int(is_summer),
        "week_of_semester":         None,
        "days_until_break":         None,
        "is_study_days":            0,
        "days_since_semester_start": None,
        "is_commencement":          is_commencement,
    }


def compute_event_flags(dt: datetime) -> dict:
    """Return holiday / special-event flags for the given datetime."""
    d   = dt.date()
    tg  = _thanksgiving(d.year)

    is_parents_weekend = int(
        any(start <= d <= end for start, end in _PARENTS_WEEKENDS)
    )

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
        "is_cinco_de_mayo":      int(d.month == 5  and d.day == 5),
        "is_parents_weekend":    is_parents_weekend,
    }

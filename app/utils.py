"""Shared utilities for the UMN Bar Traffic dashboard app."""

from __future__ import annotations

import logging
from datetime import datetime
import pandas as pd
import streamlit as st

from config.settings import BARS
from data.db import get_connection
from providers.calendar import compute_academic_flags, compute_event_flags
from providers.sports import fetch_umn_games, fetch_tv_sports
from providers.weather import fetch_current_weather

log = logging.getLogger(__name__)

@st.cache_data(ttl=600, show_spinner="Fetching weather…")
def get_weather():
    return fetch_current_weather()


@st.cache_data(ttl=3600, show_spinner="Fetching today's signals…")
def get_today_signals(pred_date):
    """Auto-detect all non-weather signals for pred_date. Cached 1 hour."""
    dt     = datetime(pred_date.year, pred_date.month, pred_date.day, 20, 0, 0)
    acad   = compute_academic_flags(dt)
    events = compute_event_flags(dt)
    games  = fetch_umn_games(pred_date)
    tv     = fetch_tv_sports(pred_date)
    return {**acad, **events, **games, **tv}


def insert_observation(
    bar_id: int,
    observed_at: datetime,
    wait_minutes: float,
    pct_full: float | None,
    drink_wait_minutes: float | None,
    cover_charge: float | None,
    notes: str,
    temperature_c: float | None,
    precipitation_mm: float | None,
    is_game_day: bool,
    is_holiday: bool,
) -> str | None:
    """Insert one observation + signals row. Returns error string or None."""
    try:
        conn = get_connection()
        with conn:
            cur = conn.execute(
                """
                INSERT INTO observations
                    (bar_id, observed_at, wait_minutes, pct_full, drink_wait_minutes,
                     cover_charge, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bar_id,
                    observed_at.isoformat(timespec="seconds"),
                    wait_minutes,
                    pct_full,
                    drink_wait_minutes,
                    cover_charge if cover_charge is not None and cover_charge >= 0 else None,
                    notes.strip() or None,
                ),
            )
            obs_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO signals
                    (observation_id, temperature_c, precipitation_mm, is_game_day, is_holiday)
                VALUES (?, ?, ?, ?, ?)
                """,
                (obs_id, temperature_c, precipitation_mm, int(is_game_day), int(is_holiday)),
            )
        conn.close()
        return None
    except Exception as exc:
        return str(exc)


def recent_observations(limit: int = 15) -> pd.DataFrame:
    """Return the most recently inserted observations across all bars."""
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            o.id                AS observation_id,
            b.name              AS bar,
            o.observed_at,
            o.wait_minutes,
            o.pct_full,
            o.drink_wait_minutes,
            o.cover_charge,
            o.notes,
            s.temperature_c,
            s.precipitation_mm,
            s.is_game_day,
            s.is_holiday,
            o.created_at
        FROM observations o
        JOIN bars b ON b.id = o.bar_id
        LEFT JOIN signals s ON s.observation_id = o.id
        ORDER BY o.created_at DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()
    return df


def fetch_observation(obs_id: int) -> dict | None:
    """Return a single observation (with signals) as a dict, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            o.id, o.bar_id, b.name AS bar_name,
            o.observed_at, o.wait_minutes, o.pct_full, o.drink_wait_minutes,
            o.cover_charge, o.notes,
            s.temperature_c, s.precipitation_mm,
            COALESCE(s.is_game_day, 0) AS is_game_day,
            COALESCE(s.is_holiday, 0)  AS is_holiday
        FROM observations o
        JOIN bars b ON b.id = o.bar_id
        LEFT JOIN signals s ON s.observation_id = o.id
        WHERE o.id = ?
        """,
        (obs_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_observation(
    obs_id: int,
    bar_id: int,
    observed_at: datetime,
    wait_minutes: float,
    pct_full: float | None,
    drink_wait_minutes: float | None,
    cover_charge: float | None,
    notes: str,
    temperature_c: float | None,
    precipitation_mm: float | None,
    is_game_day: bool,
    is_holiday: bool,
) -> str | None:
    """UPDATE an existing observation + its signals row. Returns error or None."""
    try:
        conn = get_connection()
        with conn:
            conn.execute(
                """
                UPDATE observations
                SET bar_id = ?, observed_at = ?, wait_minutes = ?,
                    pct_full = ?, drink_wait_minutes = ?,
                    cover_charge = ?, notes = ?
                WHERE id = ?
                """,
                (
                    bar_id,
                    observed_at.isoformat(timespec="seconds"),
                    wait_minutes,
                    pct_full,
                    drink_wait_minutes,
                    cover_charge if cover_charge is not None and cover_charge >= 0 else None,
                    notes.strip() or None,
                    obs_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO signals
                    (observation_id, temperature_c, precipitation_mm, is_game_day, is_holiday)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    temperature_c    = excluded.temperature_c,
                    precipitation_mm = excluded.precipitation_mm,
                    is_game_day      = excluded.is_game_day,
                    is_holiday       = excluded.is_holiday
                """,
                (obs_id, temperature_c, precipitation_mm, int(is_game_day), int(is_holiday)),
            )
        conn.close()
        return None
    except Exception as exc:
        return str(exc)


def delete_observations(ids: list[int]) -> str | None:
    """Delete observations by ID (cascade removes signals). Returns error or None."""
    if not ids:
        return None
    try:
        conn = get_connection()
        with conn:
            conn.executemany(
                "DELETE FROM observations WHERE id = ?",
                [(i,) for i in ids],
            )
        conn.close()
        return None
    except Exception as exc:
        return str(exc)

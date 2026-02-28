"""Crowd-sourced report ingestion endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from config.settings import BAR_CAPACITIES, DEAL_TYPES
from platform.backend.schemas import CrowdReport
from data.db import get_connection

router = APIRouter(prefix="/reports", tags=["reports"])

# Default cover charge (dollars) when deal_type='cover_charge' and no amount given
_DEFAULT_COVER = 5.0


@router.post("/submit", status_code=201)
def submit_report(report: CrowdReport):
    """Submit a live headcount observation for a bar.

    Accepts either pct_full (0–100) or people_count (raw heads); if both are
    provided people_count takes precedence and is converted using BAR_CAPACITIES.

    deal_type must be one of: none, happy_hour, drink_special, entertainment,
    cover_charge.  When deal_type='cover_charge' and cover_charge is not
    supplied, it defaults to $5.

    observed_at defaults to the current UTC time when omitted.
    """
    conn = get_connection()
    try:
        bar = conn.execute(
            "SELECT id FROM bars WHERE id = ?", (report.bar_id,)
        ).fetchone()
        if not bar:
            raise HTTPException(
                status_code=404,
                detail=f"Bar with id {report.bar_id} not found",
            )

        # Validate deal_type
        if report.deal_type and report.deal_type not in DEAL_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"deal_type must be one of {DEAL_TYPES}",
            )

        # Resolve pct_full: people_count wins if provided
        pct_full = report.pct_full
        if report.people_count is not None:
            capacity = BAR_CAPACITIES.get(report.bar_id, 200)
            pct_full = round(min(100.0, report.people_count / capacity * 100), 1)

        # Resolve cover_charge: auto-set when deal_type='cover_charge'
        cover_charge = report.cover_charge
        if report.deal_type == "cover_charge" and cover_charge is None:
            cover_charge = _DEFAULT_COVER

        # Resolve timestamp
        if report.observed_at is not None:
            ts = report.observed_at.astimezone(timezone.utc).isoformat(
                timespec="seconds"
            )
        else:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

        conn.execute(
            """
            INSERT OR REPLACE INTO observations
                (bar_id, observed_at, wait_minutes, pct_full,
                 cover_charge, deal_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.bar_id,
                ts,
                report.wait_minutes,
                pct_full,
                cover_charge,
                report.deal_type or "none",
                report.notes,
            ),
        )
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    return {
        "status": "success",
        "bar_id": report.bar_id,
        "observed_at": ts,
        "pct_full": pct_full,
        "deal_type": report.deal_type or "none",
    }

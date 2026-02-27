"""Crowd-sourced report ingestion endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from platform.backend.schemas import CrowdReport
from data.db import get_connection

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/submit", status_code=201)
def submit_report(report: CrowdReport):
    """Submit a live report for a bar.

    Writes the report to the observations table in the SQLite database.
    These observations will be used as historical context (lags) and 
    live signals for future predictions.
    """
    conn = get_connection()
    try:
        # Validate bar_id
        bar = conn.execute("SELECT id FROM bars WHERE id = ?", (report.bar_id,)).fetchone()
        if not bar:
            raise HTTPException(status_code=404, detail=f"Bar with id {report.bar_id} not found")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        
        conn.execute(
            """
            INSERT INTO observations (bar_id, observed_at, wait_minutes, pct_full, cover_charge, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                report.bar_id,
                now,
                report.wait_minutes,
                report.pct_full,
                report.cover_charge,
                report.notes
            )
        )
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    return {"status": "success", "message": "Report submitted"}

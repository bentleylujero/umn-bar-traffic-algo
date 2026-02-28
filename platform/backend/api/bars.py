"""Bar metadata endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from config.settings import BAR_CAPACITIES, BARS, DEAL_TYPES

router = APIRouter(prefix="/bars", tags=["bars"])


@router.get("/")
def list_bars():
    """Return bar metadata including estimated capacities and valid deal types."""
    return {
        "bars": [
            {
                "id": i + 1,
                "name": b["name"],
                "neighborhood": b["neighborhood"],
                "capacity": BAR_CAPACITIES.get(i + 1),
            }
            for i, b in enumerate(BARS)
        ],
        "deal_types": DEAL_TYPES,
    }

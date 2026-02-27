"""Model cache management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/status")
def model_status():
    """Return the current model cache state."""
    from platform.backend.engine.nodes.predictor_node import model_cache_status

    return model_cache_status()


@router.post("/retrain", status_code=202)
def retrain():
    """Invalidate the model cache.

    The next predict request will trigger a full retrain.  Returns immediately
    (202 Accepted) — the actual training happens on the next /predict call.
    """
    from platform.backend.engine.nodes.predictor_node import invalidate_model_cache

    invalidate_model_cache()
    return {"status": "accepted", "message": "Cache cleared — model will retrain on next predict request."}

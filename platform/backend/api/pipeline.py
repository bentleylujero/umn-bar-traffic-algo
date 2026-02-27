"""Generic pipeline execution endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from platform.backend.schemas import PipelineDef, PipelineRunResult

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=PipelineRunResult)
def run_pipeline(pipeline: PipelineDef) -> PipelineRunResult:
    """Execute a user-defined pipeline DAG.

    Accepts a full PipelineDef (nodes + edges) and runs it in topological
    order, returning per-node results and any predictions generated.
    """
    from platform.backend.engine.executor import execute_pipeline

    return execute_pipeline(pipeline)


@router.get("/definitions")
def list_pipeline_definitions() -> list[dict]:
    """Return pre-built named pipelines available for execution."""
    return [
        {
            "id": "live_prediction",
            "name": "Live Bar Traffic Prediction",
            "description": (
                "Full real-time prediction pipeline: "
                "Weather → Sports → Calendar → Events → Features → ML Model"
            ),
            "nodes": [
                "weather",
                "sports",
                "calendar",
                "events",
                "popular_times",
                "feature_extractor",
                "predictor",
            ],
        },
        {
            "id": "signals_only",
            "name": "Signal Aggregation Only",
            "description": "Collect all live signals without running predictions",
            "nodes": ["weather", "sports", "calendar", "events", "popular_times"],
        },
    ]

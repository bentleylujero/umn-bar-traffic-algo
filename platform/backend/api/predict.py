"""Bar wait-time prediction endpoints."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from platform.backend.schemas import PipelineDef, PredictionRequest, PredictionResult

router = APIRouter(prefix="/predict", tags=["predict"])


@router.get("/all", response_model=list[PredictionResult])
def predict_all_bars():
    """Run the full prediction pipeline for all bars right now."""
    from platform.backend.engine.executor import execute_pipeline

    pipeline = _build_live_pipeline()
    result = execute_pipeline(pipeline)

    if result.predictions:
        return [PredictionResult(**p) for p in result.predictions]
    return []


@router.get("/{bar_id}", response_model=PredictionResult)
def predict_bar(bar_id: int):
    """Predict wait time for a specific bar."""
    from platform.backend.engine.executor import execute_pipeline

    pipeline = _build_live_pipeline(bar_ids=[bar_id])
    result = execute_pipeline(pipeline)

    if result.predictions:
        preds = [p for p in result.predictions if p.get("bar_id") == bar_id]
        if preds:
            return PredictionResult(**preds[0])

    raise HTTPException(
        status_code=404,
        detail=f"No prediction could be generated for bar_id={bar_id}",
    )


def _build_live_pipeline(bar_ids: Optional[list[int]] = None) -> PipelineDef:
    """Build the standard live prediction pipeline definition."""
    from platform.backend.schemas import EdgeDef, NodeDef

    now_str = datetime.now(timezone.utc).isoformat()
    today_str = date.today().isoformat()

    nodes = [
        NodeDef(node_id="weather",   node_type="weather",   config={}),
        NodeDef(node_id="sports",    node_type="sports",    config={"date": today_str}),
        NodeDef(node_id="calendar",  node_type="calendar",  config={"datetime": now_str}),
        NodeDef(node_id="events",    node_type="events",    config={"date": today_str}),
        NodeDef(
            node_id="pop_times",
            node_type="popular_times",
            config={"datetime": now_str},
        ),
        NodeDef(
            node_id="crowd_reports",
            node_type="crowd_reports",
            config={"window_minutes": 60},
        ),
        NodeDef(
            node_id="features",
            node_type="feature_extractor",
            config={"datetime": now_str, "bar_ids": bar_ids or [1, 2, 3]},
        ),
        NodeDef(node_id="predictor", node_type="predictor", config={}),
    ]
    edges = [
        EdgeDef(source="weather",   target="features"),
        EdgeDef(source="sports",    target="features"),
        EdgeDef(source="calendar",  target="features"),
        EdgeDef(source="events",    target="features"),
        EdgeDef(source="pop_times", target="features"),
        EdgeDef(source="crowd_reports", target="features"),
        EdgeDef(source="features",  target="predictor"),
    ]
    return PipelineDef(
        pipeline_id="live_prediction",
        name="Live Bar Traffic Prediction",
        nodes=nodes,
        edges=edges,
    )

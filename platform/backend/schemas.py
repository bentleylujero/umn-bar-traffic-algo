"""Pydantic v2 models for the UMN Bar Traffic platform API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

class CrowdReport(BaseModel):
    bar_id: int
    wait_minutes: float
    pct_full: Optional[float] = None         # 0–100; derived from people_count if omitted
    people_count: Optional[int] = None       # raw headcount; converted to pct_full server-side
    cover_charge: Optional[float] = None     # dollars; auto-set when deal_type='cover_charge'
    deal_type: Optional[str] = None          # none|happy_hour|drink_special|entertainment|cover_charge
    observed_at: Optional[datetime] = None   # defaults to now() when omitted
    notes: Optional[str] = None

class PredictionRequest(BaseModel):
    bar_id: int
    at_datetime: Optional[datetime] = None  # defaults to now


class PredictionResult(BaseModel):
    bar_id: int
    bar_name: str
    predicted_wait_minutes: float
    predicted_pct_full: float  # 0–1
    confidence: str  # "high" | "medium" | "low"
    signals_used: dict[str, Any] = {}
    model_used: str  # "ml" | "baseline" | "fallback_default"


class LiveSignals(BaseModel):
    fetched_at: str
    weather: dict[str, Any]
    sports: dict[str, Any]
    calendar: dict[str, Any]
    events: dict[str, Any]
    popular_times: dict[int, dict]


class NodeDef(BaseModel):
    node_id: str
    node_type: str  # "weather" | "sports" | "events" | "calendar" | "popular_times" | "feature_extractor" | "predictor"
    config: dict[str, Any] = {}


class EdgeDef(BaseModel):
    source: str
    target: str


class PipelineDef(BaseModel):
    pipeline_id: str
    name: str
    nodes: list[NodeDef]
    edges: list[EdgeDef]


class PipelineRunResult(BaseModel):
    pipeline_id: str
    status: str
    node_results: dict[str, Any]
    predictions: Optional[list[Any]] = None
    execution_time_ms: float

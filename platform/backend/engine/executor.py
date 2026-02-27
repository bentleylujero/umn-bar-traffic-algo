"""Execute a pipeline DAG node by node in topological order."""

from __future__ import annotations

import logging
import time
from typing import Any

from platform.backend.engine.dag import get_node_inputs, topological_sort
from platform.backend.engine.nodes.crowd_node import CrowdReportNode
from platform.backend.engine.nodes.data_source import NODE_REGISTRY
from platform.backend.engine.nodes.feature_node import FeatureExtractorNode
from platform.backend.engine.nodes.predictor_node import PredictorNode
from platform.backend.schemas import NodeDef, PipelineDef, PipelineRunResult

log = logging.getLogger(__name__)

# Full node type → class registry (data sources + ML nodes)
_ALL_NODES: dict[str, type] = {
    **NODE_REGISTRY,
    "feature_extractor": FeatureExtractorNode,
    "crowd_reports":     CrowdReportNode,
    "predictor":         PredictorNode,
}


def execute_pipeline(pipeline: PipelineDef) -> PipelineRunResult:
    """Execute all nodes in topological order, passing outputs downstream.

    Each node receives:
      - config : its own NodeDef.config dict
      - inputs : dict keyed by parent node_id → that parent's output dict

    Returns a PipelineRunResult with per-node outputs and any predictions.
    """
    start_ms = time.time() * 1000
    node_map: dict[str, NodeDef] = {n.node_id: n for n in pipeline.nodes}

    # Determine execution order
    try:
        order = topological_sort(pipeline.nodes, pipeline.edges)
    except ValueError as exc:
        return PipelineRunResult(
            pipeline_id=pipeline.pipeline_id,
            status="error",
            node_results={"error": str(exc)},
            execution_time_ms=time.time() * 1000 - start_ms,
        )

    node_outputs: dict[str, Any] = {}

    for node_id in order:
        node_def: NodeDef = node_map[node_id]
        node_type = node_def.node_type

        cls = _ALL_NODES.get(node_type)
        if cls is None:
            log.warning("Unknown node type '%s' for node '%s' — skipping", node_type, node_id)
            node_outputs[node_id] = {}
            continue

        # Gather outputs from all parent nodes
        parent_ids = get_node_inputs(node_id, pipeline.edges)
        inputs: dict[str, Any] = {pid: node_outputs.get(pid, {}) for pid in parent_ids}

        try:
            t0 = time.time()
            node_outputs[node_id] = cls().execute(node_def.config, inputs)
            elapsed_ms = (time.time() - t0) * 1000
            log.info(
                "Node '%s' (%s) completed in %.0f ms",
                node_id, node_type, elapsed_ms,
            )
        except Exception as exc:
            log.error("Node '%s' failed: %s", node_id, exc, exc_info=True)
            node_outputs[node_id] = {"error": str(exc)}

    # Collect predictions from any predictor nodes that ran
    all_predictions: list[Any] = []
    for nid, output in node_outputs.items():
        if isinstance(output, dict) and "predictions" in output:
            for bar_id, pred in output["predictions"].items():
                all_predictions.append(pred)

    return PipelineRunResult(
        pipeline_id=pipeline.pipeline_id,
        status="complete",
        node_results=node_outputs,
        predictions=all_predictions if all_predictions else None,
        execution_time_ms=time.time() * 1000 - start_ms,
    )

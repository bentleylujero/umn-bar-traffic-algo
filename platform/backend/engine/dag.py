"""DAG utilities: topological sort and input resolution."""

from __future__ import annotations

from collections import defaultdict, deque

from platform.backend.schemas import EdgeDef, NodeDef


def topological_sort(nodes: list[NodeDef], edges: list[EdgeDef]) -> list[str]:
    """Return node_ids in execution order (topological sort).

    Raises ValueError if the graph contains a cycle, since DAG execution
    is not possible with circular dependencies.
    """
    in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)

    for e in edges:
        adj[e.source].append(e.target)
        in_degree[e.target] += 1

    # Start with all zero-in-degree nodes (sources)
    queue: deque[str] = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )
    result: list[str] = []

    while queue:
        nid = queue.popleft()
        result.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(nodes):
        raise ValueError("Pipeline contains a cycle — DAG execution not possible.")

    return result


def get_node_inputs(node_id: str, edges: list[EdgeDef]) -> list[str]:
    """Return the node_ids of all direct parents (upstream nodes) of node_id."""
    return [e.source for e in edges if e.target == node_id]

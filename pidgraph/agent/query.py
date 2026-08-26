"""Graph tools for the optional local question-answering helper.

These functions are the only source of connectivity claims. A language model may phrase the
result; it does not invent neighbours. Edge direction is assembly order along conductors, not
verified process flow -- callers must say so.
"""

from __future__ import annotations

from typing import Any


def _tag(data: dict) -> str:
    return str(data.get("tag_canonical") or data.get("label") or "")


def find_tag(graph: Any, query: str, limit: int = 12) -> list[dict]:
    """Substring match on tag, label, or kind."""
    needle = query.strip().upper()
    if not needle:
        return []
    hits: list[dict] = []
    for key, data in graph.nodes(data=True):
        tag = _tag(data)
        kind = str(data.get("kind") or "")
        hay = f"{tag} {kind} {key}".upper()
        if needle in hay:
            hits.append(describe(graph, key))
        if len(hits) >= limit:
            break
    return hits


def describe(graph: Any, key: str) -> dict:
    if key not in graph:
        return {"error": f"no node {key}"}
    data = graph.nodes[key]
    return {
        "stable_key": key,
        "tag": _tag(data) or None,
        "kind": data.get("kind"),
        "dexpi_class": data.get("dexpi_class"),
        "page": data.get("page"),
        "confidence": data.get("confidence"),
        "label": data.get("label") or None,
        "line_numbers": sorted(
            {
                str(edata["line_number"])
                for _u, _v, edata in graph.edges(key, data=True)
                if edata.get("line_number")
            }
            | {
                str(edata["line_number"])
                for _u, _v, edata in graph.in_edges(key, data=True)
                if edata.get("line_number")
            }
        ),
    }


def neighbors(graph: Any, key: str) -> dict:
    if key not in graph:
        return {"error": f"no node {key}"}
    out = []
    for _u, v, data in graph.out_edges(key, data=True):
        out.append({**describe(graph, v), "via": data.get("line_number"), "direction": "out"})
    incoming = []
    for u, _v, data in graph.in_edges(key, data=True):
        incoming.append({**describe(graph, u), "via": data.get("line_number"), "direction": "in"})
    return {"node": describe(graph, key), "out": out, "in": incoming}


def walk(graph: Any, key: str, direction: str = "upstream", max_depth: int = 12) -> dict:
    """BFS along edge direction.

    ``upstream`` follows incoming edges (reverse); ``downstream`` follows outgoing edges.
    Direction is assembly order, not process flow.
    """
    if key not in graph:
        return {"error": f"no node {key}"}
    reverse = direction != "downstream"
    depths: dict[str, int] = {key: 0}
    frontier = [key]
    for depth in range(1, max_depth + 1):
        nxt: list[str] = []
        for current in frontier:
            adjacent = (
                [u for u, _v in graph.in_edges(current)]
                if reverse
                else [v for _u, v in graph.out_edges(current)]
            )
            for neighbour in adjacent:
                if neighbour not in depths:
                    depths[neighbour] = depth
                    nxt.append(neighbour)
        frontier = nxt
        if not frontier:
            break
    nodes = [
        describe(graph, k) | {"depth": d}
        for k, d in sorted(depths.items(), key=lambda kv: kv[1])
    ]
    return {
        "from": describe(graph, key),
        "direction": "upstream" if reverse else "downstream",
        "note": "Edge direction is assembly order along conductors, not verified process flow.",
        "nodes": nodes,
    }

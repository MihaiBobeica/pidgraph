"""Graph interchange.

The graph is emitted in the formats a downstream consumer actually expects, rather than only in a
project-specific shape. GraphML is the common interchange for annotated engineering graphs and is
what published P&ID datasets use, so it is the format that makes this output comparable to other
work.

Both writers flatten attributes to primitives first. GraphML has no representation for a nested
value, and the failure otherwise surfaces as an obscure error from inside the writer rather than as
anything a caller can act on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _flatten(value: Any) -> str | int | float | bool:
    """Reduce an attribute to something the interchange formats can hold."""
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def to_graphml(graph: Any, path: str | Path) -> Path:
    """Write a NetworkX graph as GraphML."""
    import networkx as nx

    clean = graph.copy()
    for _, data in clean.nodes(data=True):
        for key in list(data):
            data[key] = _flatten(data[key])
    for _, _, data in clean.edges(data=True):
        for key in list(data):
            data[key] = _flatten(data[key])

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(clean, out)
    return out


def to_node_link(graph: Any, path: str | Path) -> Path:
    """Write a NetworkX graph as node-link JSON, which NetworkX itself can read back."""
    import networkx as nx

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(graph, edges="edges")
    out.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return out


def combined(pages: list[Any]) -> Any:
    """Merge per-sheet graphs into one plant graph.

    Node identity is content-addressed and includes the sheet, so merging cannot collide two
    different components; sheets join only where an explicit cross-sheet edge exists.
    """
    import networkx as nx

    merged = nx.MultiDiGraph()
    for page in pages:
        merged = nx.compose(merged, page)
    return merged

"""Graph interchange.

The plant graph is a NetworkX ``MultiDiGraph``. Node-link JSON is the on-disk form: NetworkX
reads it back with ``node_link_graph``, and it holds the attributes the rest of the pipeline
already uses. There is no project-specific graph schema and no GraphML writer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_node_link(graph: Any, path: str | Path) -> Path:
    """Write a NetworkX graph as node-link JSON, which NetworkX itself can read back."""
    import networkx as nx

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(graph, edges="edges")
    out.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return out


def load_node_link(path: str | Path) -> Any:
    """Read a plant graph written by :func:`to_node_link`."""
    import networkx as nx

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return nx.node_link_graph(data, edges="edges", directed=True, multigraph=True)


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

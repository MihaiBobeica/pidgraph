"""Interchange tests.

The assignment asks for a graph in a NetworkX-compatible format, so these check that the output
is genuinely loadable by NetworkX rather than merely resembling a graph.
"""

from __future__ import annotations

import json

import pytest

from pidgraph.extract.assemble import (
    EdgeEvidence,
    NodeKind,
    add_plant_edge,
    add_plant_node,
    empty_graph,
)
from pidgraph.extract.lines import LineStyle
from pidgraph.extract.primitives import BBox

nx = pytest.importorskip("networkx")


def sample_graph():
    graph = empty_graph()
    for index, kind in enumerate([NodeKind.INSTRUMENT, NodeKind.COMPONENT, NodeKind.UNKNOWN]):
        add_plant_node(
            graph,
            f"n{index}",
            page=0,
            kind=kind,
            bbox=BBox(index * 10.0, 0.0, index * 10.0 + 8.0, 8.0),
            signature="sig",
            dexpi_class="instrument_circle" if index == 0 else "unknown",
            confidence=0.9 - index * 0.2,
        )
    add_plant_edge(
        graph,
        "n0",
        "n1",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.SOLID,
        confidence=0.85,
    )
    add_plant_edge(
        graph,
        "n1",
        "n2",
        evidence=EdgeEvidence.ENDPOINT_JUNCTION,
        style=LineStyle.DASHED,
        confidence=0.55,
    )
    return graph


class TestNetworkXCompatibility:
    def test_is_a_directed_multigraph(self):
        """Directed because flow has a direction; multi because two components can be joined by
        more than one conductor, and collapsing that would lose real structure."""
        g = sample_graph()
        assert isinstance(g, nx.MultiDiGraph)
        assert g.number_of_nodes() == 3
        assert g.number_of_edges() == 2

    def test_attributes_are_on_the_graph(self):
        g = sample_graph()
        data = g.nodes["n0"]
        assert data["kind"] == "instrument"
        assert data["dexpi_class"] == "instrument_circle"
        assert data["confidence"] == pytest.approx(0.9)
        # Position is carried, so a consumer can lay the graph out as drawn.
        assert "x" in data and "y" in data

    def test_standard_algorithms_run_over_it(self):
        g = sample_graph()
        undirected = g.to_undirected()
        assert nx.is_connected(undirected)
        assert nx.shortest_path(undirected, "n0", "n2") == ["n0", "n1", "n2"]


class TestInterchange:
    def test_node_link_round_trips(self, tmp_path):
        from pidgraph.extract import export

        g = sample_graph()
        path = export.to_node_link(g, tmp_path / "g.json")
        back = export.load_node_link(path)
        assert back.number_of_nodes() == g.number_of_nodes()
        assert back.number_of_edges() == g.number_of_edges()
        assert back.nodes["n0"]["kind"] == "instrument"
        # The file is the NetworkX node-link document, not a project-specific schema.
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert "nodes" in raw and "edges" in raw

    def test_sheets_merge_into_one_plant_graph(self):
        from pidgraph.extract import export

        a, b = sample_graph(), sample_graph()
        # Identity is content-addressed and includes the sheet, so a real merge does not collide;
        # here the same keys are deliberately reused to assert composition is not duplicating.
        merged = export.combined([a, b])
        assert merged.number_of_nodes() == 3

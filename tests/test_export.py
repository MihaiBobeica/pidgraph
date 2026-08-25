"""Interchange tests.

The assignment asks for a graph in a NetworkX-compatible format, so these check that the output
is genuinely loadable by NetworkX rather than merely resembling a graph.
"""

from __future__ import annotations

import pytest

from pidgraph.extract.assemble import Edge, EdgeEvidence, Graph, Node, NodeKind
from pidgraph.extract.lines import LineStyle
from pidgraph.extract.primitives import BBox

nx = pytest.importorskip("networkx")


def sample_graph() -> Graph:
    graph = Graph()
    for index, kind in enumerate([NodeKind.INSTRUMENT, NodeKind.COMPONENT, NodeKind.UNKNOWN]):
        graph.nodes.append(
            Node(
                stable_key=f"n{index}",
                page_index=0,
                kind=kind,
                bbox=BBox(index * 10.0, 0.0, index * 10.0 + 8.0, 8.0),
                signature="sig",
                dexpi_class="instrument_circle" if index == 0 else "unknown",
                confidence=0.9 - index * 0.2,
                label=None,
            )
        )
    graph.edges.append(Edge("n0", "n1", EdgeEvidence.PORT_BINDING, LineStyle.SOLID, 0.85))
    graph.edges.append(Edge("n1", "n2", EdgeEvidence.ENDPOINT_JUNCTION, LineStyle.DASHED, 0.55))
    return graph


class TestNetworkXCompatibility:
    def test_converts_to_a_directed_multigraph(self):
        """Directed because flow has a direction; multi because two components can be joined by
        more than one conductor, and collapsing that would lose real structure."""
        g = sample_graph().to_networkx()
        assert isinstance(g, nx.MultiDiGraph)
        assert g.number_of_nodes() == 3
        assert g.number_of_edges() == 2

    def test_attributes_survive_conversion(self):
        g = sample_graph().to_networkx()
        data = g.nodes["n0"]
        assert data["kind"] == "instrument"
        assert data["dexpi_class"] == "instrument_circle"
        assert data["confidence"] == pytest.approx(0.9)
        # Position is carried, so a consumer can lay the graph out as drawn.
        assert "x" in data and "y" in data

    def test_standard_algorithms_run_over_it(self):
        g = sample_graph().to_networkx()
        undirected = g.to_undirected()
        assert nx.is_connected(undirected)
        assert nx.shortest_path(undirected, "n0", "n2") == ["n0", "n1", "n2"]


class TestInterchange:
    def test_graphml_round_trips(self, tmp_path):
        from pidgraph.extract import export

        g = sample_graph().to_networkx()
        path = export.to_graphml(g, tmp_path / "g.graphml")
        back = nx.read_graphml(path)
        assert back.number_of_nodes() == g.number_of_nodes()
        assert back.number_of_edges() == g.number_of_edges()
        assert back.nodes["n0"]["kind"] == "instrument"

    def test_node_link_round_trips(self, tmp_path):
        import json

        from pidgraph.extract import export

        g = sample_graph().to_networkx()
        path = export.to_node_link(g, tmp_path / "g.json")
        back = nx.node_link_graph(json.loads(path.read_text()), edges="edges")
        assert back.number_of_nodes() == g.number_of_nodes()

    def test_none_and_sequences_are_flattened_for_graphml(self, tmp_path):
        """GraphML cannot hold a nested value, and the writer's error is unhelpful."""
        from pidgraph.extract import export

        g = nx.MultiDiGraph()
        g.add_node("a", empty=None, seq=[1, 2, 3])
        g.add_edge("a", "a", tags=("x", "y"))
        path = export.to_graphml(g, tmp_path / "g.graphml")
        back = nx.read_graphml(path)
        assert back.nodes["a"]["seq"] == "1,2,3"
        assert back.nodes["a"]["empty"] == ""

    def test_sheets_merge_into_one_plant_graph(self):
        from pidgraph.extract import export

        a, b = sample_graph().to_networkx(), sample_graph().to_networkx()
        # Identity is content-addressed and includes the sheet, so a real merge does not collide;
        # here the same keys are deliberately reused to assert composition is not duplicating.
        merged = export.combined([a, b])
        assert merged.number_of_nodes() == 3

"""Convention-text binding: each phase's one property, on hand-built geometry.

The load-bearing assertion is topology invariance -- the pass may set labels, attributes and
confidence, and nothing else. Everything else here pins one rule each: bubble composition by
containment, edge-gap binding for long strings, global one-to-one assignment, self-binding
exclusion, the orientation gate on line labels, and the unbound ledger.
"""

from __future__ import annotations

from pidgraph.extract.assemble import (
    EdgeEvidence,
    NodeKind,
    add_plant_edge,
    add_plant_node,
    empty_graph,
    node_bbox,
)
from pidgraph.extract.attach import attach_all
from pidgraph.extract.calibrate import Scale, UnitSystem
from pidgraph.extract.lines import LineStyle, Polyline
from pidgraph.extract.primitives import BBox, Point
from pidgraph.extract.text import TextRegion


def make_scale(module: float = 2.0) -> Scale:
    return Scale(
        unit_system=next(iter(UnitSystem)),
        module=module,
        sheet="ANSI_B",
        page_width_pt=1224.0,
        page_height_pt=792.0,
    )


def add_node(
    graph, key: str, x0: float, y0: float, x1: float, y1: float, kind: NodeKind = NodeKind.UNKNOWN
) -> None:
    add_plant_node(
        graph,
        key,
        page=0,
        kind=kind,
        bbox=BBox(x0, y0, x1, y1),
        signature="sig",
        dexpi_class="unknown",
        confidence=0.9,
    )


def make_region(
    text: str | None,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    orientation: str = "horizontal",
    confidence: float = 0.9,
) -> TextRegion:
    return TextRegion(
        bbox=BBox(x0, y0, x1, y1),
        orientation=orientation,
        source="clustered",
        mark_count=3,
        page_index=0,
        text=text,
        text_confidence=confidence,
    )


def make_line(line_id: int, start: Point, end: Point) -> Polyline:
    return Polyline(
        id=line_id,
        page_index=0,
        start=start,
        end=end,
        style=LineStyle.SOLID,
        piece_count=1,
        total_ink=start.dist(end),
        bridged_gaps=(),
    )


def test_bubble_rows_compose_into_one_tag() -> None:
    """Function letters over the loop number, inside the circle, are one identity."""
    graph = empty_graph()
    add_node(graph, "ins_a", 0, 0, 14, 14, NodeKind.INSTRUMENT)
    regions = [
        make_region("PI", 5, 3, 9, 5),
        make_region("123", 4, 8, 10, 10, confidence=0.8),
    ]
    stats = attach_all(graph, regions, [], make_scale())
    node = graph.nodes["ins_a"]
    assert node["tag_canonical"] == "PI-123"
    assert node["attach_method"] == "bubble_rows"
    assert node["label"] == "PI-123"
    assert node["confidence"] == 0.8  # the weakest row read bounds the composite
    assert stats["composed_bubbles"] == 1
    assert stats["bound_nodes"] == 1


def test_long_region_binds_by_edge_gap_not_centre() -> None:
    """A long string abutting a node is near, no matter where its centre sits."""
    graph = empty_graph()
    add_node(graph, "com_a", 0, 0, 4, 4, NodeKind.COMPONENT)
    # Centre distance ~19pt, far beyond any radius rule; bbox gap 1pt, inside the 2-module gate.
    regions = [make_region("MV-100-01", 5, 1, 40, 3)]
    attach_all(graph, regions, [], make_scale())
    assert graph.nodes["com_a"]["tag_canonical"] == "MV-100-01"
    assert graph.nodes["com_a"]["attach_method"] == "adjacent"


def test_assignment_is_global_one_to_one() -> None:
    """Each region binds its nearest compatible node; no node receives two tags."""
    graph = empty_graph()
    add_node(graph, "com_a", 0, 0, 4, 4, NodeKind.COMPONENT)
    add_node(graph, "com_b", 10, 0, 14, 4, NodeKind.COMPONENT)
    regions = [
        make_region("V-101", 4.5, 1, 7, 3),  # gap 0.5 to a, 3.0 to b
        make_region("V-102", 7.5, 1, 9.5, 3),  # gap 3.5 to a, 0.5 to b
    ]
    attach_all(graph, regions, [], make_scale())
    assert graph.nodes["com_a"]["tag_canonical"] == "V-101"
    assert graph.nodes["com_b"]["tag_canonical"] == "V-102"


def test_coincident_text_node_is_not_its_own_label() -> None:
    """Text ink promoted to a node must not claim its own string as a tag."""
    graph = empty_graph()
    add_node(graph, "unk_a", 0, 0, 10, 3)
    regions = [make_region("[123A]", 0, 0, 10, 3)]
    stats = attach_all(graph, regions, [], make_scale())
    assert "tag_canonical" not in graph.nodes["unk_a"]
    assert len(stats["unbound"]) == 1
    assert "no compatible node" in stats["unbound"][0]["reason"]
    assert graph.graph["warnings"]  # the ledger surfaces as a warning


def test_line_number_annotates_conductor_edges() -> None:
    graph = empty_graph()
    add_node(graph, "com_a", 0, 8, 4, 12)
    add_node(graph, "com_b", 56, 8, 60, 12)
    add_plant_edge(
        graph,
        "com_a",
        "com_b",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.SOLID,
        confidence=0.85,
        line_ids=(7,),
    )
    lines = [make_line(7, Point(4, 10), Point(56, 10))]
    regions = [make_region('1"-D2S', 20, 5.4, 30, 7.4)]
    stats = attach_all(graph, regions, lines, make_scale())
    _u, _v, edge = next(iter(graph.edges(data=True)))
    assert edge["line_number"] == '1"-D2S'
    assert edge["line_size"] == "1"
    assert edge["line_service"] == "D2S"
    assert stats["bound_edges"] == 1
    # The tag never lands on a node: a line number names the run, not either endpoint.
    assert all("tag_canonical" not in data for _, data in graph.nodes(data=True))


def test_line_label_orientation_gate() -> None:
    """A label reading across a line belongs to a crossing run, not this one."""
    graph = empty_graph()
    add_node(graph, "com_a", 0, 8, 4, 12)
    add_node(graph, "com_b", 56, 8, 60, 12)
    add_plant_edge(
        graph,
        "com_a",
        "com_b",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.SOLID,
        confidence=0.85,
        line_ids=(7,),
    )
    lines = [make_line(7, Point(4, 10), Point(56, 10))]
    regions = [make_region('1"-D2S', 20, 5.4, 30, 7.4, orientation="vertical")]
    stats = attach_all(graph, regions, lines, make_scale())
    _u, _v, edge = next(iter(graph.edges(data=True)))
    assert "line_number" not in edge
    assert len(stats["unbound"]) == 1
    assert "no conductor" in stats["unbound"][0]["reason"]


def test_line_label_on_edgeless_conductor_is_unbound_with_reason() -> None:
    graph = empty_graph()
    add_node(graph, "com_a", 0, 8, 4, 12)
    lines = [make_line(9, Point(4, 10), Point(56, 10))]
    regions = [make_region('2"-P101', 20, 5.4, 30, 7.4)]
    stats = attach_all(graph, regions, lines, make_scale())
    assert len(stats["unbound"]) == 1
    assert stats["unbound"][0]["reason"] == "conductor carries no edges"


def test_unread_and_unparsed_regions_still_associate() -> None:
    """The legacy rule survives: an unread label is a gap worth showing."""
    graph = empty_graph()
    add_node(graph, "com_a", 0, 0, 6, 6, NodeKind.COMPONENT)
    add_node(graph, "com_b", 20, 0, 26, 6, NodeKind.COMPONENT)
    regions = [
        make_region(None, 6.5, 2, 9, 4),  # unread, near a
        make_region("#?!", 19, 2, 19.9, 4),  # read but unparsed, near b
    ]
    attach_all(graph, regions, [], make_scale())
    assert graph.nodes["com_a"]["label"].startswith("region@")
    assert graph.nodes["com_a"]["attach_method"] == "legacy_radius"
    assert graph.nodes["com_b"]["label"] == "#?!"
    assert "tag_canonical" not in graph.nodes["com_b"]


def test_attachment_never_alters_topology() -> None:
    """The safety property: node and edge sets are identical before and after."""
    graph = empty_graph()
    add_node(graph, "ins_a", 0, 0, 14, 14, NodeKind.INSTRUMENT)
    add_node(graph, "com_b", 30, 0, 34, 4, NodeKind.COMPONENT)
    add_node(graph, "unk_c", 50, 0, 60, 3)
    add_plant_edge(
        graph,
        "ins_a",
        "com_b",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.DASHED,
        confidence=0.85,
        line_ids=(1,),
    )
    add_plant_edge(
        graph,
        "com_b",
        "unk_c",
        evidence=EdgeEvidence.ENDPOINT_JUNCTION,
        style=LineStyle.SOLID,
        confidence=0.55,
        line_ids=(2,),
    )
    nodes_before = [(key, data["kind"], node_bbox(data)) for key, data in graph.nodes(data=True)]
    edges_before = [
        (u, v, data["evidence"], data["style"], tuple(data["line_ids"]))
        for u, v, data in graph.edges(data=True)
    ]
    regions = [
        make_region("PI", 5, 3, 9, 5),
        make_region("123", 4, 8, 10, 10),
        make_region("V-745", 34.5, 1, 38, 3),
        make_region('1"-D2S', 40, 1, 44, 3),
        make_region(None, 50, 4, 52, 6),
    ]
    lines = [make_line(2, Point(34, 2), Point(50, 2))]
    attach_all(graph, regions, lines, make_scale())
    after = [(key, data["kind"], node_bbox(data)) for key, data in graph.nodes(data=True)]
    assert after == nodes_before
    assert [
        (u, v, data["evidence"], data["style"], tuple(data["line_ids"]))
        for u, v, data in graph.edges(data=True)
    ] == edges_before

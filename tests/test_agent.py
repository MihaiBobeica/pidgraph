"""Graph tools used by the optional question helper."""

from __future__ import annotations

from pidgraph.agent.query import find_tag, neighbors, walk
from pidgraph.extract.assemble import (
    EdgeEvidence,
    NodeKind,
    add_plant_edge,
    add_plant_node,
    empty_graph,
)
from pidgraph.extract.lines import LineStyle
from pidgraph.extract.primitives import BBox


def fixture():
    graph = empty_graph()
    add_plant_node(
        graph,
        "src",
        page=0,
        kind=NodeKind.COMPONENT,
        bbox=BBox(0, 0, 4, 4),
        signature="s",
        dexpi_class="Equipment",
        confidence=0.9,
        label="V-100",
    )
    add_plant_node(
        graph,
        "valve",
        page=0,
        kind=NodeKind.COMPONENT,
        bbox=BBox(10, 0, 14, 4),
        signature="s",
        dexpi_class="OperatedValve",
        confidence=0.9,
        label="MV-101",
    )
    add_plant_node(
        graph,
        "dst",
        page=0,
        kind=NodeKind.COMPONENT,
        bbox=BBox(20, 0, 24, 4),
        signature="s",
        dexpi_class="Equipment",
        confidence=0.9,
        label="V-102",
    )
    graph.nodes["src"]["tag_canonical"] = "V-100"
    graph.nodes["valve"]["tag_canonical"] = "MV-101"
    graph.nodes["dst"]["tag_canonical"] = "V-102"
    add_plant_edge(
        graph,
        "src",
        "valve",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.SOLID,
        confidence=0.9,
    )
    add_plant_edge(
        graph,
        "valve",
        "dst",
        evidence=EdgeEvidence.PORT_BINDING,
        style=LineStyle.SOLID,
        confidence=0.9,
    )
    graph.edges["src", "valve", 0]["line_number"] = '2"-GAS'
    return graph


def test_find_tag_by_canonical() -> None:
    hits = find_tag(fixture(), "MV-101")
    assert hits and hits[0]["stable_key"] == "valve"


def test_walk_upstream_reaches_source() -> None:
    result = walk(fixture(), "valve", "upstream")
    keys = {n["stable_key"] for n in result["nodes"]}
    assert keys == {"valve", "src"}
    assert "assembly order" in result["note"]


def test_neighbors_report_both_sides() -> None:
    result = neighbors(fixture(), "valve")
    assert result["in"][0]["stable_key"] == "src"
    assert result["out"][0]["stable_key"] == "dst"


def test_call_tools_picks_tag_from_a_sentence() -> None:
    from pidgraph.agent import _call_tools

    payload = _call_tools(fixture(), "Where does MV-101 connect?")
    assert payload["matches"][0]["stable_key"] == "valve"
    assert "assembly order" in payload["upstream"]["note"]


def test_call_tools_picks_isa_compound_tag() -> None:
    from pidgraph.agent import _call_tools

    graph = fixture()
    graph.nodes["valve"]["tag_canonical"] = "MV-715-02A"
    payload = _call_tools(graph, "Where does MV-715-02A connect?")
    assert payload["matches"][0]["stable_key"] == "valve"


def test_fallback_says_when_nothing_matched() -> None:
    from pidgraph.agent import _fallback_answer

    text = _fallback_answer({"matches": []}, "Ollama is not running.")
    assert "No tags" in text
    assert "assembly order" in text


def test_chat_model_skips_embedding_only() -> None:
    from pidgraph.agent import _chat_model

    chosen = _chat_model(
        [
            {
                "name": "nomic-embed-text:latest",
                "capabilities": ["embedding"],
            },
            {
                "name": "llama3.2:latest",
                "capabilities": ["completion", "tools"],
            },
        ]
    )
    assert chosen == "llama3.2:latest"

"""Graph assembly: turn recognised geometry into a connected plant graph.

Connectivity is built from endpoint proximity and port binding only. A conductor whose interior
crosses another conductor is *not* connected to it: without a jump symbol, crossing lines pass over
one another, and emitting a junction there fabricates an edge. That failure is invisible downstream
-- a fabricated edge is structurally indistinguishable from a real one -- so the conservative rule
is the only safe one.

The plant graph is a NetworkX ``MultiDiGraph``. Every node and edge carries provenance and a
confidence, and every edge records *how* it was established. A graph whose edges are mostly
low-confidence bridges is a different artifact from one whose edges are port bindings, and the
difference has to be visible rather than averaged away.
"""

from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict
from enum import StrEnum
from typing import Any

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.lines import LineStyle, Polyline
from pidgraph.extract.primitives import BBox, Point
from pidgraph.extract.symbols import Symbol
from pidgraph.extract.text import TextRegion

# Attribute names that are first-class on a node, not extra tag/attach fields.
_NODE_CORE = frozenset(
    {
        "kind",
        "dexpi_class",
        "label",
        "page",
        "confidence",
        "signature",
        "x",
        "y",
        "x0",
        "y0",
        "x1",
        "y1",
    }
)
_EDGE_CORE = frozenset({"kind", "style", "evidence", "confidence", "line_ids"})


class NodeKind(StrEnum):
    """Structural role. Deliberately coarse -- the specific class lives in ``dexpi_class``."""

    INSTRUMENT = "instrument"
    COMPONENT = "component"
    JUNCTION = "junction"
    UNKNOWN = "unknown"


class EdgeEvidence(StrEnum):
    """How an edge was established. Retained so weak claims stay queryable."""

    PORT_BINDING = "port_binding"
    """A conductor endpoint lands on a symbol."""
    ENDPOINT_JUNCTION = "endpoint_junction"
    """Two conductor endpoints coincide."""


def empty_graph() -> Any:
    """A plant graph with the graph-level ledgers the rest of the pipeline reads."""
    import networkx as nx

    graph = nx.MultiDiGraph()
    graph.graph["warnings"] = []
    graph.graph["attach"] = {}
    return graph


def add_plant_node(
    graph: Any,
    key: str,
    *,
    page: int,
    kind: NodeKind | str,
    bbox: BBox,
    signature: str,
    dexpi_class: str,
    confidence: float,
    label: str = "",
) -> None:
    """Add one component. Identity is the node id; geometry is stored as flat attributes."""
    centre = bbox.centre
    graph.add_node(
        key,
        kind=str(kind),
        dexpi_class=dexpi_class,
        label=label,
        page=int(page),
        confidence=float(confidence),
        signature=signature,
        x=float(centre.x),
        y=float(centre.y),
        x0=float(bbox.x0),
        y0=float(bbox.y0),
        x1=float(bbox.x1),
        y1=float(bbox.y1),
    )


def add_plant_edge(
    graph: Any,
    source: str,
    target: str,
    *,
    evidence: EdgeEvidence | str,
    style: LineStyle | str,
    confidence: float,
    line_ids: tuple[int, ...] = (),
) -> None:
    graph.add_edge(
        source,
        target,
        kind="process",
        evidence=str(evidence),
        style=str(style),
        confidence=float(confidence),
        line_ids=list(line_ids),
    )


def node_bbox(data: dict) -> BBox:
    return BBox(float(data["x0"]), float(data["y0"]), float(data["x1"]), float(data["y1"]))


def node_centre(data: dict) -> Point:
    return Point(float(data["x"]), float(data["y"]))


def graph_summary(graph: Any) -> str:
    kinds: dict[str, int] = defaultdict(int)
    for _, data in graph.nodes(data=True):
        kinds[str(data.get("kind", "unknown"))] += 1
    labelled = sum(1 for _, data in graph.nodes(data=True) if data.get("label"))
    isolated = sum(1 for n in graph if graph.degree(n) == 0)
    return (
        f"{graph.number_of_nodes()} nodes {dict(kinds)} | {graph.number_of_edges()} edges | "
        f"{labelled} labelled | {isolated} isolated"
    )


def node_store_dict(key: str, data: dict) -> dict:
    """Shape the local/Supabase persist layer already consumes."""
    extra = {name: str(value) for name, value in data.items() if name not in _NODE_CORE}
    return {
        "stable_key": key,
        "page_index": data.get("page", 0),
        "kind": data.get("kind"),
        "dexpi_class": data.get("dexpi_class") or "unknown",
        "label": data.get("label") or None,
        "bbox": [data["x0"], data["y0"], data["x1"], data["y1"]],
        "confidence": data.get("confidence", 1.0),
        "signature": data.get("signature", ""),
        "attributes": extra,
        "provenance": {},
    }


def edge_store_dict(source: str, target: str, data: dict) -> dict:
    extra = {name: value for name, value in data.items() if name not in _EDGE_CORE}
    return {
        "source": source,
        "target": target,
        "kind": data.get("kind", "process"),
        "style": data.get("style"),
        "evidence": data.get("evidence"),
        "confidence": data.get("confidence", 1.0),
        "line_ids": list(data.get("line_ids") or []),
        "attributes": extra,
        "provenance": {},
    }


def stable_key(page_index: int, centre: Point, kind: str, scale: Scale) -> str:
    """Content-addressed identity that survives re-extraction.

    Coordinates are snapped to a fraction of the module before hashing, so trivial drafting or
    floating-point jitter does not produce a new identity and orphan a reviewer's decisions.
    """
    grid = max(scale.u(0.25), 1e-6)
    gx = round(centre.x / grid)
    gy = round(centre.y / grid)
    digest = hashlib.sha1(f"{page_index}|{gx}|{gy}|{kind}".encode()).hexdigest()[:12]
    return f"{kind[:3]}_{page_index}_{digest}"


def _distance_to_segment(point: Point, start: Point, end: Point) -> tuple[float, float]:
    """Perpendicular distance from a point to a segment, and its position along it.

    The position is a 0..1 parameter used to order attachments along a conductor, so consecutive
    inline components become adjacent in the graph rather than all connecting to one another.
    """
    dx, dy = end.x - start.x, end.y - start.y
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return point.dist(start), 0.0
    t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    closest = Point(start.x + t * dx, start.y + t * dy)
    return point.dist(closest), t


def _segment_meets_bbox(start: Point, end: Point, box: BBox) -> bool:
    """Whether a segment touches an (already expanded) box."""
    if box.contains(start) or box.contains(end):
        return True
    # Sample-free slab test: clip the segment's parameter range against each axis.
    dx, dy = end.x - start.x, end.y - start.y
    t0, t1 = 0.0, 1.0
    for delta, lo, hi, origin in ((dx, box.x0, box.x1, start.x), (dy, box.y0, box.y1, start.y)):
        if abs(delta) < 1e-12:
            if origin < lo or origin > hi:
                return False
            continue
        a = (lo - origin) / delta
        b = (hi - origin) / delta
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return False
    return True


def _has_undirected_edge(graph: Any, src: str, dst: str) -> bool:
    return graph.has_edge(src, dst) or graph.has_edge(dst, src)


def build(
    symbols: list[Symbol],
    lines: list[Polyline],
    regions: list[TextRegion],
    scale: Scale,
    page_index: int,
    port_tol: float = 1.5,
    junction_tol: float = 0.8,
) -> Any:
    """Assemble one page into a NetworkX ``MultiDiGraph``.

    ``port_tol`` and ``junction_tol`` are in modules, so the tolerances scale with the drawing
    rather than being tuned to one plot.
    """
    graph = empty_graph()
    port_radius = scale.u(port_tol)
    junction_radius = scale.u(junction_tol)

    # --- bind conductor endpoints to symbols, BEFORE deciding what becomes a node ---------
    # Binding first is what lets the node set be evidence-based. A composite that no conductor
    # reaches and that was not identified dimensionally is not evidence of a component -- it is
    # far more likely a fragment, an arrowhead or hatching. Promoting every candidate instead
    # inflates the graph by an order of magnitude and buries the real components among them.
    touched: set[int] = set()
    endpoint_hits: dict[int, list[int]] = defaultdict(list)
    for line in lines:
        # Symbols attach along a conductor's whole length, not only at its ends. An inline
        # component -- a valve on a header, a fitting in a run -- sits *on* the line, and the
        # standard treats it as lying on one segment between two piping nodes. Binding endpoints
        # only would connect just the first and last item on a run and silently drop every
        # component between them, which is most of them.
        attached: list[tuple[float, int]] = []
        lo_x = min(line.start.x, line.end.x)
        hi_x = max(line.start.x, line.end.x)
        lo_y = min(line.start.y, line.end.y)
        hi_y = max(line.start.y, line.end.y)
        for sym in symbols:
            # Bind on proximity to the symbol's BOX, not to a circle of its larger half-extent.
            # A circular reach around elongated equipment extends far beyond the narrow axis and
            # binds conductors that merely pass nearby -- a fabricated edge, the one failure
            # nothing downstream can detect.
            box = sym.bbox.expanded(port_radius)
            if box.x1 < lo_x or box.x0 > hi_x or box.y1 < lo_y or box.y0 > hi_y:
                continue
            if _segment_meets_bbox(line.start, line.end, box):
                _, position = _distance_to_segment(sym.centre, line.start, line.end)
                attached.append((position, sym.id))
        if not attached:
            continue
        # Ordered along the conductor so consecutive attachments become adjacent components.
        attached.sort()
        for _, sym_id in attached:
            touched.add(sym_id)
            if sym_id not in endpoint_hits[line.id]:
                endpoint_hits[line.id].append(sym_id)

    equipment_scale = 12.0  # modules; larger than any inline component
    promoted = [
        sym
        for sym in symbols
        if sym.is_instrument
        or sym.id in touched
        or (sym.diameter_modules or 0.0) >= equipment_scale
    ]
    dropped = len(symbols) - len(promoted)
    if dropped:
        graph.graph["warnings"].append(
            f"{dropped} symbol candidates carried no evidence (no conductor, not dimensionally "
            "identified, below equipment scale) and were not promoted to nodes"
        )

    # --- nodes from the promoted symbols -------------------------------------------------
    key_by_symbol: dict[int, str] = {}
    for sym in promoted:
        kind = NodeKind.INSTRUMENT if sym.is_instrument else NodeKind.COMPONENT
        if sym.symbol_class == "unknown" and not sym.is_instrument:
            kind = NodeKind.UNKNOWN
        key = stable_key(page_index, sym.centre, str(kind), scale)
        key_by_symbol[sym.id] = key
        if graph.has_node(key):
            continue
        add_plant_node(
            graph,
            key,
            page=page_index,
            kind=kind,
            bbox=sym.bbox,
            signature=sym.signature,
            dexpi_class=sym.symbol_class,
            confidence=sym.confidence,
        )

    bound: dict[int, list[str]] = defaultdict(list)
    for line_id, sym_ids in endpoint_hits.items():
        for sym_id in sym_ids:
            key = key_by_symbol.get(sym_id)
            if key is not None and key not in bound[line_id]:
                bound[line_id].append(key)

    for line in lines:
        keys = bound.get(line.id, [])
        # Consecutive pairs, not just the extremes: items along a run are adjacent to their
        # neighbours, not all connected to the first one.
        for left, right in itertools.pairwise(keys):
            if left == right:
                continue
            add_plant_edge(
                graph,
                left,
                right,
                evidence=EdgeEvidence.PORT_BINDING,
                style=line.style,
                confidence=0.85 if not line.bridged_gaps else 0.6,
                line_ids=(line.id,),
            )

    # --- chain conductors through coincident endpoints -----------------------------------
    # Two symbols joined by a chain of conductors are connected. The chain is walked through
    # endpoint coincidence only; interiors are never consulted, so crossings cannot create a path.
    adjacency: dict[int, set[int]] = defaultdict(set)
    endpoints: list[tuple[Point, int]] = []
    for line in lines:
        endpoints.append((line.start, line.id))
        endpoints.append((line.end, line.id))
    # Grid-bucketed rather than all-pairs: thousands of endpoints make the quadratic sweep the
    # slowest thing in the pipeline, and coincidence is a purely local question.
    cell = max(junction_radius, 1e-6)
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (pt, _) in enumerate(endpoints):
        grid[(int(pt.x // cell), int(pt.y // cell))].append(i)
    for (cx, cy), members in grid.items():
        neighbourhood = [
            j
            for dx in (0, 1)
            for dy in ((0, 1) if dx == 0 else (-1, 0, 1))
            for j in grid.get((cx + dx, cy + dy), ())
        ]
        for i in members:
            pt_a, id_a = endpoints[i]
            for j in neighbourhood:
                if j <= i:
                    continue
                pt_b, id_b = endpoints[j]
                if id_a != id_b and pt_a.dist(pt_b) <= junction_radius:
                    adjacency[id_a].add(id_b)
                    adjacency[id_b].add(id_a)

    seen: set[int] = set()
    for line in lines:
        if line.id in seen:
            continue
        component: list[int] = []
        stack = [line.id]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            stack.extend(adjacency[current] - seen)
        attached_keys = sorted({k for lid in component for k in bound.get(lid, [])})
        if len(attached_keys) < 2:
            continue
        styles = {ln.style for ln in lines if ln.id in component}
        style = LineStyle.DASHED if styles == {LineStyle.DASHED} else LineStyle.SOLID
        # One edge per pair reachable through this conductor component.
        for i, src in enumerate(attached_keys):
            for dst in attached_keys[i + 1 :]:
                if _has_undirected_edge(graph, src, dst):
                    continue
                add_plant_edge(
                    graph,
                    src,
                    dst,
                    evidence=EdgeEvidence.ENDPOINT_JUNCTION,
                    style=style,
                    confidence=0.55,
                    line_ids=tuple(sorted(component)),
                )

    # --- attach labels -------------------------------------------------------------------
    # Convention text binds to the elements it describes: instrument tags compose from the rows
    # inside their bubbles, other tags bind by proximity, and line numbers annotate the edges of
    # the conductor they name. The pass sets labels and attributes only -- it never alters
    # topology. The mechanics, thresholds and ledger live in ``pidgraph/extract/attach.py``.
    from pidgraph.extract.attach import attach_all

    graph.graph["attach"] = attach_all(graph, regions, lines, scale)

    isolated = sum(1 for n in graph if graph.degree(n) == 0)
    if graph.number_of_nodes() and isolated / graph.number_of_nodes() > 0.5:
        graph.graph["warnings"].append(
            f"{isolated}/{graph.number_of_nodes()} nodes are isolated; "
            "connectivity is likely incomplete"
        )
    return graph

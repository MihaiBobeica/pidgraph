"""Graph assembly: turn recognised geometry into a connected plant graph.

Connectivity is built from endpoint proximity and port binding only. A conductor whose interior
crosses another conductor is *not* connected to it: without a jump symbol, crossing lines pass over
one another, and emitting a junction there fabricates an edge. That failure is invisible downstream
-- a fabricated edge is structurally indistinguishable from a real one -- so the conservative rule
is the only safe one.

Every node and edge carries provenance and a confidence, and every edge records *how* it was
established. A graph whose edges are mostly low-confidence bridges is a different artifact from one
whose edges are port bindings, and the difference has to be visible rather than averaged away.
"""

from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.lines import LineStyle, Polyline
from pidgraph.extract.primitives import BBox, Point
from pidgraph.extract.symbols import Symbol
from pidgraph.extract.text import TextRegion


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


@dataclass(frozen=True)
class Node:
    stable_key: str
    page_index: int
    kind: NodeKind
    bbox: BBox
    signature: str
    dexpi_class: str
    confidence: float
    label: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def centre(self) -> Point:
        return self.bbox.centre


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    evidence: EdgeEvidence
    style: LineStyle
    confidence: float
    line_ids: tuple[int, ...] = field(default_factory=tuple)


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def node(self, key: str) -> Node | None:
        return next((n for n in self.nodes if n.stable_key == key), None)

    def degree(self, key: str) -> int:
        return sum(1 for e in self.edges if key in (e.source, e.target))

    def to_dict(self) -> dict:
        return {
            "nodes": [
                {**asdict(n), "kind": str(n.kind), "bbox": list(asdict(n.bbox).values())}
                for n in self.nodes
            ],
            "edges": [
                {**asdict(e), "evidence": str(e.evidence), "style": str(e.style)}
                for e in self.edges
            ],
            "warnings": list(self.warnings),
        }

    def summary(self) -> str:
        kinds: dict[str, int] = defaultdict(int)
        for node in self.nodes:
            kinds[str(node.kind)] += 1
        labelled = sum(1 for n in self.nodes if n.label)
        isolated = sum(1 for n in self.nodes if self.degree(n.stable_key) == 0)
        return (
            f"{len(self.nodes)} nodes {dict(kinds)} | {len(self.edges)} edges | "
            f"{labelled} labelled | {isolated} isolated"
        )


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


def _nearest_region(regions: list[TextRegion], point: Point, within: float) -> TextRegion | None:
    best, best_d = None, within
    for region in regions:
        d = region.centre.dist(point)
        if d <= best_d:
            best, best_d = region, d
    return best


def build(
    symbols: list[Symbol],
    lines: list[Polyline],
    regions: list[TextRegion],
    scale: Scale,
    page_index: int,
    port_tol: float = 1.5,
    junction_tol: float = 0.8,
) -> Graph:
    """Assemble one page into a graph.

    ``port_tol`` and ``junction_tol`` are in modules, so the tolerances scale with the drawing
    rather than being tuned to one plot.
    """
    graph = Graph()
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
        for sym in symbols:
            reach = max(sym.bbox.width, sym.bbox.height) / 2 + port_radius
            distance, position = _distance_to_segment(sym.centre, line.start, line.end)
            if distance <= reach:
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
        graph.warnings.append(
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
        if graph.node(key) is not None:
            continue
        graph.nodes.append(
            Node(
                stable_key=key,
                page_index=page_index,
                kind=kind,
                bbox=sym.bbox,
                signature=sym.signature,
                dexpi_class=sym.symbol_class,
                confidence=sym.confidence,
            )
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
            graph.edges.append(
                Edge(
                    source=left,
                    target=right,
                    evidence=EdgeEvidence.PORT_BINDING,
                    style=line.style,
                    confidence=0.85 if not line.bridged_gaps else 0.6,
                    line_ids=(line.id,),
                )
            )

    # --- chain conductors through coincident endpoints -----------------------------------
    # Two symbols joined by a chain of conductors are connected. The chain is walked through
    # endpoint coincidence only; interiors are never consulted, so crossings cannot create a path.
    adjacency: dict[int, set[int]] = defaultdict(set)
    endpoints: list[tuple[Point, int]] = []
    for line in lines:
        endpoints.append((line.start, line.id))
        endpoints.append((line.end, line.id))
    for i, (pt_a, id_a) in enumerate(endpoints):
        for pt_b, id_b in endpoints[i + 1 :]:
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
        attached = sorted({k for lid in component for k in bound.get(lid, [])})
        if len(attached) < 2:
            continue
        styles = {ln.style for ln in lines if ln.id in component}
        style = LineStyle.DASHED if styles == {LineStyle.DASHED} else LineStyle.SOLID
        # One edge per pair reachable through this conductor component.
        for i, src in enumerate(attached):
            for dst in attached[i + 1 :]:
                if any(
                    {e.source, e.target} == {src, dst} for e in graph.edges
                ):
                    continue
                graph.edges.append(
                    Edge(
                        source=src,
                        target=dst,
                        evidence=EdgeEvidence.ENDPOINT_JUNCTION,
                        style=style,
                        confidence=0.55,
                        line_ids=tuple(sorted(component)),
                    )
                )

    # --- attach labels -------------------------------------------------------------------
    # An instrument's tag sits inside its circle; other labels sit adjacent. Association is
    # nearest-region here and is refined by a global assignment once text is recognised.
    for index, node in enumerate(graph.nodes):
        radius = max(node.bbox.width, node.bbox.height) / 2 + scale.u(1.0)
        region = _nearest_region(regions, node.centre, radius)
        if region is not None:
            graph.nodes[index] = Node(
                stable_key=node.stable_key,
                page_index=node.page_index,
                kind=node.kind,
                bbox=node.bbox,
                signature=node.signature,
                dexpi_class=node.dexpi_class,
                confidence=node.confidence,
                label=f"region@{region.centre.x:.0f},{region.centre.y:.0f}",
                attributes={"text_orientation": region.orientation},
            )

    isolated = sum(1 for n in graph.nodes if graph.degree(n.stable_key) == 0)
    if graph.nodes and isolated / len(graph.nodes) > 0.5:
        graph.warnings.append(
            f"{isolated}/{len(graph.nodes)} nodes are isolated; connectivity is likely incomplete"
        )
    return graph

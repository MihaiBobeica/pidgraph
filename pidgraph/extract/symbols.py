"""Symbol recognition.

**Instrument circles are found dimensionally.** The standard dimensions the device/function circle
in modules, so once calibration has recovered the module the circle is identified by measurement
rather than by matching -- which makes it the highest-confidence object on the sheet.

**Everything else stays ``unknown``.** Candidates still carry a position-, scale- and
rotation-invariant signature so instances of the same shape can be compared, but they are not
forced into a class. Forcing an unrecognised shape into the nearest known class is how template
overfit becomes invisible.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.primitives import BBox, Kind, Point, Primitive

GRID = 12
"""Resolution of the normalised shape raster. Small enough to be tolerant of drafting jitter,
large enough to separate the symbol vocabulary."""

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Symbol:
    """A recognised or unrecognised symbol instance."""

    id: int
    page_index: int
    bbox: BBox
    signature: str
    symbol_class: str
    confidence: float
    diameter_modules: float | None = None
    member_indices: tuple[int, ...] = field(default_factory=tuple)

    @property
    def centre(self) -> Point:
        return self.bbox.centre

    @property
    def is_instrument(self) -> bool:
        return self.symbol_class == "instrument_circle"


def _sample_points(prim: Primitive, per_segment: int = 6) -> list[Point]:
    """Points along a primitive's geometry, dense enough to characterise its shape."""
    pts: list[Point] = []
    for seg in prim.segments:
        for i in range(per_segment):
            t = i / max(per_segment - 1, 1)
            pts.append(Point(seg.a.x + (seg.b.x - seg.a.x) * t, seg.a.y + (seg.b.y - seg.a.y) * t))
    if not pts:
        c = prim.bbox.centre
        pts = [c]
    return pts


def shape_signature(points: list[Point], bbox: BBox, rotation_invariant: bool = True) -> str:
    """A position-, scale- and rotation-normalised signature.

    Normalising by the bounding box makes the signature scale-free, so a symbol drawn at a
    different module produces the same key. Rotation invariance is obtained by taking the
    lexicographically smallest raster over the four quarter turns, which is enough for
    engineering symbology where instances appear at multiples of 90 degrees.
    """
    if bbox.width <= 0 or bbox.height <= 0:
        return "degenerate"

    cells: set[tuple[int, int]] = set()
    for p in points:
        gx = min(GRID - 1, max(0, int((p.x - bbox.x0) / bbox.width * GRID)))
        gy = min(GRID - 1, max(0, int((p.y - bbox.y0) / bbox.height * GRID)))
        cells.add((gx, gy))

    variants = []
    current = cells
    turns = 4 if rotation_invariant else 1
    for _ in range(turns):
        bits = ["1" if (x, y) in current else "0" for y in range(GRID) for x in range(GRID)]
        variants.append("".join(bits))
        current = {(GRID - 1 - y, x) for x, y in current}
    return f"{min(variants)}"


def find_instrument_circles(
    prims: list[Primitive], scale: Scale, page_index: int, start_id: int = 0
) -> list[Symbol]:
    """Locate device/function circles by their standard dimension.

    The standard puts the circle at a fixed number of modules, so this is measurement rather than
    matching. Both the nominal and the permitted alternate size are accepted.
    """
    out: list[Symbol] = []
    next_id = start_id
    for prim in prims:
        if not prim.curves or not prim.is_black:
            continue
        w, h = prim.bbox.width, prim.bbox.height
        if w <= 0 or h <= 0 or abs(w - h) > 0.15 * max(w, h):
            continue
        modules = w / scale.module
        if not (5.0 <= modules <= 10.0):
            continue
        out.append(
            Symbol(
                id=next_id,
                page_index=page_index,
                bbox=prim.bbox,
                signature="circle",
                symbol_class="instrument_circle",
                confidence=0.95,
                diameter_modules=round(modules, 3),
                member_indices=(prim.index,),
            )
        )
        next_id += 1
    return out


def cluster_shapes(
    prims: list[Primitive], scale: Scale, page_index: int, start_id: int = 0
) -> list[Symbol]:
    """Group symbol-scale geometry by normalised shape.

    Every instance comes out as ``unknown`` with its signature attached. A new drawing template
    therefore yields new signatures rather than confident wrong answers.
    """
    out: list[Symbol] = []
    next_id = start_id
    for prim in prims:
        if prim.kind is not Kind.SYMBOL or not prim.is_black:
            continue
        diag_modules = prim.bbox.diagonal / scale.module
        if not (1.0 <= diag_modules <= 40.0):
            continue
        sig = shape_signature(_sample_points(prim), prim.bbox)
        out.append(
            Symbol(
                id=next_id,
                page_index=page_index,
                bbox=prim.bbox,
                signature=sig,
                symbol_class=UNKNOWN,
                confidence=0.0,
                diameter_modules=round(diag_modules, 3),
                member_indices=(prim.index,),
            )
        )
        next_id += 1
    return out


def group_composites(
    prims: list[Primitive],
    scale: Scale,
    page_index: int,
    start_id: int = 0,
    radius: float = 1.2,
) -> list[Symbol]:
    """Group symbol-scale geometry into composite instances before recognising them.

    A symbol is rarely one path. The convention composes final control elements from an *element*
    plus an *actuator*, and a drafting package emits each as separate geometry along with leaders
    and fill hatching. Treating every path as its own symbol therefore inflates the node count by
    roughly an order of magnitude and leaves most of them unreachable by any conductor -- which is
    exactly what over-segmentation looks like from downstream.

    Grouping is single-link over bounding boxes with a module-relative gap, so it scales with the
    drawing. ``radius`` is in modules.
    """
    gap = scale.u(radius)
    candidates = [
        p
        for p in prims
        if p.kind is Kind.SYMBOL and p.is_black and 1.0 <= p.bbox.diagonal / scale.module <= 40.0
    ]
    if not candidates:
        return []

    # Bucket by a coarse grid so only plausible neighbours are ever compared. A candidate is
    # inserted into EVERY cell its expanded box covers, not just the one under its centre: parts
    # are up to forty modules across, and centre-only bucketing means two touching parts whose
    # centres sit a few cells apart are never compared -- which defeats the whole grouping.
    cell = max(gap, 1e-6)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, prim in enumerate(candidates):
        box = prim.bbox.expanded(gap / 2)
        for cx in range(int(box.x0 // cell), int(box.x1 // cell) + 1):
            for cy in range(int(box.y0 // cell), int(box.y1 // cell) + 1):
                buckets[(cx, cy)].append(i)

    parent = list(range(len(candidates)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for members in buckets.values():
        # Coverage-bucketing makes each cell self-sufficient: any two boxes that touch share at
        # least one cell, so no neighbourhood walk is needed.
        for a_pos, i in enumerate(members):
            bi = candidates[i].bbox.expanded(gap / 2)
            for j in members[a_pos + 1 :]:
                if bi.intersects(candidates[j].bbox.expanded(gap / 2)):
                    union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(candidates)):
        groups[find(i)].append(i)

    out: list[Symbol] = []
    next_id = start_id
    for _, members in sorted(groups.items()):
        parts = [candidates[i] for i in members]
        bbox = BBox(
            min(p.bbox.x0 for p in parts),
            min(p.bbox.y0 for p in parts),
            max(p.bbox.x1 for p in parts),
            max(p.bbox.y1 for p in parts),
        )
        diag_modules = bbox.diagonal / scale.module
        # A composite spanning far more than any symbol is a merge failure, not a symbol.
        if diag_modules > 60.0:
            continue
        points: list[Point] = []
        for prim in parts:
            points.extend(_sample_points(prim))
        out.append(
            Symbol(
                id=next_id,
                page_index=page_index,
                bbox=bbox,
                signature=shape_signature(points, bbox),
                symbol_class=UNKNOWN,
                confidence=0.0,
                diameter_modules=round(diag_modules, 3),
                member_indices=tuple(sorted(p.index for p in parts)),
            )
        )
        next_id += 1
    return out


def dedupe(symbols: list[Symbol], scale: Scale, tol: float = 0.5) -> list[Symbol]:
    """Drop instances whose centres coincide, keeping the most confident.

    A symbol is often drawn as several paths, so the same object can be nominated more than once.
    """
    radius = scale.u(tol)
    kept: list[Symbol] = []
    for sym in sorted(symbols, key=lambda s: (-s.confidence, s.id)):
        if any(
            sym.centre.dist(k.centre) <= radius and abs(sym.bbox.width - k.bbox.width) <= radius
            for k in kept
        ):
            continue
        kept.append(sym)
    return sorted(kept, key=lambda s: s.id)


def nearest(symbols: list[Symbol], point: Point, within: float) -> Symbol | None:
    best: Symbol | None = None
    best_d = math.inf
    for sym in symbols:
        d = sym.centre.dist(point)
        if d < best_d and d <= within:
            best, best_d = sym, d
    return best

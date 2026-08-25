"""Symbol recognition.

Two mechanisms, used for different things.

**Instrument circles are found dimensionally.** The standard dimensions the device/function circle
in modules, so once calibration has recovered the module the circle is identified by measurement
rather than by matching -- which makes it the highest-confidence object on the sheet.

**Everything else is clustered by normalised shape.** Each candidate is reduced to a signature that
is invariant to position, scale and rotation, so the codebook that maps signatures to classes works
for any drawing template rather than the one it was built on. The codebook is built by clustering a
drawing's own symbols and labelling the exemplars, so a new template produces new clusters rather
than silent misclassification.

An explicit ``unknown`` class is mandatory. Forcing an unrecognised shape into the nearest known
class is how template overfit becomes invisible.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

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

    Unlabelled: every instance comes out as ``unknown`` with its signature attached. Labels are
    applied by :func:`apply_codebook`, which keeps recognition separate from the vocabulary and
    means a new drawing template yields new signatures rather than confident wrong answers.
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
        if p.kind is Kind.SYMBOL
        and p.is_black
        and 1.0 <= p.bbox.diagonal / scale.module <= 40.0
    ]
    if not candidates:
        return []

    # Bucket by a coarse grid so only plausible neighbours are ever compared.
    cell = max(gap, 1e-6)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, prim in enumerate(candidates):
        c = prim.bbox.centre
        buckets[(int(c.x // cell), int(c.y // cell))].append(i)

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

    for (cx, cy), members in buckets.items():
        neighbourhood = [
            j
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for j in buckets.get((cx + dx, cy + dy), ())
        ]
        for i in members:
            bi = candidates[i].bbox.expanded(gap / 2)
            for j in neighbourhood:
                if j <= i:
                    continue
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
            min(p.bbox.x0 for p in parts), min(p.bbox.y0 for p in parts),
            max(p.bbox.x1 for p in parts), max(p.bbox.y1 for p in parts),
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


def signature_histogram(symbols: list[Symbol]) -> dict[str, int]:
    """How many instances share each signature. The input to codebook labelling."""
    counts: dict[str, int] = defaultdict(int)
    for sym in symbols:
        counts[sym.signature] += 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


@dataclass
class Codebook:
    """Signature to class vocabulary, built once per template and committed."""

    entries: dict[str, str] = field(default_factory=dict)
    source: str = ""

    @classmethod
    def load(cls, path: str | Path) -> Codebook:
        p = Path(path)
        if not p.exists():
            return cls(entries={}, source=str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(entries=dict(data.get("entries", {})), source=str(p))

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Sorted so the committed artifact is stable across runs.
        payload = {"entries": dict(sorted(self.entries.items()))}
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def label(self, signature: str) -> str | None:
        return self.entries.get(signature)


def apply_codebook(symbols: list[Symbol], codebook: Codebook) -> list[Symbol]:
    """Attach classes from the codebook, leaving unmatched instances explicitly unknown."""
    out: list[Symbol] = []
    for sym in symbols:
        if sym.symbol_class != UNKNOWN:
            out.append(sym)
            continue
        label = codebook.label(sym.signature)
        out.append(
            sym
            if label is None
            else Symbol(
                id=sym.id,
                page_index=sym.page_index,
                bbox=sym.bbox,
                signature=sym.signature,
                symbol_class=label,
                confidence=0.8,
                diameter_modules=sym.diameter_modules,
                member_indices=sym.member_indices,
            )
        )
    return out


def coverage(symbols: list[Symbol]) -> float:
    """Fraction of instances carrying a class. Reported rather than optimised away."""
    if not symbols:
        return 1.0
    known = sum(1 for s in symbols if s.symbol_class != UNKNOWN)
    return known / len(symbols)


def dedupe(symbols: list[Symbol], scale: Scale, tol: float = 0.5) -> list[Symbol]:
    """Drop instances whose centres coincide, keeping the most confident.

    A symbol is often drawn as several paths, so the same object can be nominated more than once.
    """
    radius = scale.u(tol)
    kept: list[Symbol] = []
    for sym in sorted(symbols, key=lambda s: (-s.confidence, s.id)):
        if any(
            sym.centre.dist(k.centre) <= radius
            and abs(sym.bbox.width - k.bbox.width) <= radius
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

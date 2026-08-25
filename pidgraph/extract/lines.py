"""Line tracing: recover conductors from drawn segments.

Three decisions here carry most of the risk in the whole pipeline.

**Merging happens in polar space.** Collinear runs are grouped by ``(rho, theta)`` rather than by
axis-aligned buckets. Axis-aligned bucketing is faster and works on most of a sheet, but silently
drops every diagonal -- and diagonals are common in cooler and exchanger geometry, so the result is
an orphaned subgraph with no error raised.

**Dash typing is geometric, not declarative -- and only partially reliable.** Many producers
simulate a dashed line with a run of short solid strokes and still report an empty dash array, so
the declared attribute cannot be trusted. Typing keys on the statistics of the gaps between
collinear pieces. Measured on the sample this recovers only a handful of runs: an individual dash
is shorter than the minimum length that separates a conductor from a glyph mark, so most dashes
never reach this stage as conductors at all. Line *role* is therefore settled downstream by what a
conductor connects -- a run between an instrument and a process line is a signal line whatever its
drawn style -- and the geometric result is treated as corroboration rather than as the decision.

**Crossings are not junctions.** Two conductors crossing without a jump are unconnected. Emitting a
junction there fabricates an edge, and a fabricated edge is structurally identical to a real one --
nothing downstream can detect it. Connectivity comes from endpoint proximity only.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.primitives import BBox, Kind, Point, Primitive, Segment


class LineStyle(StrEnum):
    SOLID = "solid"
    DASHED = "dashed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Polyline:
    """A merged conductor run."""

    id: int
    page_index: int
    start: Point
    end: Point
    style: LineStyle
    piece_count: int
    total_ink: float
    bridged_gaps: tuple[float, ...]
    """Gaps that were closed to form this run. Retained so a wrong bridge is auditable."""
    member_ids: tuple[int, ...] = ()
    """Ids of the pieces a chained run absorbed, so a rejected chain can give them back."""

    @property
    def length(self) -> float:
        return self.start.dist(self.end)

    @property
    def angle(self) -> float:
        return math.atan2(self.end.y - self.start.y, self.end.x - self.start.x) % math.pi

    @property
    def bbox(self) -> BBox:
        return BBox(
            min(self.start.x, self.end.x),
            min(self.start.y, self.end.y),
            max(self.start.x, self.end.x),
            max(self.start.y, self.end.y),
        )

    def endpoints(self) -> tuple[Point, Point]:
        return self.start, self.end


def _polar(seg: Segment) -> tuple[float, float]:
    """``(theta, rho)`` of the infinite line through a segment.

    ``theta`` is folded to ``[0, pi)`` so a segment and its reverse land together; ``rho`` is the
    signed perpendicular offset from the origin.
    """
    theta = seg.angle
    rho = seg.a.x * math.sin(theta) - seg.a.y * math.cos(theta)
    return theta, rho


def _collinear_key(seg: Segment, angle_tol: float, offset_tol: float) -> tuple[int, int]:
    theta, rho = _polar(seg)
    return (round(theta / angle_tol), round(rho / offset_tol))


def _project(point: Point, theta: float) -> float:
    """Position along a line of direction ``theta``."""
    return point.x * math.cos(theta) + point.y * math.sin(theta)


def merge(
    prims: list[Primitive],
    scale: Scale,
    page_index: int,
    angle_tol_deg: float = 1.5,
    bridge: float = 1.0,
) -> list[Polyline]:
    """Merge collinear conductor segments into runs.

    ``bridge`` is in modules and bounds how far a gap may be closed. Every closed gap is recorded
    on the resulting run: bridging is the single most error-prone step here, and an unrecorded
    bridge is indistinguishable from a genuinely continuous line.
    """
    angle_tol = math.radians(angle_tol_deg)
    offset_tol = scale.u(0.6)
    bridge_max = scale.u(bridge)

    buckets: dict[tuple[int, int], list[Segment]] = defaultdict(list)
    for prim in prims:
        if prim.kind is not Kind.PIPE:
            continue
        for seg in prim.segments:
            if seg.length <= 0:
                continue
            buckets[_collinear_key(seg, angle_tol, offset_tol)].append(seg)

    out: list[Polyline] = []
    next_id = 0
    for key in sorted(buckets):
        segs = buckets[key]
        theta = statistics.median(s.angle for s in segs)

        # Order every endpoint along the shared direction, then walk it, splitting where a gap
        # exceeds what we are willing to bridge.
        spans: list[tuple[float, float, Segment]] = []
        for seg in segs:
            pa, pb = _project(seg.a, theta), _project(seg.b, theta)
            spans.append((min(pa, pb), max(pa, pb), seg))
        # Key on the projection only: Segment is deliberately not orderable.
        spans.sort(key=lambda span: (span[0], span[1]))

        run: list[tuple[float, float, Segment]] = []
        gaps: list[float] = []
        reach = None
        for span in spans:
            if reach is not None and span[0] - reach > bridge_max:
                out.append(_emit(next_id, page_index, run, theta, gaps, scale))
                next_id += 1
                run, gaps = [], []
                reach = None
            if reach is not None and span[0] > reach:
                gaps.append(span[0] - reach)
            run.append(span)
            reach = max(reach if reach is not None else span[1], span[1])
        if run:
            out.append(_emit(next_id, page_index, run, theta, gaps, scale))
            next_id += 1

    return [p for p in out if p.length > scale.u(0.5)]


def _emit(
    line_id: int,
    page_index: int,
    run: list[tuple[float, float, Segment]],
    theta: float,
    gaps: list[float],
    scale: Scale,
) -> Polyline:
    points: list[Point] = []
    ink = 0.0
    for _, _, seg in run:
        points += [seg.a, seg.b]
        ink += seg.length
    lo = min(points, key=lambda p: _project(p, theta))
    hi = max(points, key=lambda p: _project(p, theta))
    return Polyline(
        id=line_id,
        page_index=page_index,
        start=lo,
        end=hi,
        style=classify_style(len(run), gaps, ink, lo.dist(hi), scale),
        piece_count=len(run),
        total_ink=ink,
        bridged_gaps=tuple(round(g, 3) for g in gaps),
    )


def classify_style(
    pieces: int,
    gaps: list[float],
    ink: float,
    span: float,
    scale: Scale,
    min_pieces: int = 4,
) -> LineStyle:
    """Solid or dashed, from the statistics of the gaps between collinear pieces.

    A dashed line is many short pieces separated by regular small gaps, so the discriminators are
    piece count, gap regularity, and the fraction of the span actually inked. A solid line that
    happens to be split by a symbol crossing has few pieces and irregular gaps, and is not
    mistaken for dashed.
    """
    if pieces < min_pieces or not gaps or span <= 0:
        return LineStyle.SOLID
    median_gap = statistics.median(gaps)
    if not (scale.u(0.2) <= median_gap <= scale.u(3.5)):
        return LineStyle.SOLID
    if len(gaps) >= 3:
        spread = statistics.pstdev(gaps) / max(median_gap, 1e-9)
        if spread > 0.85:
            return LineStyle.SOLID
    if ink / span > 0.9:
        return LineStyle.SOLID
    return LineStyle.DASHED


def chain_dashes(
    lines: list[Polyline],
    scale: Scale,
    angle_tol_deg: float = 1.5,
    max_gap: float = 4.0,
    min_pieces: int = 4,
) -> list[Polyline]:
    """Second pass: chain short collinear runs into dashed conductors.

    Structural merging deliberately bridges only very small gaps, because a generous bridge joins
    genuinely separate conductors. But a simulated dash has gaps *larger* than that bound, so
    dashed lines survive the first pass as a scatter of short runs rather than as one gapped run.

    This pass looks specifically for that signature -- four or more short collinear runs at
    regular spacing -- and merges them, which is the only way to recover a dashed conductor when
    the producer does not declare dash arrays. Runs that do not form such a chain are returned
    untouched.
    """
    angle_tol = math.radians(angle_tol_deg)
    offset_tol = scale.u(0.6)
    gap_max = scale.u(max_gap)
    short = scale.u(6.0)

    buckets: dict[tuple[int, int], list[Polyline]] = defaultdict(list)
    passthrough: list[Polyline] = []
    for line in lines:
        if line.length > short:
            passthrough.append(line)
            continue
        seg = Segment(line.start, line.end)
        buckets[_collinear_key(seg, angle_tol, offset_tol)].append(line)

    out = list(passthrough)
    next_id = max((line.id for line in lines), default=0) + 1
    for key in sorted(buckets):
        group = buckets[key]
        if len(group) < min_pieces:
            out.extend(group)
            continue
        theta = statistics.median(line.angle for line in group)
        group.sort(key=lambda line: _project(line.start, theta))

        chain: list[Polyline] = []
        gaps: list[float] = []
        for line in group:
            if chain:
                gap = _project(line.start, theta) - _project(chain[-1].end, theta)
                if gap > gap_max:
                    out.extend(_flush_chain(chain, gaps, theta, scale, next_id, min_pieces))
                    next_id += 1
                    chain, gaps = [], []
                elif gap > 0:
                    gaps.append(gap)
            chain.append(line)
        out.extend(_flush_chain(chain, gaps, theta, scale, next_id, min_pieces))
        next_id += 1
    return out


GLYPH_CANDIDATE_BASE = 1_000_000
"""Id offset for glyph-derived dash candidates, so they are distinguishable in chain output."""


def glyph_dash_candidates(
    prims: list, scale: Scale, page_index: int
) -> tuple[list[Polyline], dict[int, int]]:
    """Single-stroke glyph marks recast as dash-chain candidates.

    A simulated dash shorter than two modules classifies as a glyph -- it *is* a small black
    mark -- and from a single mark the two are genuinely indistinguishable. The distinction is
    structural: four or more of them, collinear at regular pitch, are a dashed conductor, and no
    string of lettering has that signature. These candidates go through the same chaining and
    regularity tests as any other dash; a candidate that fails to chain is dropped from the
    conductor set entirely, because a lone letter stroke must not become a line.

    Returns the candidates and a map of candidate id to primitive index, so the marks a chain
    consumed can be removed from the text pool.
    """
    from pidgraph.extract.primitives import Kind

    out: list[Polyline] = []
    mapping: dict[int, int] = {}
    lo, hi = scale.u(0.2), scale.u(2.0)
    for prim in prims:
        if prim.kind is not Kind.GLYPH or not prim.is_black or prim.filled or prim.curves:
            continue
        if len(prim.segments) != 1:
            continue
        seg = prim.segments[0]
        if not (lo <= seg.length <= hi):
            continue
        candidate_id = GLYPH_CANDIDATE_BASE + len(out)
        out.append(
            Polyline(
                id=candidate_id,
                page_index=page_index,
                start=seg.a,
                end=seg.b,
                style=LineStyle.SOLID,
                piece_count=1,
                total_ink=seg.length,
                bridged_gaps=(),
            )
        )
        mapping[candidate_id] = prim.index
    return out, mapping


def _flush_chain(
    chain: list[Polyline],
    gaps: list[float],
    theta: float,
    scale: Scale,
    line_id: int,
    min_pieces: int,
) -> list[Polyline]:
    """Emit a chain as one dashed run, or return its members unchanged."""
    if len(chain) < min_pieces or not gaps:
        return list(chain)
    points = [p for line in chain for p in (line.start, line.end)]
    lo = min(points, key=lambda p: _project(p, theta))
    hi = max(points, key=lambda p: _project(p, theta))
    ink = sum(line.total_ink for line in chain)
    style = classify_style(len(chain), gaps, ink, lo.dist(hi), scale, min_pieces=min_pieces)
    if style is not LineStyle.DASHED:
        return list(chain)
    return [
        Polyline(
            id=line_id,
            page_index=chain[0].page_index,
            start=lo,
            end=hi,
            style=LineStyle.DASHED,
            piece_count=len(chain),
            total_ink=ink,
            bridged_gaps=tuple(round(g, 3) for g in gaps),
            member_ids=tuple(line.id for line in chain),
        )
    ]


@dataclass(frozen=True)
class Junction:
    """A place where conductor endpoints meet. Never inferred from a crossing."""

    point: Point
    line_ids: tuple[int, ...]


def junctions(lines: list[Polyline], scale: Scale, tol: float = 0.8) -> list[Junction]:
    """Group coincident endpoints.

    Only endpoints participate. A point where one line's *interior* crosses another is ignored,
    because a crossing without a jump symbol means the conductors pass over one another. Treating
    it as a junction merges two unrelated process lines, and no downstream confidence score can
    recover from that.
    """
    radius = scale.u(tol)
    entries: list[tuple[Point, int]] = []
    for line in lines:
        entries.append((line.start, line.id))
        entries.append((line.end, line.id))

    used = [False] * len(entries)
    out: list[Junction] = []
    for i, (point, _) in enumerate(entries):
        if used[i]:
            continue
        group = [i]
        used[i] = True
        for j in range(i + 1, len(entries)):
            if not used[j] and point.dist(entries[j][0]) <= radius:
                group.append(j)
                used[j] = True
        if len(group) < 2:
            continue
        ids = sorted({entries[k][1] for k in group})
        if len(ids) < 2:
            continue
        xs = [entries[k][0].x for k in group]
        ys = [entries[k][0].y for k in group]
        out.append(Junction(Point(sum(xs) / len(xs), sum(ys) / len(ys)), tuple(ids)))
    return out


def stats(lines: list[Polyline]) -> dict[str, float]:
    if not lines:
        return {}
    styles = defaultdict(int)
    for line in lines:
        styles[line.style.value] += 1
    lengths = sorted(line.length for line in lines)
    bridged = sum(1 for line in lines if line.bridged_gaps)
    return {
        "count": float(len(lines)),
        "solid": float(styles["solid"]),
        "dashed": float(styles["dashed"]),
        "bridged": float(bridged),
        "median_length": lengths[len(lengths) // 2],
        "max_length": lengths[-1],
    }

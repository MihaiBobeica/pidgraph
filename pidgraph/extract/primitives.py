"""Primitive extraction: the one place the page transform is applied.

Geometry comes out of a PDF in unrotated media-box coordinates while rendering happens in display
coordinates. Confusing the two raises nothing -- clipping simply returns an empty image and every
overlay lands in the wrong place. So the transform is applied exactly here, and nothing downstream
ever sees an untransformed coordinate.

Classification order is load-bearing and is documented on :func:`classify`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pidgraph.extract.calibrate import Scale


class Kind(StrEnum):
    """What a primitive is, before any semantic interpretation."""

    PIPE = "pipe"
    """A drawn conductor: a process line, a signal line, or a leader."""
    GLYPH = "glyph"
    """A text mark. Not yet a character -- recognition happens later."""
    SYMBOL = "symbol"
    """Symbol-scale geometry: valve bodies, instrument circles, fittings."""
    FRAME = "frame"
    """Border, zone grid, title block, logo. Drawing furniture, not content."""
    OTHER = "other"


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def dist(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def centre(self) -> Point:
        return Point((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)

    def contains(self, p: Point) -> bool:
        return self.x0 <= p.x <= self.x1 and self.y0 <= p.y <= self.y1

    def intersects(self, other: BBox) -> bool:
        return not (
            self.x1 < other.x0 or other.x1 < self.x0 or self.y1 < other.y0 or other.y1 < self.y0
        )

    def expanded(self, margin: float) -> BBox:
        return BBox(self.x0 - margin, self.y0 - margin, self.x1 + margin, self.y1 + margin)


@dataclass(frozen=True)
class Segment:
    a: Point
    b: Point

    @property
    def length(self) -> float:
        return self.a.dist(self.b)

    @property
    def angle(self) -> float:
        """Direction in radians, folded to [0, pi) so a segment equals its reverse."""
        return math.atan2(self.b.y - self.a.y, self.b.x - self.a.x) % math.pi


@dataclass(frozen=True)
class Primitive:
    """One drawn path, transformed into display space and classified."""

    index: int
    page_index: int
    kind: Kind
    bbox: BBox
    segments: tuple[Segment, ...]
    curves: int
    stroke_width: float
    filled: bool
    colour: tuple[float, ...] | None
    closed: bool

    @property
    def total_length(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def longest_segment(self) -> float:
        return max((s.length for s in self.segments), default=0.0)

    @property
    def is_black(self) -> bool:
        """Black ink. Coloured marks on an engineering drawing are usually branding."""
        if self.colour is None:
            return True
        return all(c < 0.15 for c in self.colour[:3])


def _transform(page: Any) -> Any:
    """The page's own rotation matrix. Applied once, here."""
    return page.rotation_matrix


def _pt(raw: Any, matrix: Any) -> Point:
    moved = raw * matrix
    return Point(float(moved.x), float(moved.y))


def classify(
    bbox: BBox,
    segments: tuple[Segment, ...],
    curves: int,
    filled: bool,
    scale: Scale,
) -> Kind:
    """Assign a primitive kind. **The order of these tests is load-bearing.**

    The pipe test must run before the glyph test. Short connector stubs -- exactly the segments
    that carry connectivity between a symbol and a header -- are glyph-sized by bounding box, so
    testing for glyphs first silently swallows them and the graph loses its edges without any
    error being raised.
    """
    diag = bbox.diagonal
    longest = max((s.length for s in segments), default=0.0)
    minor = min(bbox.width, bbox.height)

    # 1. Pipes. Some producers draw conductors as degenerate *filled* rectangles rather than
    #    strokes; others stroke them. Both are caught: a thin extent with a long run.
    if longest > scale.u(2.0) and minor <= scale.u(2.5):
        return Kind.PIPE
    if filled and minor <= scale.u(1.0) and longest > scale.u(1.5):
        return Kind.PIPE

    # 2. Frame furniture. Runs far longer than any symbol are borders and rules.
    if longest > scale.u(60.0):
        return Kind.FRAME

    # 3. Glyphs. Small marks with only short strokes.
    if diag < scale.u(5.0) and longest < scale.u(1.5):
        return Kind.GLYPH

    # 4. Symbol-scale geometry, including anything with curvature at plausible size.
    if diag <= scale.u(30.0) or curves:
        return Kind.SYMBOL

    return Kind.OTHER


def extract_page(page: Any, scale: Scale, page_index: int) -> list[Primitive]:
    """Transform and classify every path on a page."""
    matrix = _transform(page)
    out: list[Primitive] = []

    for index, path in enumerate(page.get_drawings()):
        segments: list[Segment] = []
        curves = 0
        xs: list[float] = []
        ys: list[float] = []

        for item in path.get("items", ()):
            if item[0] == "l":
                a, b = _pt(item[1], matrix), _pt(item[2], matrix)
                segments.append(Segment(a, b))
                xs += [a.x, b.x]
                ys += [a.y, b.y]
            elif item[0] == "c":
                curves += 1
                for raw in item[1:]:
                    p = _pt(raw, matrix)
                    xs.append(p.x)
                    ys.append(p.y)
            elif item[0] == "re":
                rect = item[1] * matrix
                corners = [
                    Point(float(rect.x0), float(rect.y0)),
                    Point(float(rect.x1), float(rect.y0)),
                    Point(float(rect.x1), float(rect.y1)),
                    Point(float(rect.x0), float(rect.y1)),
                ]
                for i in range(4):
                    segments.append(Segment(corners[i], corners[(i + 1) % 4]))
                xs += [c.x for c in corners]
                ys += [c.y for c in corners]
            elif item[0] == "qu":
                quad = item[1] * matrix
                for raw in (quad.ul, quad.ur, quad.lr, quad.ll):
                    xs.append(float(raw.x))
                    ys.append(float(raw.y))

        if not xs or not ys:
            continue

        bbox = BBox(min(xs), min(ys), max(xs), max(ys))
        fill = path.get("fill")
        colour = path.get("color") or fill
        filled = fill is not None
        kind = classify(bbox, tuple(segments), curves, filled, scale)

        out.append(
            Primitive(
                index=index,
                page_index=page_index,
                kind=kind,
                bbox=bbox,
                segments=tuple(segments),
                curves=curves,
                stroke_width=round(float(path.get("width") or 0.0), 4),
                filled=filled,
                colour=tuple(colour) if colour is not None else None,
                closed=bool(path.get("closePath")),
            )
        )

    return out

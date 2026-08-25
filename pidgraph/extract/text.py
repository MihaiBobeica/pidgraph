"""Text region recovery.

Segmentation -- deciding which marks form one string -- is normally the hardest part of reading an
engineering drawing, and it is the part that most often fails silently. Strategies are ranked by
what the page actually offers:

1. **Structural hints.** Some producers publish one marker annotation per text entity, giving the
   region and its orientation exactly. Where present this is free and near-perfect.
2. **Anisotropic clustering.** Otherwise, group glyph marks with a generous tolerance *along* the
   text direction and a tight one *across* it. An isotropic tolerance fragments a drawing into
   two-character pieces, shattering every tag.

Recognition -- turning a region into characters -- is a separate concern and lives elsewhere. This
module answers only "where is text, and which way does it run".
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.primitives import BBox, Kind, Point, Primitive

Orientation = Literal["horizontal", "vertical"]
Source = Literal["structural", "clustered"]


@dataclass(frozen=True)
class TextRegion:
    """A run of marks forming one string. The string itself is not yet known."""

    bbox: BBox
    orientation: Orientation
    source: Source
    mark_count: int
    page_index: int
    text: str | None = None
    """The recognised string, once recognition has run. None means unread, which downstream code
    must treat differently from empty: an unread label is an extraction gap, not evidence."""
    text_confidence: float = 0.0

    def with_text(self, text: str, confidence: float) -> TextRegion:
        return TextRegion(
            bbox=self.bbox, orientation=self.orientation, source=self.source,
            mark_count=self.mark_count, page_index=self.page_index,
            text=text, text_confidence=confidence,
        )

    @property
    def centre(self) -> Point:
        return self.bbox.centre

    @property
    def length(self) -> float:
        """Extent along the reading direction."""
        return self.bbox.width if self.orientation == "horizontal" else self.bbox.height

    @property
    def height(self) -> float:
        """Extent across the reading direction -- the text height."""
        return self.bbox.height if self.orientation == "horizontal" else self.bbox.width


def _orientation(bbox: BBox) -> Orientation:
    return "horizontal" if bbox.width >= bbox.height else "vertical"


def structural_regions(page: Any, page_index: int) -> list[TextRegion]:
    """Text regions published by the producing application, if any.

    The marker annotations carry a rectangle but *no* content -- they locate text, they do not
    read it. A truthiness check on the content field therefore yields zero regions silently,
    which is why the filter keys on the annotation's title and the absence of content.
    """
    out: list[TextRegion] = []
    try:
        annots = page.annots()
    except Exception:
        return out
    if annots is None:
        return out

    matrix = page.rotation_matrix
    for annot in annots:
        info = annot.info or {}
        title = (info.get("title") or "").lower()
        if (info.get("content") or "").strip():
            continue  # a real comment, not a layout hint
        if "text" not in title and "shx" not in title:
            continue
        rect = annot.rect * matrix
        bbox = BBox(
            min(rect.x0, rect.x1), min(rect.y0, rect.y1),
            max(rect.x0, rect.x1), max(rect.y0, rect.y1),
        )
        if bbox.width <= 0 or bbox.height <= 0:
            continue
        out.append(
            TextRegion(
                bbox=bbox,
                orientation=_orientation(bbox),
                source="structural",
                mark_count=0,
                page_index=page_index,
            )
        )
    return out


def _dominant_axis(marks: list[Primitive]) -> Orientation:
    """Which way this group of marks reads, from the spread of their centres."""
    if len(marks) < 2:
        return "horizontal"
    xs = [m.bbox.centre.x for m in marks]
    ys = [m.bbox.centre.y for m in marks]
    return "horizontal" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "vertical"


def cluster_regions(
    marks: list[Primitive],
    scale: Scale,
    page_index: int,
    along: float = 1.6,
    across: float = 0.5,
) -> list[TextRegion]:
    """Group glyph marks into runs with an anisotropic tolerance.

    ``along`` and ``across`` are in modules. The asymmetry is the whole point: characters in a
    string are close along the baseline and separated across it, so a single isotropic radius
    either fragments strings or merges adjacent lines. Both orientations are grown independently
    and the better-supported grouping wins, because a drawing carries text at 0 and 90 degrees.
    """
    if not marks:
        return []

    best: list[TextRegion] = []
    for orientation in ("horizontal", "vertical"):
        eps_x = scale.u(along if orientation == "horizontal" else across)
        eps_y = scale.u(across if orientation == "horizontal" else along)

        # Bucket by the across-axis first so only plausible neighbours are ever compared.
        buckets: dict[int, list[Primitive]] = defaultdict(list)
        for mark in marks:
            c = mark.bbox.centre
            key = int((c.y if orientation == "horizontal" else c.x) // max(eps_y, 1e-6))
            buckets[key].append(mark)

        groups: list[list[Primitive]] = []
        consumed: set[int] = set()
        for key in sorted(buckets):
            # The +1 bucket catches marks straddling a boundary, but each mark may join only one
            # row: without the consumed set every straddler is emitted twice, producing
            # overlapping regions that are recognised twice and can label two different nodes
            # with the same tag.
            row = sorted(
                (
                    m
                    for m in buckets[key] + buckets.get(key + 1, [])
                    if id(m) not in consumed
                ),
                key=lambda m: m.bbox.centre.x if orientation == "horizontal" else m.bbox.centre.y,
            )
            for m in row:
                consumed.add(id(m))
            current: list[Primitive] = []
            previous: float | None = None
            for mark in row:
                c = mark.bbox.centre
                pos = c.x if orientation == "horizontal" else c.y
                if previous is not None and pos - previous > eps_x:
                    if current:
                        groups.append(current)
                    current = []
                current.append(mark)
                previous = pos
            if current:
                groups.append(current)

        regions = []
        for group in groups:
            if not group:
                continue
            bbox = BBox(
                min(m.bbox.x0 for m in group), min(m.bbox.y0 for m in group),
                max(m.bbox.x1 for m in group), max(m.bbox.y1 for m in group),
            )
            regions.append(
                TextRegion(
                    bbox=bbox,
                    orientation=_dominant_axis(group),
                    source="clustered",
                    mark_count=len(group),
                    page_index=page_index,
                )
            )
        # Prefer the grouping that produces longer runs: fragmentation is the failure mode.
        if not best or _mean_marks(regions) > _mean_marks(best):
            best = regions
    return best


def _mean_marks(regions: list[TextRegion]) -> float:
    if not regions:
        return 0.0
    return sum(r.mark_count for r in regions) / len(regions)


def recover(
    page: Any,
    marks: list[Primitive],
    scale: Scale,
    page_index: int,
    content: BBox | None = None,
) -> tuple[list[TextRegion], str]:
    """Recover text regions using the best strategy the page supports.

    ``content`` restricts the result to the drawing area. Structural hints are published for
    *every* text entity on the sheet, including the zone-grid numerals down the margins and the
    title-block fields -- so without this filter the recogniser spends its effort on border
    numbering and the graph acquires labels that are not annotation at all.

    Returns the regions and the name of the strategy used, so the choice is recorded on the run
    rather than being invisible.
    """
    structural = structural_regions(page, page_index)
    if content is not None:
        structural = [r for r in structural if content.contains(r.centre)]
    if len(structural) >= 10:
        covered = _coverage(structural, marks)
        if covered >= 0.6:
            return structural, f"structural ({covered:.0%} of marks covered)"
        # Hints exist but miss too much; fill the gaps by clustering what they do not cover.
        uncovered = [
            m for m in marks if not any(r.bbox.contains(m.bbox.centre) for r in structural)
        ]
        extra = cluster_regions(uncovered, scale, page_index)
        how = f"structural+clustered ({covered:.0%} covered, {len(extra)} added)"
        return structural + extra, how
    return cluster_regions(marks, scale, page_index), "clustered"


def _coverage(regions: list[TextRegion], marks: list[Primitive]) -> float:
    if not marks:
        return 1.0
    inside = sum(
        1 for m in marks if any(r.bbox.contains(m.bbox.centre) for r in regions)
    )
    return inside / len(marks)


def glyph_marks(prims: list[Primitive]) -> list[Primitive]:
    """Black glyph-scale marks. Colour is excluded because branding is not text."""
    return [p for p in prims if p.kind is Kind.GLYPH and p.is_black]


def height_stats(regions: list[TextRegion]) -> dict[str, float]:
    """Text-height distribution. Standards assign different heights to different roles."""
    heights = sorted(r.height for r in regions if r.height > 0)
    if not heights:
        return {}
    return {
        "count": float(len(heights)),
        "min": heights[0],
        "median": heights[len(heights) // 2],
        "p90": heights[min(len(heights) - 1, int(len(heights) * 0.9))],
        "max": heights[-1],
        "mean": math.fsum(heights) / len(heights),
    }

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

import heapq
import itertools
import math
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
    marks: tuple = ()
    """The vector marks the region was built from. Empty for structural regions until the
    containing marks are collected; the vector matcher reads from these."""

    def with_text(self, text: str, confidence: float) -> TextRegion:
        return TextRegion(
            bbox=self.bbox,
            orientation=self.orientation,
            source=self.source,
            mark_count=self.mark_count,
            page_index=self.page_index,
            text=text,
            text_confidence=confidence,
            marks=self.marks,
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
            min(rect.x0, rect.x1),
            min(rect.y0, rect.y1),
            max(rect.x0, rect.x1),
            max(rect.y0, rect.y1),
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


def _split_across(
    group: list[Primitive], orientation: str, eps: float
) -> list[list[Primitive]]:
    """Re-band a group along its across-axis using only its own marks.

    The same interval single-link rule the page-level banding uses, but confined to the group:
    page-level bands chain through a running maximum, so marks elsewhere in the stripe can
    bridge rows that, taken alone, separate cleanly."""
    def interval(m: Primitive) -> tuple[float, float]:
        box = m.bbox
        return (box.y0, box.y1) if orientation == "horizontal" else (box.x0, box.x1)

    parts: list[list[Primitive]] = []
    hi: float | None = None
    for mark in sorted(group, key=lambda m: interval(m)[0]):
        lo, mark_hi = interval(mark)
        if hi is None or lo > hi + eps:
            parts.append([])
            hi = mark_hi
        else:
            hi = max(hi, mark_hi)
        parts[-1].append(mark)
    return parts


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
    band_gap: float = 0.15,
) -> list[TextRegion]:
    """Group glyph marks into runs with an anisotropic tolerance.

    ``along`` is the maximum centre gap between neighbouring characters and ``band_gap`` the
    across-axis gap that separates two rows; both are in modules. The asymmetry is the whole
    point: characters in a string are close along the baseline and separated across it, so a
    single isotropic radius either fragments strings or merges adjacent lines.

    Both orientations are grown independently and the winner is chosen **per row, not per page**.
    A drawing carries text at 0 and 90 degrees *simultaneously* -- one vertical label on a page
    of horizontal tags is normal, and a page-level vote fragments it into unreadable single-mark
    rows. Rows from both orientations compete mark by mark: the better-supported row claims its
    marks. A row that lost marks to a stronger row is not dropped whole -- its unclaimed
    remainder re-enters the competition at its new size, so no mark can fall out of every
    region just because two rows each lost a different neighbour.
    """
    if not marks:
        return []

    candidates: list[tuple[list[Primitive], str]] = []
    for orientation in ("horizontal", "vertical"):
        eps_along = scale.u(along)
        eps_across = scale.u(band_gap)

        # Band the page along the across-axis by interval single-link: a mark joins the current
        # band while its across-extent overlaps the band's (within a small gap). Glyph strokes of
        # one string always overlap transitively -- a dot at the baseline and a quote at the cap
        # line both overlap the full-height strokes between them -- so a band holds whole rows.
        # Fixed-width bucketing cannot do this: a row spans two to three buckets depending on
        # phase, and the marks that fall outside become orphan fragments that read as junk.
        def across_interval(
            m: Primitive, horizontal: bool = orientation == "horizontal"
        ) -> tuple[float, float]:
            box = m.bbox
            return (box.y0, box.y1) if horizontal else (box.x0, box.x1)

        ordered = sorted(marks, key=lambda m: across_interval(m)[0])
        bands: list[list[Primitive]] = []
        band_hi = None
        for mark in ordered:
            lo, hi = across_interval(mark)
            if band_hi is None or lo > band_hi + eps_across:
                bands.append([])
                band_hi = hi
            else:
                band_hi = max(band_hi, hi)
            bands[-1].append(mark)

        groups: list[list[Primitive]] = []
        for band in bands:
            band.sort(
                key=lambda m: m.bbox.centre.x if orientation == "horizontal" else m.bbox.centre.y
            )
            current: list[Primitive] = []
            previous: float | None = None
            for mark in band:
                c = mark.bbox.centre
                pos = c.x if orientation == "horizontal" else c.y
                if previous is not None and pos - previous > eps_along:
                    if current:
                        groups.append(current)
                    current = []
                current.append(mark)
                previous = pos
            if current:
                groups.append(current)

        candidates.extend((group, orientation) for group in groups if group)

    # Row-level competition. Larger rows first -- fragmentation is the failure mode, so the row
    # explaining more marks wins them. Ties go to horizontal, the dominant convention. A queue
    # rather than one pass: a row that lost marks re-enters as its unclaimed remainder, which is
    # strictly smaller, so the loop terminates and every mark gets its best remaining home.
    # The running counter is a heap tiebreaker: primitives are not orderable, so ties on size
    # and orientation must be broken before the comparison ever reaches the group itself.
    tiebreak = itertools.count()
    queue: list[tuple[int, int, int, list[Primitive], str]] = [
        (-len(group), 0 if orientation == "horizontal" else 1, next(tiebreak), group, orientation)
        for group, orientation in candidates
    ]
    heapq.heapify(queue)
    claimed: set[int] = set()
    regions = []
    while queue:
        _, _, _, group, orientation = heapq.heappop(queue)
        remainder = [m for m in group if id(m) not in claimed]
        if not remainder:
            continue
        if len(remainder) != len(group):
            heapq.heappush(
                queue,
                (
                    -len(remainder),
                    0 if orientation == "horizontal" else 1,
                    next(tiebreak),
                    remainder,
                    orientation,
                ),
            )
            continue
        bbox = BBox(
            min(m.bbox.x0 for m in group),
            min(m.bbox.y0 for m in group),
            max(m.bbox.x1 for m in group),
            max(m.bbox.y1 for m in group),
        )
        # Lettering is never shorter than about half a module -- the module is *defined* by
        # lettering height. A "row" whose across-axis extent is a stroke width is a run of
        # line dashes, and recognising it manufactures text where there is none. A single mark
        # is gated on its smaller dimension outright: a lone stroke-thin mark is a dash in any
        # orientation, and gating it by the reading axis lets each dash of a rejected row
        # sneak back in as an opposite-orientation "letter" the height of its own length.
        if len(group) == 1:
            minor = min(bbox.width, bbox.height)
        else:
            minor = bbox.height if orientation == "horizontal" else bbox.width
        if minor < scale.u(0.4):
            continue
        # A candidate whose across-axis extent spans several letter heights is not a string in
        # that orientation -- it is a *stack* of rows: an instrument bubble's letters-over-number
        # tag caught whole by the vertical pass, or two stacked rows bridged into one band by
        # unrelated marks elsewhere in the page stripe (banding tracks a running maximum, so a
        # tall interval anywhere chains rows the bubble itself keeps separate). Reading a stack
        # as one string interleaves the rows into garbage, and because the stack explains more
        # marks than either row it wins the competition exactly where the rows matter most. A
        # genuine string's across extent stays near one letter height, which the tallest member
        # mark bounds, with headroom for shear and jitter. A detected stack is *split* into its
        # across-axis sub-rows -- re-banded over its own marks only, where no foreign bridge
        # exists -- and the parts re-enter the competition; a stack its own marks genuinely
        # bridge cannot split and is dropped.
        if len(group) > 1:
            across = bbox.height if orientation == "horizontal" else bbox.width
            deepest = max(
                (m.bbox.height if orientation == "horizontal" else m.bbox.width) for m in group
            )
            if across > deepest * 1.6:
                parts = _split_across(group, orientation, scale.u(band_gap))
                if len(parts) > 1:
                    for part in parts:
                        heapq.heappush(
                            queue,
                            (
                                -len(part),
                                0 if orientation == "horizontal" else 1,
                                next(tiebreak),
                                part,
                                orientation,
                            ),
                        )
                continue
        claimed.update(id(m) for m in group)
        regions.append(
            TextRegion(
                bbox=bbox,
                orientation=_dominant_axis(group),
                source="clustered",
                mark_count=len(group),
                page_index=page_index,
                marks=tuple(group),
            )
        )
    return regions


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
    # Attach the glyph marks each hint contains: the hint locates the text, the marks *are* the
    # text, and the vector matcher reads from them.
    structural = [_with_contained_marks(region, marks) for region in structural]
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


def _with_contained_marks(region: TextRegion, marks: list[Primitive]) -> TextRegion:
    inside = tuple(m for m in marks if region.bbox.contains(m.bbox.centre))
    if not inside:
        return region
    return TextRegion(
        bbox=region.bbox,
        orientation=region.orientation,
        source=region.source,
        mark_count=len(inside),
        page_index=region.page_index,
        marks=inside,
    )


def _coverage(regions: list[TextRegion], marks: list[Primitive]) -> float:
    if not marks:
        return 1.0
    inside = sum(1 for m in marks if any(r.bbox.contains(m.bbox.centre) for r in regions))
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

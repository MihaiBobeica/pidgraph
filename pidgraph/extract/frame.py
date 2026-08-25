"""Region of interest: separate drawing content from drawing furniture.

A P&ID sheet carries a border, a zone grid, a title block, revision tables and often a vendor logo.
None of it is process content, and left in place it distorts every statistic and floods symbol
matching with false candidates.

Two independent signals do the work, and neither is trusted alone:

* **Colour.** Engineering content is drawn in black; coloured marks are almost always branding.
  Cheap and effective, but a drawing that colours lines by service would lose real content, so
  colour is used to *nominate* a region rather than to delete marks outright.
* **Geometry.** Furniture clusters at the sheet margins and in one corner, and the border is the
  longest run on the page.

Everything removed is retained with a reason, so a mistake is auditable rather than invisible.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.primitives import BBox, Kind, Primitive

ZONE_BAND_MODULES = 7.0
"""Width of the margin band holding zone-grid numerals, in modules.

Sized from the numerals themselves: a zone label is text plus its surrounding rule, which is a few
modules across. Generous rather than tight, because a numeral read as a tag is worse than losing a
little drawing area at the extreme edge.
"""


@dataclass(frozen=True)
class Frame:
    """The furniture found on a sheet, and the content area that remains."""

    content: BBox
    border: BBox | None
    excluded: tuple[BBox, ...]
    reasons: tuple[str, ...]

    def is_content(self, prim: Primitive) -> bool:
        centre = prim.bbox.centre
        if not self.content.contains(centre):
            return False
        return not any(region.contains(centre) for region in self.excluded)


def _colour_clusters(prims: list[Primitive], scale: Scale) -> list[tuple[BBox, int]]:
    """Bounding boxes of contiguous non-black regions, with their mark counts."""
    coloured = [p for p in prims if not p.is_black]
    if not coloured:
        return []

    # Single-link clustering on centres. Logos are compact, so a generous but bounded radius
    # groups one mark cluster without swallowing the sheet.
    radius = scale.u(20.0)
    unassigned = list(coloured)
    clusters: list[list[Primitive]] = []
    while unassigned:
        seed = unassigned.pop()
        group = [seed]
        changed = True
        while changed:
            changed = False
            for candidate in list(unassigned):
                c = candidate.bbox.centre
                if any(c.dist(m.bbox.centre) <= radius for m in group):
                    group.append(candidate)
                    unassigned.remove(candidate)
                    changed = True
        clusters.append(group)

    out = []
    for group in clusters:
        xs0 = min(p.bbox.x0 for p in group)
        ys0 = min(p.bbox.y0 for p in group)
        xs1 = max(p.bbox.x1 for p in group)
        ys1 = max(p.bbox.y1 for p in group)
        out.append((BBox(xs0, ys0, xs1, ys1), len(group)))
    return sorted(out, key=lambda pair: -pair[1])


def _border(prims: list[Primitive], page: BBox, scale: Scale) -> BBox | None:
    """The innermost long rectangle enclosing most of the sheet."""
    candidates = [
        p
        for p in prims
        if p.longest_segment > scale.u(60.0)
        # A border encloses the sheet, so it must span BOTH axes. Width alone admits a header
        # pipe or a title-block band, and cropping to either deletes the real content.
        and p.bbox.width > page.width * 0.5
        and p.bbox.height > page.height * 0.5
    ]
    if not candidates:
        return None
    # The drawing border is the largest such box; nested rules sit just inside it.
    best = max(candidates, key=lambda p: p.bbox.width * p.bbox.height)
    return best.bbox


def detect_frame(prims: list[Primitive], page: BBox, scale: Scale) -> Frame:
    """Find the furniture and the content area.

    Returns the sheet unchanged rather than guessing when the signals are absent -- an
    over-aggressive crop silently deletes process content, which is far worse than leaving a
    border in.
    """
    reasons: list[str] = []
    excluded: list[BBox] = []

    border = _border(prims, page, scale)
    if border is not None:
        # A drawing border is usually a nested pair of rules with the zone-grid numerals banded
        # between them, so stepping just inside the outer rule still leaves the numbering in the
        # content area -- where it is indistinguishable from annotation and gets recognised as
        # tags. The inset clears that band. It is expressed in modules, so it scales.
        content = border.expanded(-scale.u(ZONE_BAND_MODULES))
        if content.width <= 0 or content.height <= 0:
            # The inset inverted the box -- the "border" was too small to be one. Guessing here
            # deletes the drawing; using the full page merely keeps some furniture.
            content = page
            border = None
            reasons.append("border candidate too small after inset; using the full page")
        else:
            reasons.append(
                f"border detected at {border.width:.0f}x{border.height:.0f}pt; "
                f"content inset by {ZONE_BAND_MODULES} modules to clear the zone band"
            )
    else:
        content = page
        reasons.append("no border found; using the full page")

    # A dense coloured cluster is branding. Excluded by region so black content that happens to
    # sit inside it is still removed -- logos are drawn over their own bounding area.
    for bbox, count in _colour_clusters(prims, scale):
        area_ratio = (bbox.width * bbox.height) / max(page.width * page.height, 1e-9)
        if count >= 50 and area_ratio < 0.08:
            excluded.append(bbox)
            reasons.append(f"colour cluster of {count} marks excluded ({area_ratio:.2%} of sheet)")

    return Frame(
        content=content,
        border=border,
        excluded=tuple(excluded),
        reasons=tuple(reasons),
    )


def split(prims: list[Primitive], frame: Frame) -> tuple[list[Primitive], list[Primitive]]:
    """Partition primitives into (content, furniture)."""
    content, furniture = [], []
    for prim in prims:
        (content if frame.is_content(prim) else furniture).append(prim)
    return content, furniture


def summarise(content: list[Primitive], furniture: list[Primitive]) -> str:
    kinds = Counter(p.kind.value for p in content)
    total = len(content) + len(furniture)
    pct = len(furniture) / total if total else 0.0
    return f"content={len(content)} furniture={len(furniture)} ({pct:.0%}) kinds={dict(kinds)}"


__all__ = ["Frame", "Kind", "detect_frame", "split", "summarise"]

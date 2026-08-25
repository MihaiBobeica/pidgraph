"""Capability probing.

The pipeline does not fork on file type. It measures what a page actually offers and lets each
downstream stage pick its own best available strategy. This module produces that measurement.

The distinction matters because real files sit between the extremes. A born-digital vector drawing
routinely carries an embedded logo bitmap and a vestigial text layer; a scan can carry stray vector
annotations. Rules of the form "has an image therefore scanned" or "has text therefore use it"
misroute such files in both directions, which is why every field below is a *magnitude* and every
derived predicate thresholds on it.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Thresholds are fractions and counts, never absolute drawing dimensions -- those are derived
# per drawing by the calibration stage.
MIN_VECTOR_PATHS = 50
"""Below this a page has no usable vector geometry, whatever else it contains."""

MIN_TEXT_LAYER_CHARS = 200
"""A logo footer or a stray watermark is not a text layer. Threshold on volume, not presence."""

RASTER_DOMINANT_AREA = 0.5
"""Embedded raster covering at least half the page means the page *is* an image."""

RASTER_INCIDENTAL_AREA = 0.05
"""Below this the raster is decoration (a logo, a stamp) and says nothing about the page."""


@dataclass(frozen=True)
class PageCapabilities:
    """What one page can actually offer, measured rather than assumed."""

    page_index: int
    width_pt: float
    height_pt: float
    rotation: int

    vector_path_count: int
    line_segment_count: int
    bezier_count: int

    raster_area_ratio: float
    raster_max_dpi: float | None

    text_layer_chars: int
    text_region_count: int
    """Structural text-region hints published by the producing application, if any."""

    has_ocg_layers: bool
    dash_arrays_present: bool

    paint_types: dict[str, int] = field(default_factory=dict)
    """Counts keyed ``"<type>@<width>"``. Reveals whether fills and strokes are used distinctly."""

    stroke_widths: dict[float, int] = field(default_factory=dict)
    colours: int = 0

    # ---- derived predicates -------------------------------------------------------------

    @property
    def has_vector_geometry(self) -> bool:
        return self.vector_path_count >= MIN_VECTOR_PATHS

    @property
    def has_text_layer(self) -> bool:
        return self.text_layer_chars >= MIN_TEXT_LAYER_CHARS

    @property
    def has_text_regions(self) -> bool:
        return self.text_region_count > 0

    @property
    def is_raster_page(self) -> bool:
        """True only when a raster dominates. An incidental logo must not trigger this."""
        return self.raster_area_ratio >= RASTER_DOMINANT_AREA and not self.has_vector_geometry

    @property
    def has_incidental_raster(self) -> bool:
        return 0.0 < self.raster_area_ratio < RASTER_INCIDENTAL_AREA

    @property
    def has_linewidth_signal(self) -> bool:
        """Whether stroke width can discriminate anything.

        A drawing using a single non-zero width carries no line-class information in its
        strokes, so the standards-assigned width hierarchy is unavailable and typing must come
        from geometry instead.
        """
        return len([w for w in self.stroke_widths if w > 0]) >= 2

    @property
    def has_paint_type_signal(self) -> bool:
        """Whether fills and strokes are used as distinct classes.

        Some producers emit long thin *filled* rectangles for one class of object and strokes for
        another. Where that holds, paint type separates them for free.
        """
        kinds = {key.split("@", 1)[0] for key in self.paint_types}
        return len(kinds) >= 2

    def summary(self) -> str:
        bits = [
            f"page {self.page_index}",
            f"{self.width_pt:.0f}x{self.height_pt:.0f}pt rot{self.rotation}",
            f"paths={self.vector_path_count}",
            f"segs={self.line_segment_count}",
            f"text={self.text_layer_chars}c",
            f"regions={self.text_region_count}",
            f"raster={self.raster_area_ratio:.3%}",
        ]
        flags = [
            name
            for name, on in (
                ("vector", self.has_vector_geometry),
                ("text-layer", self.has_text_layer),
                ("text-regions", self.has_text_regions),
                ("dash-arrays", self.dash_arrays_present),
                ("linewidth", self.has_linewidth_signal),
                ("paint-type", self.has_paint_type_signal),
                ("ocg", self.has_ocg_layers),
            )
            if on
        ]
        return " | ".join(bits) + "  [" + (", ".join(flags) or "none") + "]"


def _text_region_hints(page: Any) -> int:
    """Count structural text-region hints.

    Some CAD exporters emit an invisible marker annotation per text entity, giving the region and
    its orientation for free. The content is typically empty -- these locate text, they do not
    read it -- so a truthiness check on the content field silently yields zero. We count the
    markers themselves.
    """
    count = 0
    try:
        annots = page.annots()
    except Exception:
        return 0
    if annots is None:
        return 0
    for annot in annots:
        info = annot.info or {}
        title = (info.get("title") or "").lower()
        # Marker annotations name the producing subsystem in their title, and carry a rect but
        # no contents. Anything with real contents is a human comment, not a layout hint.
        if not (info.get("content") or "").strip() and ("text" in title or "shx" in title):
            count += 1
    return count


def probe_page(page: Any, page_index: int) -> PageCapabilities:
    """Measure one page. Pure: no side effects, no mutation of ``page``."""
    rect = page.rect
    page_area = max(float(rect.width) * float(rect.height), 1e-9)

    drawings = page.get_drawings()
    paint_types: Counter[str] = Counter()
    stroke_widths: Counter[float] = Counter()
    colours: set[tuple] = set()
    lines = beziers = 0
    dashed = False

    for path in drawings:
        width = round(float(path.get("width") or 0.0), 4)
        paint_types[f"{path.get('type', '?')}@{width}"] += 1
        stroke_widths[width] += 1
        dashes = (path.get("dashes") or "").strip()
        # "[] 0" is an explicitly empty dash array -- a producer that simulates dashes with runs
        # of short solid strokes still reports it, so only a populated array counts.
        if dashes and dashes not in ("[] 0", "[]0"):
            dashed = True
        for colour_key in ("color", "fill"):
            value = path.get(colour_key)
            if value is not None:
                colours.add(tuple(value))
        for item in path.get("items", ()):
            if item[0] == "l":
                lines += 1
            elif item[0] == "c":
                beziers += 1

    raster_area = 0.0
    max_dpi: float | None = None
    try:
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if not bbox:
                continue
            w_pt = abs(bbox[2] - bbox[0])
            h_pt = abs(bbox[3] - bbox[1])
            raster_area += w_pt * h_pt
            if w_pt > 0 and info.get("width"):
                max_dpi = max(max_dpi or 0.0, 72.0 * float(info["width"]) / w_pt)
    except Exception:
        pass

    try:
        ocg = bool(page.parent.get_ocgs())
    except Exception:
        ocg = False

    return PageCapabilities(
        page_index=page_index,
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rotation=int(page.rotation),
        vector_path_count=len(drawings),
        line_segment_count=lines,
        bezier_count=beziers,
        raster_area_ratio=min(raster_area / page_area, 1.0),
        raster_max_dpi=max_dpi,
        text_layer_chars=len(page.get_text().strip()),
        text_region_count=_text_region_hints(page),
        has_ocg_layers=ocg,
        dash_arrays_present=dashed,
        paint_types=dict(paint_types.most_common()),
        stroke_widths={w: c for w, c in sorted(stroke_widths.items())},
        colours=len(colours),
    )


def probe_document(path: str | Path) -> list[PageCapabilities]:
    """Measure every page of a document."""
    import pymupdf

    with pymupdf.open(str(path)) as doc:
        return [probe_page(page, index) for index, page in enumerate(doc)]


def rotation_matrix_check(page: Any) -> tuple[float, float, float, float]:
    """Return ``(x_unrot, y_unrot, x_display, y_display)`` for the page's own corner.

    Guards the single highest-cost silent bug in the pipeline: geometry is returned in unrotated
    media-box coordinates while rendering happens in display coordinates. Nothing raises when the
    two are confused -- clipping simply returns an empty image and every overlay lands wrong. The
    transform is applied in exactly one place, and this function is what pins it.
    """
    media = page.mediabox
    x_unrot, y_unrot = float(media.x1), float(media.y0)
    point = fitz_point(x_unrot, y_unrot) * page.rotation_matrix
    return x_unrot, y_unrot, float(point.x), float(point.y)


def fitz_point(x: float, y: float) -> Any:
    import pymupdf

    return pymupdf.Point(x, y)


def is_finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0

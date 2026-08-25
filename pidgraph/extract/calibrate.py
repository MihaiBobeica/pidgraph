"""Scale calibration: recover the drawing's own module.

No absolute dimension is hardcoded anywhere in this pipeline. Drawings are plotted at arbitrary
scales onto arbitrary sheet sizes by arbitrary CAD templates, so a threshold expressed in points is
an assumption about one plot.

Calibration is not arbitrary self-derivation either. Symbol geometry is *normatively* defined in a
per-drawing dimensionless module -- ISA-5.1 calls it a measurement unit (m.u.) and fixes only its
minimum, leaving the actual value a free per-drawing parameter; ISO 81714-1 calls it M and ties line
width to M/10. ISA-5.1 4.1.6 is explicit that symbols must preserve the *ratios* in the tables when
scaled. So the quantity to recover is the module, and everything downstream is a published ratio.

The module is over-determined: three partly independent observables (narrow stroke width, text
height, dominant symbol diameter) each predict it through a different published ratio. Agreement
between them is the confidence signal; disagreement is a loud failure rather than a silent one.

References: docs/assumptions.md STD-04, STD-05, STD-11, STD-12, STD-16, STD-17, STD-20.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

UnitSystem = Literal["ISA", "ISO", "unknown"]

# ---- published ratios ------------------------------------------------------------------------
# ISA-5.1-2009 Table 6.3: signal line 0.2 m.u.  Table 6.1: device/function circle 7 m.u. (8 option).
# ISO 81714-1 6.6: line width = M/10.  ISO 10628-1 5.4.2: ordinary lettering = 1 M, equipment = 2 M.
NARROW_STROKE_PER_MODULE = {"ISA": 0.2, "ISO": 0.1}
SYMBOL_DIAMETER_PER_MODULE = {"ISA": 7.0, "ISO": 7.0}

# Text height is deliberately NOT a module estimator. No published text-to-module or
# text-to-symbol ratio exists (docs/assumptions.md STD-24), and a real drawing carries several
# text sizes whose marks overlap in height with partial glyph strokes -- so the observable is a
# mixture, not a single cap height. It is measured, reported, and used as a sanity gate only.
TARGET_STROKE_PX = 4.0
"""Pixels across the narrowest stroke at the derived render resolution.

Below about 2 px adjacent parallel strokes inside a symbol merge into one blob, which destroys
both symbol matching and glyph legibility. The stroke is the binding constraint for a CAD stroke
font, and unlike text height it is a single well-defined observable."""

SYMBOL_DIAMETER_ACCEPT = (5.0, 10.0)
"""Nominal is 7 (or 8). The window admits both plus real-world spread; outside it we do not claim
to have found an instrument bubble."""

CAP_TO_STROKE_GATE = (3.0, 20.0)
"""ISO 3098 fixes lettering stroke-to-height at h/10 (type B) or h/14 (type A); ISA's own tables
imply nearer 5. Outside this band the stroke estimate is not measuring what we think it is."""

# ISO 128-2 5.1. A narrow stroke landing exactly on one of these is a hint that the producer used a
# fixed plot style, whose widths are absolute and therefore independent of plot scale.
ISO_128_WIDTHS_MM = (0.13, 0.18, 0.25, 0.35, 0.5, 0.7, 1.0, 1.4, 2.0)

MM_PER_PT = 25.4 / 72.0

# Trimmed sheet sizes. ANSI/ARCH in inches, ISO in millimetres. Used only to infer which unit
# system's ratio table applies -- never to infer plot scale, which the page box cannot give us
# ("B-size drawn small" and "D-size plotted at half" are indistinguishable from the box alone).
ANSI_SHEETS_IN = {
    "ANSI_A": (8.5, 11.0), "ANSI_B": (11.0, 17.0), "ANSI_C": (17.0, 22.0),
    "ANSI_D": (22.0, 34.0), "ANSI_E": (34.0, 44.0),
    "ARCH_A": (9.0, 12.0), "ARCH_B": (12.0, 18.0), "ARCH_C": (18.0, 24.0),
    "ARCH_D": (24.0, 36.0), "ARCH_E": (36.0, 48.0),
}
ISO_SHEETS_MM = {
    "ISO_A4": (210.0, 297.0), "ISO_A3": (297.0, 420.0), "ISO_A2": (420.0, 594.0),
    "ISO_A1": (594.0, 841.0), "ISO_A0": (841.0, 1189.0),
}


class CalibrationError(RuntimeError):
    """Calibration could not produce a usable module.

    Raised rather than returning a low-confidence guess, because every downstream threshold is a
    multiple of the module: a wrong module produces confident garbage everywhere.
    """


@dataclass(frozen=True)
class Estimator:
    """One prediction of the module, with the observable it came from."""

    name: str
    module: float
    observable: float
    ratio: float
    trusted: bool = True
    note: str = ""


@dataclass(frozen=True)
class Scale:
    """The recovered scale basis. Every downstream threshold is a multiple of :attr:`module`."""

    unit_system: UnitSystem
    module: float
    sheet: str
    page_width_pt: float
    page_height_pt: float

    narrow_stroke: float | None = None
    text_height: float | None = None
    symbol_diameter: float | None = None

    estimators: tuple[Estimator, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def u(self, multiple: float) -> float:
        """A threshold expressed in modules. The only sanctioned way to get an absolute size."""
        return multiple * self.module

    @property
    def symbol_modules(self) -> float | None:
        """Measured symbol diameter in modules. Nominal 7 (or 8) for a conforming drawing."""
        if self.symbol_diameter is None:
            return None
        return self.symbol_diameter / self.module

    def render_dpi(self, target_stroke_px: float = TARGET_STROKE_PX) -> float:
        """Resolution needed to put ``target_stroke_px`` pixels across the narrowest stroke.

        Derived, never fixed: a drawing at a different plot scale needs a different resolution.
        Keyed to the stroke rather than to text height because the stroke is a single
        well-defined observable, and because merging adjacent strokes destroys symbol matching
        as surely as it destroys legibility.
        """
        default = self.module * NARROW_STROKE_PER_MODULE.get(self.unit_system, 0.2)
        stroke = self.narrow_stroke or default
        return target_stroke_px * 72.0 / stroke

    def summary(self) -> str:
        sym = f"{self.symbol_modules:.2f}" if self.symbol_modules else "n/a"
        return (
            f"{self.sheet} [{self.unit_system}] module={self.module:.4f}pt "
            f"stroke={self.narrow_stroke} text={self.text_height} "
            f"symbol={self.symbol_diameter} ({sym} modules) "
            f"dpi={self.render_dpi():.0f} confidence={self.confidence:.2f}"
        )


# ---- observables -------------------------------------------------------------------------------


def detect_sheet(
    width_pt: float, height_pt: float, tolerance: float = 0.02
) -> tuple[str, UnitSystem]:
    """Match the page box against the standard sheet series.

    Yields a *unit-system prior only*. It cannot recover plot scale, and both series are probed
    because a drawing may be issued on either -- ISO 10628-1 recommends A1 while US process
    practice uses 22x34 in, and those differ by only a few percent on one axis.
    """
    short_pt, long_pt = sorted((width_pt, height_pt))
    short_in, long_in = short_pt / 72.0, long_pt / 72.0
    short_mm, long_mm = short_pt * MM_PER_PT, long_pt * MM_PER_PT

    best: tuple[float, str, UnitSystem] | None = None
    for name, (s, lg) in ANSI_SHEETS_IN.items():
        err = max(abs(short_in - s) / s, abs(long_in - lg) / lg)
        if best is None or err < best[0]:
            best = (err, name, "ISA")
    for name, (s, lg) in ISO_SHEETS_MM.items():
        err = max(abs(short_mm - s) / s, abs(long_mm - lg) / lg)
        if best is None or err < best[0]:
            best = (err, name, "ISO")

    assert best is not None
    err, name, system = best
    if err > tolerance:
        return "custom", "unknown"
    return name, system


def narrow_stroke_width(paths: list[dict[str, Any]]) -> tuple[float | None, dict[float, float]]:
    """Narrowest well-populated stroke width, weighted by how much ink it draws.

    Weighted by path length rather than path count so that a handful of long structural lines is
    not outvoted by thousands of tiny glyph strokes. Returns the width and the full weighted
    histogram, which the caller uses to check for the 4:2:1 hierarchy.
    """
    weights: Counter[float] = Counter()
    for path in paths:
        width = round(float(path.get("width") or 0.0), 4)
        if width <= 0:
            continue
        length = 0.0
        for item in path.get("items", ()):
            if item[0] == "l":
                a, b = item[1], item[2]
                length += math.hypot(b.x - a.x, b.y - a.y)
        weights[width] += max(length, 1e-6)
    if not weights:
        return None, {}
    total = sum(weights.values())
    populated = sorted(w for w, wt in weights.items() if wt / total >= 0.01)
    return (populated[0] if populated else None), dict(sorted(weights.items()))


def _glyph_heights(paths: list[dict[str, Any]], page_span: float) -> list[float]:
    """Heights of glyph-scale marks, as a fraction-free list in drawing units."""
    heights: list[float] = []
    for path in paths:
        rect = path.get("rect")
        if rect is None:
            continue
        h, w = float(rect.height), float(rect.width)
        # Glyph-scale: small relative to the page, and not a degenerate hairline.
        if not (0.0008 * page_span < h < 0.02 * page_span):
            continue
        if w <= 0 or h <= 0:
            continue
        heights.append(round(h, 3))
    return heights


def modal_text_height(paths: list[dict[str, Any]], page_span: float) -> float | None:
    """Modal height of glyph-scale marks -- the smallest common text size.

    Not a cap height and not a module estimator. A drawing carries several text sizes, and in a
    stroke font the individual marks include partial glyphs, so the height distribution is a
    mixture. The mode approximates the *smallest* common annotation size, which is the right
    conservative basis for a legibility sanity check: if that resolves, everything larger does.
    """
    heights = _glyph_heights(paths, page_span)
    if len(heights) < 50:
        return None
    return Counter(heights).most_common(1)[0][0]


def dominant_symbol_diameter(
    paths: list[dict[str, Any]], page_span: float
) -> tuple[float | None, int]:
    """Diameter of the dominant near-circular symbol, found by mode-seeking.

    Found empirically rather than predicted from the module, so it is an *independent* estimator
    rather than a restatement of one. A real P&ID carries tens to hundreds of instrument circles
    at one or two radii, which makes this the strongest single signal in the document.
    """
    diameters: Counter[float] = Counter()
    for path in paths:
        if not any(item[0] == "c" for item in path.get("items", ())):
            continue
        rect = path.get("rect")
        if rect is None:
            continue
        w, h = float(rect.width), float(rect.height)
        if w <= 0 or h <= 0 or abs(w - h) > 0.1 * w:
            continue
        if not (0.004 * page_span < w < 0.06 * page_span):
            continue
        diameters[round(w, 2)] += 1
    if not diameters:
        return None, 0
    value, count = diameters.most_common(1)[0]
    return (value, count) if count >= 5 else (None, count)


def _looks_like_fixed_plot_style(stroke_pt: float) -> bool:
    """Whether a stroke width sits on the ISO 128 series.

    A width landing exactly on the standard series suggests the producer applied a fixed plot
    style, which assigns absolute output widths independent of plot scale -- making the stroke
    useless as a scale proxy even though it stays useful as a line-class signal.
    """
    mm = stroke_pt * MM_PER_PT
    return any(abs(mm - w) <= 0.005 for w in ISO_128_WIDTHS_MM)


# ---- the recipe --------------------------------------------------------------------------------


def calibrate_page(
    page: Any, min_confidence: float = 0.35, drawings: list | None = None
) -> Scale:
    """Recover the module for one page.

    Raises :class:`CalibrationError` rather than returning a low-confidence result, because every
    downstream threshold multiplies the module.
    """
    rect = page.rect
    page_span = max(float(rect.width), float(rect.height))
    sheet, system = detect_sheet(float(rect.width), float(rect.height))
    paths = drawings if drawings is not None else page.get_drawings()
    warnings: list[str] = []

    if system == "unknown":
        warnings.append("page box matches no standard sheet series; assuming ISA ratios")
        system = "ISA"

    stroke, stroke_hist = narrow_stroke_width(paths)
    text_h = modal_text_height(paths, page_span)
    symbol, symbol_count = dominant_symbol_diameter(paths, page_span)

    estimators: list[Estimator] = []

    if stroke:
        trusted, note = True, ""
        if _looks_like_fixed_plot_style(stroke):
            trusted = False
            note = "width sits on the ISO 128 series; likely a fixed plot style, not scale-bearing"
            warnings.append(f"narrow stroke {stroke}pt {note}")
        ratio = NARROW_STROKE_PER_MODULE[system]
        estimators.append(Estimator("stroke", stroke / ratio, stroke, ratio, trusted, note))

    if stroke and text_h:
        lo, hi = CAP_TO_STROKE_GATE
        ratio_ok = lo <= text_h / stroke <= hi
    else:
        ratio_ok = True
    if stroke and text_h and not ratio_ok:
        warnings.append(
            f"text/stroke ratio {text_h / stroke:.1f} outside the lettering band "
            f"{CAP_TO_STROKE_GATE}; text may not be a stroke font"
        )

    if symbol:
        ratio = SYMBOL_DIAMETER_PER_MODULE[system]
        estimators.append(
            Estimator("symbol", symbol / ratio, symbol, ratio, note=f"{symbol_count} instances")
        )

    trusted = [e for e in estimators if e.trusted]
    if not trusted:
        raise CalibrationError(
            f"no trusted scale estimator on page {getattr(page, 'number', '?')}; "
            f"observables: stroke={stroke} text={text_h} symbol={symbol}"
        )

    module = statistics.median(e.module for e in trusted)

    # Confidence is agreement between independent estimators. One estimator alone can be right,
    # but it cannot be corroborated, so it is capped well below a cross-checked result.
    if len(trusted) == 1:
        confidence = 0.45
        warnings.append(f"single estimator ({trusted[0].name}); no cross-check available")
    else:
        spread = max(abs(e.module - module) / module for e in trusted)
        confidence = max(0.0, 1.0 - spread * 2.0)
        if spread > 0.25:
            warnings.append(
                "scale estimators disagree by "
                f"{spread:.0%}: " + ", ".join(f"{e.name}={e.module:.4f}" for e in trusted)
            )

    if symbol:
        modules = symbol / module
        lo, hi = SYMBOL_DIAMETER_ACCEPT
        if not (lo <= modules <= hi):
            warnings.append(
                f"dominant symbol is {modules:.2f} modules, outside the expected {lo}-{hi}; "
                "this may be a non-standard template"
            )
            confidence *= 0.6

    if len({w for w in stroke_hist if w > 0}) >= 2:
        warnings.append("multiple stroke widths present: usable as a line-class signal")

    if confidence < min_confidence:
        raise CalibrationError(
            f"calibration confidence {confidence:.2f} below {min_confidence:.2f}. "
            + "; ".join(warnings)
        )

    return Scale(
        unit_system=system,
        module=module,
        sheet=sheet,
        page_width_pt=float(rect.width),
        page_height_pt=float(rect.height),
        narrow_stroke=stroke,
        text_height=text_h,
        symbol_diameter=symbol,
        estimators=tuple(estimators),
        confidence=round(confidence, 3),
        warnings=tuple(warnings),
    )


def calibrate_document(path: str) -> list[Scale]:
    """Recover the module for every page."""
    import pymupdf

    with pymupdf.open(path) as doc:
        return [calibrate_page(page) for page in doc]

"""A vector stroke font for the synthetic generator.

The real input renders text the way CAD plotters always have: each character is a handful of pen
strokes, not a filled outline. A generator that placed text with a TrueType font would
produce something the recogniser finds *easier* than the real content, and every figure measured
on it would be flattered. So the generator draws its own strokes.

Glyphs are defined on a 4x6 grid, y down, baseline at y=6. Each polyline becomes one PDF path,
which is how SHX plotting behaves and what the glyph classifier expects: short strokes, each
below the ``longest < 1.5 module`` gate as long as the text height stays near one module -- which
is itself the standard's proportion, since the module *is* the lettering height (STD-05).
"""

from __future__ import annotations

# The generator renders the recogniser's own alphabet -- deliberately and visibly. What the
# synthetic benchmark then measures is segmentation, normalisation and matching under randomised
# size, weight, tracking, shear and jitter; what it does not measure is transfer to a foreign
# shape font, which is reported separately from the real drawing. One definition, one place.
from pidgraph.recognise.glyphs import CELL_H, CELL_W, GLYPHS

__all__ = ["CELL_H", "CELL_W", "GLYPHS", "draw_text", "text_width"]


def text_width(text: str, height: float, *, tracking: float = 1.35) -> float:
    """Width of a rendered string. ``tracking`` is advance as a multiple of glyph width."""
    if not text:
        return 0.0
    advance = height * (CELL_W / CELL_H) * tracking
    return advance * (len(text) - 1) + height * (CELL_W / CELL_H)


def draw_text(
    page,
    text: str,
    x: float,
    y: float,
    height: float,
    stroke_width: float,
    *,
    tracking: float = 1.35,
    vertical: bool = False,
    shear: float = 0.0,
    jitter: float = 0.0,
    rng=None,
) -> tuple[float, float, float, float]:
    """Draw ``text`` with its top-left at ``(x, y)`` and return the bounding box.

    ``vertical`` rotates the whole string 90 degrees clockwise so it reads top-to-bottom when the
    head is tilted right -- the convention for labels on vertical runs. The returned box is the
    axis-aligned extent either way, which is what the truth record needs.
    """
    import random as random_mod

    import pymupdf

    unit = height / CELL_H
    advance = height * (CELL_W / CELL_H) * tracking
    length = text_width(text, height, tracking=tracking)
    rng = rng or random_mod.Random(0)

    for index, char in enumerate(text.upper()):
        strokes = GLYPHS.get(char)
        if strokes is None:
            continue  # unknown characters advance silently; the truth string keeps them
        offset = index * advance
        for stroke in strokes:
            points = []
            for gx, gy in stroke:
                # Domain randomisation at the point level: an oblique slant and per-point
                # jitter, so an exact-coordinate shortcut in any matcher scores zero and only
                # genuine shape matching passes.
                gx = gx + shear * (CELL_H - gy)
                if jitter:
                    gx += rng.uniform(-jitter, jitter) * CELL_H
                    gy += rng.uniform(-jitter, jitter) * CELL_H
                if vertical:
                    # Rotated a quarter-turn anticlockwise: the string reads bottom-to-top, the
                    # drafting convention for labels on vertical runs and the direction the
                    # recognition crop rotation undoes.
                    px = x + gy * unit
                    py = y + length - offset - gx * unit
                else:
                    px = x + offset + gx * unit
                    py = y + gy * unit
                points.append(pymupdf.Point(px, py))
            if len(points) >= 2:
                page.draw_polyline(points, color=(0, 0, 0), width=stroke_width)

    if vertical:
        return (x, y, x + height, y + length)
    return (x, y, x + length, y + height)

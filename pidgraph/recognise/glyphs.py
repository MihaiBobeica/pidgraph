"""The canonical stroke alphabet: CAD lettering as geometry, not pixels.

CAD text in a born-digital drawing is not an image of a font -- it is a small set of pen strokes
per character, emitted by the plotter from a shape font. Rasterising those strokes and asking a
raster OCR engine to guess at them throws away the strongest evidence in the file: the strokes
themselves. This module is the alphabet the vector matcher recognises against.

Shapes are defined on a 4-wide, 6-high cell, y down, baseline at y=6. They deliberately follow
the proportions of single-stroke engineering lettering (the gothic style every drafting standard
descends from), because that is what CAD shape fonts themselves imitate.

**Shared lineage, stated plainly:** the synthetic benchmark's generator renders text from this
same alphabet (``pidgraph.benchmark.strokefont`` imports it). The benchmark therefore measures
segmentation, normalisation and shape matching under randomised size, weight, tracking, shear
and point jitter -- it does not measure transfer to a foreign shape font. Transfer to real
AutoCAD SHX lettering is a separate question, answered by the matcher's confidence gate: a
character whose best match is not clearly better than its second stays unread and falls through
to raster OCR rather than being guessed.
"""

from __future__ import annotations

Stroke = list[tuple[float, float]]

CELL_W, CELL_H = 4.0, 6.0

GLYPHS: dict[str, list[Stroke]] = {
    "0": [[(0.5, 0), (3.5, 0), (4, 1), (4, 5), (3.5, 6), (0.5, 6), (0, 5), (0, 1), (0.5, 0)]],
    "1": [[(1, 1), (2, 0), (2, 6)], [(1, 6), (3, 6)]],
    "2": [[(0, 1), (0.5, 0), (3.5, 0), (4, 1), (4, 2.5), (0, 6), (4, 6)]],
    "3": [[(0, 0), (4, 0), (2, 2.5), (4, 3.5), (4, 5), (3.5, 6), (0.5, 6), (0, 5)]],
    "4": [[(3, 6), (3, 0), (0, 4), (4, 4)]],
    "5": [[(4, 0), (0, 0), (0, 2.5), (3, 2.5), (4, 3.5), (4, 5), (3.5, 6), (0.5, 6), (0, 5)]],
    "6": [
        [(3.5, 0), (1, 0), (0, 1.5), (0, 5), (0.5, 6), (3.5, 6), (4, 5), (4, 3.5), (3.5, 3), (0, 3)]
    ],
    "7": [[(0, 0), (4, 0), (1.5, 6)]],
    "8": [
        [(0.5, 0), (3.5, 0), (4, 1), (4, 5), (3.5, 6), (0.5, 6), (0, 5), (0, 1), (0.5, 0)],
        [(0, 3), (4, 3)],
    ],
    "9": [
        [(0.5, 6), (3, 6), (4, 4.5), (4, 1), (3.5, 0), (0.5, 0), (0, 1), (0, 2.5), (0.5, 3), (4, 3)]
    ],
    "A": [[(0, 6), (2, 0), (4, 6)], [(0.8, 4.2), (3.2, 4.2)]],
    "B": [
        [(0, 0), (0, 6)],
        [(0, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)],
        [(3, 3), (4, 4), (4, 5), (3, 6), (0, 6)],
    ],
    "C": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5)]],
    "D": [[(0, 0), (0, 6)], [(0, 0), (2.8, 0), (4, 1.2), (4, 4.8), (2.8, 6), (0, 6)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "F": [[(4, 0), (0, 0), (0, 6)], [(0, 3), (3, 3)]],
    "G": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 3), (2.2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(2, 0), (2, 6)], [(1, 0), (3, 0)], [(1, 6), (3, 6)]],
    "J": [[(4, 0), (4, 5), (3, 6), (1, 6), (0, 5)]],
    "K": [[(0, 0), (0, 6)], [(4, 0), (0, 3.2), (4, 6)]],
    "L": [[(0, 0), (0, 6), (4, 6)]],
    "M": [[(0, 6), (0, 0), (2, 3.2), (4, 0), (4, 6)]],
    "N": [[(0, 6), (0, 0), (4, 6), (4, 0)]],
    "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
    "P": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2.2), (3, 3.2), (0, 3.2)]],
    "Q": [
        [(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)],
        [(2.4, 4.4), (4.2, 6.2)],
    ],
    "R": [[(0, 6), (0, 0), (3, 0), (4, 1), (4, 2.2), (3, 3.2), (0, 3.2)], [(2, 3.2), (4, 6)]],
    "S": [
        [
            (4, 1),
            (3, 0),
            (1, 0),
            (0, 1),
            (0, 2),
            (1, 3),
            (3, 3),
            (4, 4),
            (4, 5),
            (3, 6),
            (1, 6),
            (0, 5),
        ]
    ],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "U": [[(0, 0), (0, 5), (1, 6), (3, 6), (4, 5), (4, 0)]],
    "V": [[(0, 0), (2, 6), (4, 0)]],
    "W": [[(0, 0), (1, 6), (2, 2.8), (3, 6), (4, 0)]],
    "X": [[(0, 0), (4, 6)], [(4, 0), (0, 6)]],
    "Y": [[(0, 0), (2, 3), (4, 0)], [(2, 3), (2, 6)]],
    "Z": [[(0, 0), (4, 0), (0, 6), (4, 6)]],
    "-": [[(0.6, 3), (3.4, 3)]],
    "/": [[(0.2, 6), (3.8, 0)]],
    '"': [[(1.2, 0), (1.2, 1.6)], [(2.6, 0), (2.6, 1.6)]],
    ".": [[(1.7, 5.5), (2.3, 5.5), (2.3, 6), (1.7, 6), (1.7, 5.5)]],
}

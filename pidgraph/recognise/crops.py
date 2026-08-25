"""Rendering text regions to images for recognition.

Two decisions are worth stating.

**Resolution is derived, not fixed.** The calibration stage recovers the drawing's module, and the
render resolution follows from the narrow stroke width -- enough pixels across a stroke that
adjacent parallel strokes inside a symbol do not merge. A drawing plotted at a different scale
therefore renders at a different resolution automatically.

**Crops are cut from one whole-page render.** Clipping per crop costs a fixed setup per call, so
several hundred crops cost far more that way than one page render plus array slicing. It also
guarantees every crop shares one coordinate frame.

The clip rectangle must be in *display* space. Passing an unrotated rectangle returns a zero-byte
image and raises nothing, which is the quietest way to get an empty result.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from pidgraph.extract.calibrate import Scale
from pidgraph.extract.text import TextRegion

MAX_RENDER_PIXELS = 400_000_000
"""Guard against a pathological page. Set explicitly rather than disabled: these are user files."""


@dataclass(frozen=True)
class Crop:
    """One rendered text region, ready for recognition."""

    region: TextRegion
    png: bytes
    width: int
    height: int
    upright: bool
    """False when the region was rotated to bring vertical text upright."""

    @property
    def key(self) -> str:
        """Content hash. The cache key, so identical crops are never recognised twice."""
        return hashlib.sha256(self.png).hexdigest()[:24]

    @property
    def legible(self) -> bool:
        """Whether the crop is large enough to be worth sending to a recogniser."""
        return self.width >= 8 and self.height >= 8


def render_page(page: Any, scale: Scale, dpi: float | None = None) -> tuple[Any, float]:
    """Render a whole page once. Returns the pixmap and the pixels-per-point factor."""
    import pymupdf

    resolution = dpi or scale.render_dpi()
    factor = resolution / 72.0
    rect = page.rect
    if rect.width * factor * rect.height * factor > MAX_RENDER_PIXELS:
        # Fall back to whatever resolution fits rather than failing outright.
        factor = (MAX_RENDER_PIXELS / (rect.width * rect.height)) ** 0.5
    matrix = pymupdf.Matrix(factor, factor)
    return page.get_pixmap(matrix=matrix, alpha=False), factor


def cut(
    pixmap: Any,
    factor: float,
    regions: list[TextRegion],
    scale: Scale,
    pad: float = 0.5,
) -> list[Crop]:
    """Cut crops out of a rendered page.

    ``pad`` is in modules, so the margin scales with the drawing. Vertical regions are rotated
    upright, because a recogniser reading sideways text performs far worse than one reading a
    rotated copy.
    """
    from PIL import Image

    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    margin = scale.u(pad) * factor
    out: list[Crop] = []

    for region in regions:
        box = region.bbox
        left = max(0, int(box.x0 * factor - margin))
        top = max(0, int(box.y0 * factor - margin))
        right = min(image.width, int(box.x1 * factor + margin))
        bottom = min(image.height, int(box.y1 * factor + margin))
        if right - left < 4 or bottom - top < 4:
            continue

        tile = image.crop((left, top, right, bottom))
        upright = True
        if region.orientation == "vertical":
            tile = tile.rotate(-90, expand=True)
            upright = False

        import io

        buffer = io.BytesIO()
        tile.save(buffer, format="PNG", optimize=True)
        out.append(
            Crop(
                region=region,
                png=buffer.getvalue(),
                width=tile.width,
                height=tile.height,
                upright=upright,
            )
        )
    return out


def montage(crops: list[Crop], columns: int = 4, gap: int = 8, label: bool = True) -> bytes:
    """Tile crops into one image.

    Recognisers charge and rate-limit per request, so batching a few dozen crops into one image
    turns thousands of calls into a few tens. Each cell is numbered so the response can be mapped
    back to its crop; without that the batch is unusable.
    """
    from PIL import Image, ImageDraw

    if not crops:
        return b""
    import io

    tiles = [Image.open(io.BytesIO(c.png)).convert("RGB") for c in crops]
    pad_left = 46 if label else 0
    cell_w = max(t.width for t in tiles) + pad_left
    cell_h = max(t.height for t in tiles)
    rows = (len(tiles) + columns - 1) // columns

    sheet = Image.new(
        "RGB",
        (columns * (cell_w + gap) + gap, rows * (cell_h + gap) + gap),
        (255, 255, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for index, tile in enumerate(tiles):
        row, col = divmod(index, columns)
        x = gap + col * (cell_w + gap)
        y = gap + row * (cell_h + gap)
        if label:
            draw.text((x + 4, y + max(0, (cell_h - 10) // 2)), f"{index + 1:02d}", fill=(200, 0, 0))
        sheet.paste(tile, (x + pad_left, y))
        draw.rectangle(
            [x, y, x + cell_w, y + cell_h], outline=(220, 220, 220), width=1
        )

    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()

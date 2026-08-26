"""Render one PDF page to PNG on stdout. Used by the review UI, not by extraction."""

from __future__ import annotations

import sys
from pathlib import Path


def page_png(path: str | Path, page: int, scale: float = 1.6) -> bytes:
    import pymupdf

    with pymupdf.open(str(path)) as doc:
        if page < 0 or page >= doc.page_count:
            raise IndexError(f"page {page} out of range (0..{doc.page_count - 1})")
        pix = doc[page].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: python -m pidgraph.render <pdf> <page-index>", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(page_png(args[0], int(args[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

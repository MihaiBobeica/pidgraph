"""End-to-end extraction pipeline.

Wires the stages together and records, per page, which strategy each stage chose. That record is
part of the output rather than a log line: a run whose text came from structural hints is a
different artifact from one whose text was clustered, and a reader has to be able to tell.

Every stage asserts its postconditions. No stage may return an empty result silently -- an empty
graph that reports success is the worst failure this pipeline can produce, because everything
downstream inherits it without any error to notice.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pidgraph.extract import frame as frame_mod
from pidgraph.extract import lines as lines_mod
from pidgraph.extract import symbols as symbols_mod
from pidgraph.extract import text as text_mod
from pidgraph.extract.assemble import Graph, build
from pidgraph.extract.calibrate import CalibrationError, Scale, calibrate_page
from pidgraph.extract.primitives import BBox, extract_page
from pidgraph.ingest.probe import PageCapabilities, probe_page


class ExtractionError(RuntimeError):
    """A stage could not produce a usable result. Raised rather than returning empty."""


@dataclass
class PageResult:
    page_index: int
    capabilities: PageCapabilities
    scale: Scale
    graph: Graph
    strategies: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        strat = " ".join(f"{k}={v}" for k, v in self.strategies.items())
        return f"page {self.page_index}: {self.graph.summary()}\n    {strat}"


@dataclass
class DocumentResult:
    source: str
    pages: list[PageResult] = field(default_factory=list)
    elapsed_s: float = 0.0

    @property
    def graph_nodes(self) -> int:
        return sum(len(p.graph.nodes) for p in self.pages)

    @property
    def graph_edges(self) -> int:
        return sum(len(p.graph.edges) for p in self.pages)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "elapsed_s": round(self.elapsed_s, 3),
            "pages": [
                {
                    "page_index": p.page_index,
                    "capabilities": p.capabilities.summary(),
                    "scale": {
                        "unit_system": p.scale.unit_system,
                        "module_pt": round(p.scale.module, 4),
                        "sheet": p.scale.sheet,
                        "symbol_modules": round(p.scale.symbol_modules or 0, 3),
                        "render_dpi": round(p.scale.render_dpi()),
                        "confidence": p.scale.confidence,
                        "warnings": list(p.scale.warnings),
                    },
                    "strategies": p.strategies,
                    "counts": p.counts,
                    "notes": p.notes,
                    "graph": p.graph.to_dict(),
                }
                for p in self.pages
            ],
        }


def run_page(page: Any, page_index: int) -> PageResult:
    """Extract one page, recording the strategy chosen at each stage."""
    caps = probe_page(page, page_index)
    if not caps.has_vector_geometry and not caps.is_raster_page:
        raise ExtractionError(
            f"page {page_index} offers neither vector geometry nor a decodable raster; "
            "no extraction strategy applies"
        )
    if not caps.has_vector_geometry:
        raise ExtractionError(
            f"page {page_index} is a raster page; the raster strategy is not yet implemented. "
            "Refusing rather than returning an empty graph."
        )

    strategies: dict[str, str] = {"geometry": "vector"}
    notes: list[str] = []

    try:
        scale = calibrate_page(page)
    except CalibrationError as exc:
        raise ExtractionError(f"page {page_index}: {exc}") from exc
    strategies["calibration"] = f"module={scale.module:.3f}pt@{scale.confidence:.2f}"
    notes.extend(scale.warnings)

    prims = extract_page(page, scale, page_index)
    page_box = BBox(0.0, 0.0, float(page.rect.width), float(page.rect.height))
    detected = frame_mod.detect_frame(prims, page_box, scale)
    content, furniture = frame_mod.split(prims, detected)
    notes.extend(detected.reasons)
    if not content:
        raise ExtractionError(f"page {page_index}: frame stripping removed all content")

    marks = text_mod.glyph_marks(content)
    regions, how = text_mod.recover(page, marks, scale, page_index)
    strategies["text_regions"] = how

    conductors = lines_mod.chain_dashes(lines_mod.merge(content, scale, page_index), scale)
    strategies["line_typing"] = (
        "dash_arrays" if caps.dash_arrays_present else "gap_statistics"
    )

    circles = symbols_mod.dedupe(
        symbols_mod.find_instrument_circles(content, scale, page_index), scale
    )
    shapes = symbols_mod.group_composites(content, scale, page_index, start_id=10_000)
    symbols = symbols_mod.dedupe(circles + shapes, scale)
    strategies["symbols"] = f"dimensional+shape ({len(circles)} dimensional)"

    graph = build(symbols, conductors, regions, scale, page_index)

    return PageResult(
        page_index=page_index,
        capabilities=caps,
        scale=scale,
        graph=graph,
        strategies=strategies,
        counts={
            "primitives": len(prims),
            "content": len(content),
            "furniture": len(furniture),
            "text_regions": len(regions),
            "conductors": len(conductors),
            "instrument_circles": len(circles),
            "symbols": len(symbols),
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
        },
        notes=notes,
    )


def run(path: str | Path) -> DocumentResult:
    """Extract a whole document."""
    import pymupdf

    started = time.perf_counter()
    result = DocumentResult(source=str(path))
    with pymupdf.open(str(path)) as doc:
        if doc.page_count == 0:
            raise ExtractionError(f"{path} has no pages")
        for index, page in enumerate(doc):
            result.pages.append(run_page(page, index))
    result.elapsed_s = time.perf_counter() - started

    if result.graph_nodes == 0:
        raise ExtractionError(
            f"{path}: extraction produced no nodes. Refusing to report success on an empty graph."
        )
    return result

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
    notes: list[str] = field(default_factory=list)
    """Document-level events. Backend failures land here rather than on whichever page happened
    to be processed last, which misattributes every earlier page's failure."""

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
            "notes": list(self.notes),
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


def run_page(page: Any, page_index: int, recogniser: Any | None = None) -> PageResult:
    """Extract one page, recording the strategy chosen at each stage."""
    drawings = page.get_drawings()  # parsed once; every stage below reuses it
    caps = probe_page(page, page_index, drawings=drawings)
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
        scale = calibrate_page(page, drawings=drawings)
    except CalibrationError as exc:
        raise ExtractionError(f"page {page_index}: {exc}") from exc
    strategies["calibration"] = f"module={scale.module:.3f}pt@{scale.confidence:.2f}"
    notes.extend(scale.warnings)

    prims = extract_page(page, scale, page_index, drawings=drawings)
    page_box = BBox(0.0, 0.0, float(page.rect.width), float(page.rect.height))
    detected = frame_mod.detect_frame(prims, page_box, scale)
    content, furniture = frame_mod.split(prims, detected)
    notes.extend(detected.reasons)
    if not content:
        raise ExtractionError(f"page {page_index}: frame stripping removed all content")

    marks = text_mod.glyph_marks(content)
    regions, how = text_mod.recover(page, marks, scale, page_index, content=detected.content)
    strategies["text_regions"] = how

    # Recognition, cache-first. With a warm cache this costs one page render; with a cold cache
    # it additionally runs the local engine on the misses. Without any recogniser the regions
    # stay unread, which downstream code treats as a gap rather than as absence.
    texts_read = tags_parsed = 0
    recognition_error: str | None = None
    if recogniser is not None and regions:
        from pidgraph.recognise import crops as crops_mod
        from pidgraph.standards.tags import parse as parse_tag

        # Recognition is an enrichment, not a prerequisite: if the render or the engine fails,
        # the graph is still extracted and the labels stay unread -- the same degraded state as
        # having no recogniser at all, and the failure is recorded rather than fatal.
        try:
            pixmap, factor = crops_mod.render_page(page, scale)
            cut = crops_mod.cut(pixmap, factor, regions, scale)
            results = recogniser.recognise(cut)
        except Exception as exc:  # any render/engine failure degrades, never aborts
            recognition_error = f"{type(exc).__name__}: {exc}"
            cut, results = [], {}
        by_region: dict[int, tuple[str, float]] = {}
        for crop in cut:
            hit = results.get(crop.key)
            if hit is not None and hit.usable:
                by_region[id(crop.region)] = (hit.text, hit.confidence)
        enriched = []
        for region in regions:
            hit = by_region.get(id(region))
            if hit is None:
                enriched.append(region)
                continue
            enriched.append(region.with_text(hit[0], hit[1]))
            texts_read += 1
            if parse_tag(hit[0]).ok:
                tags_parsed += 1
        regions = enriched
        if recognition_error is not None:
            strategies["text_content"] = f"failed, labels left unread ({recognition_error})"
        else:
            strategies["text_content"] = (
                f"{recogniser.backend().name if recogniser.backend() else 'cache'} "
                f"({texts_read}/{len(regions)} read, {tags_parsed} tags)"
            )
    else:
        strategies["text_content"] = "none available"

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
            "texts_read": texts_read,
            "tags_parsed": tags_parsed,
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

    # One recogniser for the whole document, so the cache is shared and saved once. Its absence
    # is not an error: the pipeline degrades to unread labels and says so per page.
    try:
        from pidgraph.recognise.ocr import Cache, Recogniser

        recogniser: Any | None = Recogniser(cache=Cache.load())
    except Exception:
        recogniser = None

    with pymupdf.open(str(path)) as doc:
        if doc.page_count == 0:
            raise ExtractionError(f"{path} has no pages")
        for index, page in enumerate(doc):
            result.pages.append(run_page(page, index, recogniser=recogniser))

    if recogniser is not None:
        result.notes.extend(f"recognition: {m}" for m in recogniser.errors)
        recogniser.cache.save()
    result.elapsed_s = time.perf_counter() - started

    if result.graph_nodes == 0:
        raise ExtractionError(
            f"{path}: extraction produced no nodes. Refusing to report success on an empty graph."
        )
    return result

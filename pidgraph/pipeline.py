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
from pidgraph.extract.assemble import build, graph_summary
from pidgraph.extract.calibrate import CalibrationError, Scale, calibrate_page
from pidgraph.extract.primitives import BBox, extract_page, promote_lettering
from pidgraph.ingest.probe import PageCapabilities, probe_page


class ExtractionError(RuntimeError):
    """A stage could not produce a usable result. Raised rather than returning empty."""


@dataclass
class PageResult:
    page_index: int
    capabilities: PageCapabilities
    scale: Scale
    graph: Any
    strategies: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    regions: list = field(default_factory=list)
    """The recovered text regions after recognition, for scoring and inspection."""

    def summary(self) -> str:
        strat = " ".join(f"{k}={v}" for k, v in self.strategies.items())
        return f"page {self.page_index}: {graph_summary(self.graph)}\n    {strat}"


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
        return sum(p.graph.number_of_nodes() for p in self.pages)

    @property
    def graph_edges(self) -> int:
        return sum(p.graph.number_of_edges() for p in self.pages)


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
    prims, promoted_marks = promote_lettering(prims, scale)
    page_box = BBox(0.0, 0.0, float(page.rect.width), float(page.rect.height))
    detected = frame_mod.detect_frame(prims, page_box, scale)
    content, furniture = frame_mod.split(prims, detected)
    notes.extend(detected.reasons)
    if not content:
        raise ExtractionError(f"page {page_index}: frame stripping removed all content")

    # Conductors are recovered before text, because the two compete for the same small marks: a
    # simulated dash is glyph-sized, and only the chaining test can tell a dash run from a label.
    # Marks a chain consumed are removed from the text pool; candidates that failed to chain are
    # removed from the conductor set.
    merged = lines_mod.merge(content, scale, page_index)
    candidates, candidate_map = lines_mod.glyph_dash_candidates(content, scale, page_index)
    chained = lines_mod.chain_dashes(merged + candidates, scale)
    candidate_ids = set(candidate_map)
    # A chain that absorbed glyph strokes must look like a conductor, not like a word: hyphens,
    # serifs and base bars of a printed string are also short collinear strokes at regular pitch,
    # but a string spans a few modules where a signal run spans tens. A candidate-bearing chain
    # below conductor scale is dissolved and its marks returned to the text pool.
    conductors: list = []
    consumed_marks: set[int] = set()
    merged_by_id = {line.id: line for line in merged}
    for line in chained:
        if line.id in candidate_ids:
            continue  # an unchained candidate is a letter stroke, not a conductor
        absorbed = [m for m in line.member_ids if m in candidate_ids]
        if absorbed:
            pure = len(absorbed) == len(line.member_ids)
            duty = line.total_ink / max(line.length, 1e-9)
            if pure and (line.length < scale.u(15.0) or duty < 0.35):
                # Printed text is periodic too: the base bars of a string of digits are
                # collinear at the character pitch and chain exactly like dashes. What text can
                # never fake is a conductor's scale and ink: a real dashed run is tens of
                # modules long with mark comparable to gap, where a string's bars span a word
                # and leave the pitch mostly empty.
                continue
            if not pure and line.length < scale.u(8.0):
                # Dissolving the chain must not delete its real line pieces: the merged runs it
                # absorbed exist nowhere else in the output, so they are re-emitted as the
                # conductors they were before the candidates dragged them into a chain.
                conductors.extend(merged_by_id[m] for m in line.member_ids if m in merged_by_id)
                continue
        conductors.append(line)
        consumed_marks.update(candidate_map[m] for m in absorbed)

    marks = [m for m in text_mod.glyph_marks(content) if m.index not in consumed_marks]
    regions, how = text_mod.recover(page, marks, scale, page_index, content=detected.content)
    strategies["text_regions"] = how

    # Recognition, cache-first. With a warm cache this costs one page render; with a cold cache
    # it additionally runs the local engine on the misses. Without any recogniser the regions
    # stay unread, which downstream code treats as a gap rather than as absence.
    texts_read = tags_parsed = 0
    vector_read = 0
    recognition_error: str | None = None
    if regions:
        from pidgraph.recognise import vector_match
        from pidgraph.standards.tags import parse as parse_tag

        # Vector matching first: the strokes are already in hand, and reading them directly has
        # none of raster OCR's resolution and threshold failure modes. Only regions the matcher
        # refuses -- foreign shape fonts, curved lettering, low-margin matches -- go on to the
        # raster engine.
        enriched = []
        vector_confirmed: set[int] = set()
        for region in regions:
            read = (
                vector_match.read_region(region.marks, region.orientation) if region.marks else None
            )
            if read is not None:
                enriched.append(region.with_text(read.text, read.confidence))
                vector_confirmed.update(m.index for m in region.marks)
                vector_read += 1
                texts_read += 1
                if parse_tag(read.text).ok:
                    tags_parsed += 1
            else:
                enriched.append(region)
        regions = enriched

    if recogniser is not None and any(r.text is None for r in regions):
        from pidgraph.recognise import crops as crops_mod
        from pidgraph.standards.tags import parse as parse_tag

        pending = [r for r in regions if r.text is None]
        # Recognition is an enrichment, not a prerequisite: if the render or the engine fails,
        # the graph is still extracted and the labels stay unread -- the same degraded state as
        # having no recogniser at all, and the failure is recorded rather than fatal.
        try:
            pixmap, factor = crops_mod.render_page(page, scale)
            cut = crops_mod.cut(pixmap, factor, pending, scale)
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
            strategies["text_content"] = (
                f"vector {vector_read}; raster failed, rest unread ({recognition_error})"
            )
        else:
            strategies["text_content"] = (
                f"vector {vector_read} + "
                f"{recogniser.backend().name if recogniser.backend() else 'cache'} "
                f"{texts_read - vector_read} ({texts_read}/{len(regions)} read, {tags_parsed} tags)"
            )
    else:
        strategies["text_content"] = (
            f"vector only ({vector_read}/{len(regions)} read, {tags_parsed} tags)"
        )

    # Promotion was a hypothesis; reading was the test. A promoted mark inside a region that no
    # recogniser could read is returned to the symbol pool -- it was probably a symbol internal
    # keeping letter-shaped company -- before symbols are detected.
    if promoted_marks:
        import dataclasses as _dc

        from pidgraph.extract.primitives import Kind as _Kind
        from pidgraph.standards.tags import parse as _parse

        # Confirmation must be earned: a vector read passed the grammar-guarded matcher, and a
        # raster read confirms only if it parses -- a raster engine given a cluster of symbol
        # internals will hallucinate letter salad, and letter salad must not keep real symbol
        # geometry out of the symbol pool.
        confirmed: set[int] = set(vector_confirmed) if regions else set()
        for region in regions:
            if region.text is not None and _parse(region.text).ok:
                confirmed.update(m.index for m in region.marks)
        demote = promoted_marks - confirmed
        if demote:
            content = [
                _dc.replace(p, kind=_Kind.SYMBOL)
                if p.index in demote and p.kind is _Kind.GLYPH
                else p
                for p in content
            ]
            notes.append(
                f"{len(demote)} letter-shaped marks promoted, unread, and returned to symbols"
            )

    strategies["line_typing"] = "dash_arrays" if caps.dash_arrays_present else "gap_statistics"

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
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "tags_bound_nodes": graph.graph.get("attach", {}).get("bound_nodes", 0),
            "tags_bound_edges": graph.graph.get("attach", {}).get("bound_edges", 0),
            "tags_composed": graph.graph.get("attach", {}).get("composed_bubbles", 0),
            "tags_unbound": len(graph.graph.get("attach", {}).get("unbound", [])),
        },
        notes=notes,
        regions=list(regions),
    )


def run(path: str | Path, *, recogniser: Any | None = None) -> DocumentResult:
    """Extract a whole document."""
    import pymupdf

    started = time.perf_counter()
    result = DocumentResult(source=str(path))

    # One recogniser for the whole document, so the cache is shared and saved once. Its absence
    # is not an error: the pipeline degrades to unread labels and says so per page. An injected
    # recogniser (the benchmark passes one with its own cache) is used as given, so synthetic
    # crops never pollute the committed codebook.
    if recogniser is None:
        try:
            from pidgraph.recognise.ocr import Cache, Recogniser

            recogniser = Recogniser(cache=Cache.load())
        except Exception:
            recogniser = None

    with pymupdf.open(str(path)) as doc:
        if doc.page_count == 0:
            raise ExtractionError(f"{path} has no pages")
        for index, page in enumerate(doc):
            result.pages.append(run_page(page, index, recogniser=recogniser))

    if recogniser is not None:
        # Drain, not copy: an injected recogniser is shared across documents, and errors left on
        # it would be re-reported by every later document as if they were its own.
        result.notes.extend(f"recognition: {m}" for m in recogniser.errors)
        recogniser.errors.clear()
        recogniser.cache.save()
    result.elapsed_s = time.perf_counter() - started

    if result.graph_nodes == 0:
        raise ExtractionError(
            f"{path}: extraction produced no nodes. Refusing to report success on an empty graph."
        )
    return result

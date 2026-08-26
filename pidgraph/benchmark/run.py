"""Benchmark runner.

Scores the pipeline against synthetic drawings whose truth is exact by construction, and reports
per-method results with denominators and intervals.

The governing rule is that **no component is scored against output it produced**. The truth here
was authored before anything was drawn, so nothing in the pipeline had a hand in it.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from pidgraph.benchmark import generate, metrics
from pidgraph.benchmark.metrics import Score


@dataclass
class SampleResult:
    name: str
    module_truth: float
    module_found: float | None
    sheet_truth: str
    sheet_found: str | None
    symbol_sweep: dict[float, tuple[Score, Score]] = field(default_factory=dict)
    edge_precision: Score | None = None
    edge_recall: Score | None = None
    text_precision: Score | None = None
    text_recall: Score | None = None
    attach_precision: Score | None = None
    attach_recall: Score | None = None
    attach_unmatched_tagged: int = 0
    line_precision: Score | None = None
    line_recall: Score | None = None
    error: str | None = None

    @property
    def module_error(self) -> float | None:
        if self.module_found is None:
            return None
        return abs(self.module_found - self.module_truth) / self.module_truth


@dataclass
class BenchmarkReport:
    samples: list[SampleResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def aggregate(self, threshold: float = 0.3) -> dict[str, Score]:
        """Pool counts across samples before computing a rate.

        Pooling rather than averaging per-sample rates: averaging weights a drawing with three
        symbols the same as one with thirty, which is not what the number should mean.
        """
        p_hits = p_total = r_hits = r_total = 0
        e_p_hits = e_p_total = e_r_hits = e_r_total = 0
        t_p_hits = t_p_total = t_r_hits = t_r_total = 0
        a_p_hits = a_p_total = a_r_hits = a_r_total = 0
        l_p_hits = l_p_total = l_r_hits = l_r_total = 0
        for sample in self.samples:
            if sample.error or threshold not in sample.symbol_sweep:
                continue
            precision, recall = sample.symbol_sweep[threshold]
            p_hits += precision.hits
            p_total += precision.total
            r_hits += recall.hits
            r_total += recall.total
            if sample.edge_precision and sample.edge_recall:
                e_p_hits += sample.edge_precision.hits
                e_p_total += sample.edge_precision.total
                e_r_hits += sample.edge_recall.hits
                e_r_total += sample.edge_recall.total
            if sample.text_precision and sample.text_recall:
                t_p_hits += sample.text_precision.hits
                t_p_total += sample.text_precision.total
                t_r_hits += sample.text_recall.hits
                t_r_total += sample.text_recall.total
            if sample.attach_precision and sample.attach_recall:
                a_p_hits += sample.attach_precision.hits
                a_p_total += sample.attach_precision.total
                a_r_hits += sample.attach_recall.hits
                a_r_total += sample.attach_recall.total
            if sample.line_precision and sample.line_recall:
                l_p_hits += sample.line_precision.hits
                l_p_total += sample.line_precision.total
                l_r_hits += sample.line_recall.hits
                l_r_total += sample.line_recall.total
        return {
            "symbol_precision": metrics.score(p_hits, p_total, f"symbol precision@{threshold}"),
            "symbol_recall": metrics.score(r_hits, r_total, f"symbol recall@{threshold}"),
            "edge_precision": metrics.score(e_p_hits, e_p_total, "edge precision"),
            "edge_recall": metrics.score(e_r_hits, e_r_total, "edge recall"),
            "text_precision": metrics.score(t_p_hits, t_p_total, "text precision"),
            "text_recall": metrics.score(t_r_hits, t_r_total, "text recall"),
            "attachment_precision": metrics.score(a_p_hits, a_p_total, "attachment precision"),
            "attachment_recall": metrics.score(a_r_hits, a_r_total, "attachment recall"),
            "line_precision": metrics.score(l_p_hits, l_p_total, "line attachment precision"),
            "line_recall": metrics.score(l_r_hits, l_r_total, "line attachment recall"),
        }

    def calibration_accuracy(self) -> dict[str, float | int]:
        errors = [s.module_error for s in self.samples if s.module_error is not None]
        recovered = sum(1 for s in self.samples if s.module_found is not None)
        sheets = sum(1 for s in self.samples if s.sheet_found == s.sheet_truth)
        return {
            "samples": len(self.samples),
            "module_recovered": recovered,
            "sheet_correct": sheets,
            "median_module_error": statistics.median(errors) if errors else float("nan"),
            "max_module_error": max(errors) if errors else float("nan"),
        }

    def to_dict(self) -> dict:
        aggregate = self.aggregate()
        return {
            "calibration": self.calibration_accuracy(),
            "aggregate": {k: v.to_dict() for k, v in aggregate.items()},
            # Tag-bearing nodes matched to no truth symbol: a detection question, not an
            # attachment one, so a raw count rather than a rate (see attachment_scores).
            "attachment_unmatched_tagged": sum(s.attach_unmatched_tagged for s in self.samples),
            "samples": [
                {
                    "name": s.name,
                    "module_truth": round(s.module_truth, 4),
                    "module_found": round(s.module_found, 4) if s.module_found else None,
                    "module_error": (
                        round(s.module_error, 4) if s.module_error is not None else None
                    ),
                    "sheet_truth": s.sheet_truth,
                    "sheet_found": s.sheet_found,
                    "error": s.error,
                }
                for s in self.samples
            ],
            "notes": self.notes,
        }


def score_sample(path: Path, truth: generate.TruthGraph, recogniser=None) -> SampleResult:
    """Run the pipeline over one generated drawing and score it."""
    from pidgraph.pipeline import ExtractionError, run

    result = SampleResult(
        name=path.stem,
        module_truth=truth.module,
        module_found=None,
        sheet_truth=truth.sheet,
        sheet_found=None,
    )
    try:
        extraction = run(path, recogniser=recogniser)
    except ExtractionError as exc:
        result.error = str(exc)
        return result

    page = extraction.pages[0]
    result.module_found = page.scale.module
    result.sheet_found = page.scale.sheet

    # Score the object that lands on disk (NetworkX node-link), not a parallel in-memory shape.
    import tempfile

    from pidgraph.extract import export

    with tempfile.TemporaryDirectory() as tmp:
        nodelink = export.to_node_link(page.graph, Path(tmp) / "graph.nodelink.json")
        graph = export.load_node_link(nodelink)

    truth_boxes = [(s.id, s.bbox) for s in truth.symbols]
    predicted_boxes = [
        (key, (data["x0"], data["y0"], data["x1"], data["y1"]))
        for key, data in graph.nodes(data=True)
    ]
    result.symbol_sweep = metrics.sweep(truth_boxes, predicted_boxes)

    mapping = metrics.match(truth_boxes, predicted_boxes, 0.3)
    result.edge_precision, result.edge_recall = metrics.edge_scores(
        [(e.source, e.target) for e in truth.edges],
        [(u, v) for u, v in graph.edges()],
        mapping,
    )

    predicted_tags = {
        key: tag
        for key, data in graph.nodes(data=True)
        if (tag := data.get("tag_canonical"))
    }
    result.attach_precision, result.attach_recall, result.attach_unmatched_tagged = (
        metrics.attachment_scores(truth.symbols, mapping, predicted_tags)
    )
    line_edges = [
        (u, v, data["line_number"])
        for u, v, data in graph.edges(data=True)
        if data.get("line_number")
    ]
    result.line_precision, result.line_recall = metrics.line_attachment_scores(
        truth.labels, mapping, line_edges
    )

    if truth.labels:
        reads = [
            ((r.bbox.x0, r.bbox.y0, r.bbox.x1, r.bbox.y1), r.text)
            for r in page.regions
            if getattr(r, "text", None)
        ]
        result.text_precision, result.text_recall = metrics.text_scores(
            truth.labels, reads, truth.module
        )
    return result


def run_benchmark(
    count: int = 12, directory: str | Path = "outputs/synthetic", *, seed0: int = 0
) -> BenchmarkReport:
    report = BenchmarkReport()
    samples = generate.corpus(count, directory, seed0=seed0, defects=True)
    # The benchmark carries its own recognition cache, kept apart from the committed codebook:
    # synthetic crops are not evidence about the real drawing, and the codebook must stay a
    # faithful record of what the real input contains.
    recogniser = None
    try:
        from pidgraph.recognise.ocr import Cache, Recogniser

        recogniser = Recogniser(
            cache=Cache.load(Path(directory) / "text_cache.json"), allow_network=False
        )
    except Exception:
        pass
    for path, truth in samples:
        report.samples.append(score_sample(path, truth, recogniser=recogniser))
    if recogniser is not None:
        recogniser.cache.save()

    report.notes.append(
        f"This corpus is seeds {seed0}..{seed0 + count - 1}. We tuned development against seeds "
        "0..9 only, so anything from seed 500 up is held-out — no change was fitted to it."
    )
    report.notes.append(
        "The ground truth was authored before the drawing was rendered, which means no part of "
        "the pipeline had any hand in producing the answers it is being scored against."
    )
    report.notes.append(
        "Read the text figures narrowly. They cover the vector glyph matcher plus its raster "
        "fallback, and the generator renders the matcher's own stroke alphabet — one definition, "
        "stated in code at both ends. So what is measured here is segmentation and matching "
        "under randomised size, weight, tracking, shear and jitter. It is NOT transfer to a "
        "font the matcher has never seen; only the real drawing measures that."
    )
    report.notes.append(
        "Module and sheet size vary from sample to sample, so any absolute dimension hardcoded "
        "somewhere in the pipeline would fail on most of these drawings rather than passing "
        "quietly."
    )
    report.notes.append(
        "Synthetic drawings are cleaner and more regular than real ones, so treat everything "
        "here as an upper bound rather than as a prediction of how it will do in the field."
    )
    report.notes.append(
        "Every rate above carries its denominator and a Wilson interval, and any rate with "
        "fewer than 5 instances behind it is withheld rather than printed."
    )
    return report


def write(report: BenchmarkReport, directory: str | Path = "benchmarks") -> tuple[Path, Path]:
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)

    json_path = base / "results.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    aggregate = report.aggregate()
    calibration = report.calibration_accuracy()
    lines = [
        "# Benchmark results",
        "",
        "These numbers come from synthetic drawings. We wrote down the correct answer first and",
        "rendered the drawing from it afterwards, so nothing here is scored against output the",
        "pipeline produced itself. The notes at the bottom say what that does and does not buy",
        "us — worth reading before quoting any of these figures.",
        "",
        "## Calibration",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Samples | {calibration['samples']} |",
        f"| Module recovered | {calibration['module_recovered']}/{calibration['samples']} |",
        f"| Sheet size identified | {calibration['sheet_correct']}/{calibration['samples']} |",
        f"| Median module error | {calibration['median_module_error']:.2%} |",
        f"| Worst module error | {calibration['max_module_error']:.2%} |",
        "",
        "## Detection and connectivity",
        "",
        "| Metric | Result |",
        "|---|---|",
    ]
    for key, value in aggregate.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    lines += ["", "## Notes", ""]
    lines += [f"- {note}" for note in report.notes]
    lines.append("")

    md_path = base / "results.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path

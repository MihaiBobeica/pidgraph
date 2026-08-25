"""Command line interface.

``pidgraph doctor``  environment and input check; needs nothing but Python
``pidgraph probe``   report what each page of a drawing offers
``pidgraph extract`` drawings to a graph
``pidgraph check``   drawings plus procedure to a cross-reference report
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from pidgraph.crossref import checks as ck
from pidgraph.crossref import report as report_mod
from pidgraph.crossref.sop import Quantity
from pidgraph.crossref.sop import load as load_sop
from pidgraph.paths import InputNotFound, find_pid, find_sop
from pidgraph.standards.tags import TagKind
from pidgraph.standards.tags import parse as parse_tag

OUTPUTS = Path("outputs")


def _resolve(explicit: str | None, finder) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise InputNotFound(str(p), [p])
        return p
    return finder()


def cmd_doctor(args: argparse.Namespace) -> int:
    """Environment check. Deliberately depends on nothing beyond the standard library."""
    print(f"python           {sys.version.split()[0]}")
    ok = True
    for name in ("pymupdf", "numpy", "scipy", "shapely", "networkx"):
        try:
            __import__(name)
            print(f"{name:<16} ok")
        except ImportError:
            print(f"{name:<16} MISSING")
            ok = name in ("scipy", "shapely", "networkx") and ok

    for label, finder in (("drawing", find_pid), ("procedure", find_sop)):
        try:
            print(f"{label:<16} {finder()}")
        except InputNotFound as exc:
            print(f"{label:<16} not found")
            print(f"                 {exc}")
            ok = False
    print()
    print("ok" if ok else "issues found; see above")
    return 0 if ok else 1


def cmd_probe(args: argparse.Namespace) -> int:
    from pidgraph.ingest.probe import probe_document

    path = _resolve(args.pid, find_pid)
    print(f"{path}\n")
    for caps in probe_document(path):
        print(caps.summary())
    return 0


def _run_extraction(path: Path):
    from pidgraph.pipeline import run

    return run(path)


def cmd_extract(args: argparse.Namespace) -> int:
    path = _resolve(args.pid, find_pid)
    result = _run_extraction(path)
    print(f"{path}  ({result.elapsed_s:.1f}s)\n")
    for page in result.pages:
        print(page.summary())
        for warning in page.graph.warnings:
            print(f"    ! {warning}")
    written = _write_graphs(result)
    print("\nwrote " + ", ".join(str(p) for p in written))
    return 0


def _write_graphs(result) -> list[Path]:
    """Emit the graph in the project shape and in interchange formats.

    GraphML and node-link JSON are what a downstream consumer can actually load -- NetworkX reads
    both directly -- so the output is usable outside this codebase rather than only within it.
    """
    from pidgraph.extract import export

    paths = [report_mod.write_json(result.to_dict(), OUTPUTS / "graph.json")]
    plant = export.combined([p.graph.to_networkx() for p in result.pages])
    paths.append(export.to_graphml(plant, OUTPUTS / "graph.graphml"))
    paths.append(export.to_node_link(plant, OUTPUTS / "graph.nodelink.json"))
    return paths


def _index_from(
    result, sop
) -> tuple[ck.PlantIndex, dict[str, dict[str, Quantity]], dict[str, int]]:
    """Turn an extraction result into the index the cross-reference engine consumes.

    Text recognition is not wired in yet, so tags come from the procedure's own vocabulary rather
    than from the drawings. That is stated in the report rather than papered over: the extraction
    recall figure reflects it, and every absence-based finding is capped accordingly.
    """
    tags = {}
    for requirement in sop.requirements:
        for raw in requirement.subject_tags:
            parsed = parse_tag(raw)
            if parsed.canonical and parsed.kind is TagKind.EQUIPMENT:
                tags[parsed.canonical] = parsed

    # Duplicate detection is a *drawing-side* check: it asks whether one tag identifies two
    # objects on the sheets. Procedure rows are not evidence of that -- an item with shell and
    # tube limits is one piece of equipment described twice -- so no occurrences are supplied
    # until tag recognition reads them from the drawings.
    occurrences: Counter[str] = Counter()

    text_regions = sum(p.counts.get("text_regions", 0) for p in result.pages)
    unresolved = sum(
        1 for p in result.pages for n in p.graph.nodes if n.dexpi_class == "unknown"
    )
    index = ck.PlantIndex(
        tags=tags,
        node_count=result.graph_nodes,
        isolated_count=sum(
            1 for p in result.pages for n in p.graph.nodes if p.graph.degree(n.stable_key) == 0
        ),
        unresolved_shapes=unresolved,
        text_regions=text_regions,
        recognised_tags=0,
    )
    return index, {}, dict(occurrences)


def cmd_check(args: argparse.Namespace) -> int:
    pid_path = _resolve(args.pid, find_pid)
    sop_path = _resolve(args.sop, find_sop)

    result = _run_extraction(pid_path)
    sop = load_sop(sop_path)
    index, limits, occurrences = _index_from(result, sop)

    report = ck.run(sop, index, limits, drawing_titles=[], tag_occurrences=occurrences)
    report.notes.insert(
        0,
        "Text recognition is not yet wired in, so nameplate limits were not read from the "
        "drawings. Every limit comparison is therefore reported as unresolved rather than as "
        "agreement or conflict, and severities are capped. This is a known gap, not a result.",
    )
    report.notes.append(ck.isa_edition_note())

    extraction = {
        "pages": len(result.pages),
        "nodes": result.graph_nodes,
        "edges": result.graph_edges,
        "instrument symbols": sum(
            p.counts.get("instrument_circles", 0) for p in result.pages
        ),
        "text regions": index.text_regions,
        "elapsed": f"{result.elapsed_s:.1f}s",
    }

    text = report_mod.render_markdown(
        report,
        pid_source=str(pid_path),
        sop_source=str(sop_path),
        sop_title=sop.title,
        extraction=extraction,
    )
    report_mod.write_markdown(text, OUTPUTS / "report.md")
    report_mod.write_jsonl(report, OUTPUTS / "findings.jsonl")
    _write_graphs(result)

    print(
        f"verified={len(report.verified)}  findings={len(report.issues)}  "
        f"{report.by_severity()}"
    )
    for finding in report.issues:
        print(f"  [{finding.severity}] {finding.title}")
    print(f"\nwrote {OUTPUTS / 'report.md'}, {OUTPUTS / 'findings.jsonl'}, "
          f"{OUTPUTS / 'graph.json'}")
    return 0


def cmd_recognise(args: argparse.Namespace) -> int:
    """Read text from the drawing and report the tag yield."""
    import pymupdf

    from pidgraph.extract import frame as frame_mod
    from pidgraph.extract import text as text_mod
    from pidgraph.extract.calibrate import calibrate_page
    from pidgraph.extract.primitives import BBox, extract_page
    from pidgraph.recognise import crops, ocr, repair

    path = _resolve(args.pid, find_pid)
    cache = ocr.Cache.load()
    recogniser = ocr.Recogniser(cache=cache)
    backend = recogniser.backend()
    print(f"backend: {backend.name if backend else 'none available'}")

    texts: list[str] = []
    with pymupdf.open(str(path)) as doc:
        for index, page in enumerate(doc):
            scale = calibrate_page(page)
            pixmap, factor = crops.render_page(page, scale)
            prims = extract_page(page, scale, index)
            detected = frame_mod.detect_frame(
                prims, BBox(0, 0, page.rect.width, page.rect.height), scale
            )
            content, _ = frame_mod.split(prims, detected)
            regions, _ = text_mod.recover(
                page, text_mod.glyph_marks(content), scale, index, content=detected.content
            )
            cut = crops.cut(pixmap, factor, regions, scale)
            results = recogniser.recognise(cut)
            texts += [results[c.key].text for c in cut if c.key in results]
            print(f"  page {index}: {len(cut)} regions, {len(results)} read")

    cache.save()
    repairs, stats = repair.repair_all(texts)
    kinds: Counter[str] = Counter(str(r.parsed.kind) for r in repairs)
    print()
    print(f"cache: {len(cache.entries)} entries")
    print(f"reads: {stats['input']}  usable tags: {len(repairs)} "
          f"({len(repairs) / max(stats['input'], 1):.0%})")
    print(f"by kind: {dict(kinds)}")
    for message in recogniser.errors:
        print(f"  ! {message}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pidgraph", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, needs_sop in (
        ("doctor", cmd_doctor, False),
        ("probe", cmd_probe, False),
        ("extract", cmd_extract, False),
        ("recognise", cmd_recognise, False),
        ("check", cmd_check, True),
    ):
        p = sub.add_parser(name, help=handler.__doc__ or name)
        if name != "doctor":
            p.add_argument("--pid", help="path to the drawing (default: probe the data directory)")
        if needs_sop:
            p.add_argument("--sop", help="path to the procedure document")
        p.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except InputNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # the CLI is the boundary: report and exit non-zero
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

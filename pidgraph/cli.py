"""Command line interface.

``pidgraph doctor``  environment and input check; needs nothing but Python
``pidgraph probe``   report what each page of a drawing offers
``pidgraph extract`` drawings to a graph
``pidgraph check``   drawings plus procedure to a cross-reference report
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from pidgraph.config import bootstrap
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
    from pidgraph.config import Config, find_cli
    from pidgraph.recognise.ocr import find_tesseract

    print(f"python           {sys.version.split()[0]}")
    ok = True
    for name in ("pymupdf", "numpy", "networkx", "PIL"):
        label = "pillow" if name == "PIL" else name
        try:
            __import__(name)
            print(f"{label:<16} ok")
        except ImportError:
            print(f"{label:<16} MISSING")
            ok = False

    print(f"{'tesseract':<16} {find_tesseract() or 'not found (text recognition unavailable)'}")
    print(f"{'1password cli':<16} {find_cli() or 'not found (op:// references cannot resolve)'}")
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        import urllib.request

        urllib.request.urlopen(f"{host}/api/tags", timeout=1)
        print(f"{'ollama':<16} ok")
    except Exception:
        print(f"{'ollama':<16} not running (optional Q&A unavailable)")

    print()
    # Configuration status only -- no value is ever printed, resolved or otherwise.
    for key, status in Config.load().describe():
        print(f"  {key:<32} {status}")
    print()

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
        for warning in page.graph.graph.get("warnings", []):
            print(f"    ! {warning}")
    written = _write_graphs(result, path)
    print("\nwrote " + ", ".join(str(p) for p in written))
    return 0


def _write_graphs(result, pid_path: Path | None = None) -> list[Path]:
    """Emit the plant graph as NetworkX node-link JSON.

    Latest run also lands at ``outputs/graph.nodelink.json`` so a consumer that does not know
    the content hash still has a stable path. Per-document copies live under ``outputs/<sha256>/``.
    """
    from pidgraph.extract import export
    from pidgraph.paths import sha256

    plant = export.combined([p.graph for p in result.pages])
    latest = OUTPUTS / "graph.nodelink.json"
    paths = [export.to_node_link(plant, latest)]
    if pid_path is not None:
        hashed = OUTPUTS / sha256(pid_path) / "graph.nodelink.json"
        paths.append(export.to_node_link(plant, hashed))
    return paths


def _index_from(
    result, sop
) -> tuple[ck.PlantIndex, dict[str, dict[str, Quantity]], dict[str, int]]:
    """Turn an extraction result into the index the cross-reference engine consumes.

    Tags come from the drawings themselves now: recognition attaches read text to nodes and the
    parser lifts it into canonical tags. The procedure's own tags are still merged in as
    *subjects to check* -- an unreadable nameplate must not make its equipment vanish from the
    checklist -- but drawing-side checks (duplicates) key only on what was actually read.
    """
    tags = {}
    occurrences: Counter[str] = Counter()
    for page in result.pages:
        for _key, data in page.graph.nodes(data=True):
            canonical = data.get("tag_canonical")
            if not canonical:
                continue
            parsed = parse_tag(canonical)
            if parsed.ok and parsed.canonical:
                tags[parsed.canonical] = parsed
                occurrences[parsed.canonical] += 1

    for requirement in sop.requirements:
        for raw in requirement.subject_tags:
            parsed = parse_tag(raw)
            if parsed.canonical and parsed.kind is TagKind.EQUIPMENT:
                tags.setdefault(parsed.canonical, parsed)

    text_regions = sum(p.counts.get("text_regions", 0) for p in result.pages)
    unresolved = sum(
        1
        for p in result.pages
        for _, data in p.graph.nodes(data=True)
        if data.get("dexpi_class") == "unknown"
    )
    index = ck.PlantIndex(
        tags=tags,
        node_count=result.graph_nodes,
        isolated_count=sum(
            1 for p in result.pages for n in p.graph if p.graph.degree(n) == 0
        ),
        unresolved_shapes=unresolved,
        text_regions=text_regions,
        recognised_tags=sum(p.counts.get("tags_parsed", 0) for p in result.pages),
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
        "We deliberately do not read the nameplate design-limit blocks off the drawings. Local "
        "OCR manages about a quarter of the regions on this stroke font, and a page usually "
        "holds more than one piece of equipment — so pinning a stray pressure value to the "
        "wrong vessel is a worse outcome than saying the comparison is unresolved. Tags on the "
        "drawing ARE read, and they drive the drawing-side checks.",
    )
    report.notes.append(ck.isa_edition_note())

    extraction = {
        "pages": len(result.pages),
        "nodes": result.graph_nodes,
        "edges": result.graph_edges,
        "instrument symbols": sum(p.counts.get("instrument_circles", 0) for p in result.pages),
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
    _write_graphs(result, pid_path)
    stored = _persist(result, report, pid_path, sop)

    print(f"verified={len(report.verified)}  findings={len(report.issues)}  {report.by_severity()}")
    for finding in report.issues:
        print(f"  [{finding.severity}] {finding.title}")
    print(
        f"\nwrote {OUTPUTS / 'report.md'}, {OUTPUTS / 'findings.jsonl'}, "
        f"{OUTPUTS / 'graph.nodelink.json'}"
    )
    print(f"persisted to {stored}")
    return 0


def _persist(result, report, pid_path: Path, sop) -> str:
    """Write the run to whichever store is configured, and name it.

    Falling back to the filesystem rather than failing is deliberate: the pipeline's job is to
    produce a graph, and someone without database credentials should still get one. Naming the
    store in the output is what stops a silent fallback from reading like a successful write.
    """
    from pidgraph.extract.assemble import edge_store_dict, node_store_dict
    from pidgraph.paths import find_sop, sha256, storage_key
    from pidgraph.store.base import LocalJsonStore, RunRecord
    from pidgraph.store.supabase_store import choose_store

    try:
        sop_path = find_sop()
        sop_sha, sop_key, sop_name = sha256(sop_path), storage_key(sop_path), sop_path.name
    except InputNotFound:
        sop_sha = sop_key = sop_name = ""

    nodes = [
        node_store_dict(key, data)
        for page in result.pages
        for key, data in page.graph.nodes(data=True)
    ]
    edges = [
        edge_store_dict(source, target, data)
        for page in result.pages
        for source, target, data in page.graph.edges(data=True)
    ]
    record = RunRecord(
        document_sha256=sha256(pid_path),
        document_kind="pid",
        filename=pid_path.name,
        storage_key=storage_key(pid_path),
        extractor_version="0.1.0",
        isa_edition="ANSI/ISA-5.1-2009",
        page_count=len(result.pages),
        title=sop.title,
        strategies={str(p.page_index): p.strategies for p in result.pages},
        scale={
            str(p.page_index): {"module": p.scale.module, "sheet": p.scale.sheet}
            for p in result.pages
        },
        stats={
            "nodes": result.graph_nodes,
            "edges": result.graph_edges,
            # The binding ledger travels with the run: how many tags bound, and each one that
            # did not, with its reason -- a reviewer should never have to re-run to learn this.
            "attach": {str(p.page_index): p.graph.graph.get("attach", {}) for p in result.pages},
        },
        nodes=nodes,
        edges=edges,
        findings=[f.to_dict() for f in report.findings],
        requirements=[
            {
                "ordinal": r.ordinal,
                "subject_raw": r.subject_raw,
                "subject_tags": list(r.subject_tags),
                "subject_part": r.subject_part,
                "quantities": {
                    k: {"min": v.minimum, "max": v.maximum, "unit": v.unit}
                    for k, v in r.quantities.items()
                },
                "evidence": r.evidence,
            }
            for r in sop.requirements
        ],
        sop_sha256=sop_sha,
        sop_filename=sop_name,
        sop_storage_key=sop_key,
    )

    store = choose_store()
    try:
        return f"{store.name} (run {store.write_run(record)})"
    except Exception as exc:
        print(f"  ! {store.name} write failed ({type(exc).__name__}: {exc}); falling back to files")
        fallback = LocalJsonStore()
        return f"{fallback.name} (run {fallback.write_run(record)})"


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Score the pipeline against synthetic drawings whose truth was authored before rendering."""
    from pidgraph.benchmark import run as bench

    report = bench.run_benchmark(args.count, args.dir, seed0=args.seed0)
    calibration = report.calibration_accuracy()
    print(
        f"samples={calibration['samples']}  "
        f"module recovered={calibration['module_recovered']}/{calibration['samples']}  "
        f"median module error={calibration['median_module_error']:.2%}"
    )
    for value in report.aggregate().values():
        print(f"  {value}")
    unmatched = sum(s.attach_unmatched_tagged for s in report.samples)
    print(f"  tagged nodes matched to no truth symbol: {unmatched} (raw count, not a rate)")
    for sample in report.samples:
        if sample.error:
            print(f"  ! {sample.name}: {sample.error}")
    json_path, md_path = bench.write(report, args.out)
    print(f"\nwrote {json_path}, {md_path}")
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Apply the database schema. Inspects first, and defaults to reporting rather than changing."""
    from pidgraph.config import Config
    from pidgraph.store import migrate

    dsn = Config.load().get("DATABASE_URL")
    if not dsn:
        print(
            "DATABASE_URL is not configured. The pipeline runs without a database -- results go "
            "to outputs/ and the interface reads them from there."
        )
        return 2

    report = migrate.apply(dsn, dry_run=not args.apply)
    if report.error:
        print(f"error: {report.error}")
        return 1

    if not args.apply:
        print("Inspection only. Re-run with --apply to make changes.")
        print()
        print(f"  already present: {report.existing_tables or 'none'}")
        print(f"  would create:    {report.missing or 'nothing (schema is current)'}")
        return 0

    print(f"applied: {', '.join(report.applied)}")
    print(f"  created:   {report.created_tables or 'nothing new'}")
    print(f"  functions: {report.functions or 'none'}")
    if report.missing:
        # Verified rather than assumed: a schema that reported success but left a table missing
        # would fail much later, during a write, far from the cause.
        print(f"  MISSING:   {report.missing}")
        return 1
    print()
    print("schema is current")
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
    print(
        f"reads: {stats['input']}  usable tags: {len(repairs)} "
        f"({len(repairs) / max(stats['input'], 1):.0%})"
    )
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
        ("migrate", cmd_migrate, False),
        ("check", cmd_check, True),
    ):
        p = sub.add_parser(name, help=handler.__doc__ or name)
        if name != "doctor":
            p.add_argument("--pid", help="path to the drawing (default: probe the data directory)")
        if needs_sop:
            p.add_argument("--sop", help="path to the procedure document")
        if name == "migrate":
            p.add_argument(
                "--apply",
                action="store_true",
                help="make changes; without this the command only inspects and reports",
            )
        p.set_defaults(handler=handler)

    bench = sub.add_parser("benchmark", help=cmd_benchmark.__doc__)
    bench.add_argument("--count", type=int, default=12, help="number of synthetic drawings")
    bench.add_argument(
        "--seed0",
        type=int,
        default=0,
        help="first seed; development tunes on 0..9, seeds from 500 are held out",
    )
    bench.add_argument(
        "--dir", default="outputs/synthetic", help="where generated drawings and their cache go"
    )
    bench.add_argument("--out", default="benchmarks", help="where results.json/.md are written")
    bench.set_defaults(handler=cmd_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Resolve configuration before anything reads the environment. Secret references are fetched
    # here and held in memory; nothing is written back to disk.
    bootstrap()
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

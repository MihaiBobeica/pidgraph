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
    out = report_mod.write_json(result.to_dict(), OUTPUTS / "graph.json")
    print(f"\nwrote {out}")
    return 0


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
    report_mod.write_json(result.to_dict(), OUTPUTS / "graph.json")

    print(
        f"verified={len(report.verified)}  findings={len(report.issues)}  "
        f"{report.by_severity()}"
    )
    for finding in report.issues:
        print(f"  [{finding.severity}] {finding.title}")
    print(f"\nwrote {OUTPUTS / 'report.md'}, {OUTPUTS / 'findings.jsonl'}, "
          f"{OUTPUTS / 'graph.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pidgraph", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, handler, needs_sop in (
        ("doctor", cmd_doctor, False),
        ("probe", cmd_probe, False),
        ("extract", cmd_extract, False),
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

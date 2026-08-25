"""Report rendering.

Two forms, because they serve different readers: JSONL for machines and downstream tooling, and
Markdown for a person.

The Markdown report leads with what was **verified**. Conforming documents may legitimately agree
everywhere, and a report that opens with an empty findings list reads as a broken tool rather than
as a clean result -- so the verification table is the headline and the findings follow it.
"""

from __future__ import annotations

import json
from pathlib import Path

from pidgraph.crossref.checks import CrossReferenceReport, Severity

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def write_jsonl(report: CrossReferenceReport, path: str | Path) -> Path:
    """One finding per line, ordered by severity. Stable across runs."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(report.findings, key=lambda f: (_SEVERITY_ORDER[f.severity], f.check, f.title))
    with p.open("w", encoding="utf-8") as handle:
        for finding in ordered:
            handle.write(json.dumps(finding.to_dict(), sort_keys=True) + "\n")
    return p


def write_json(payload: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return p


def render_markdown(
    report: CrossReferenceReport,
    *,
    pid_source: str,
    sop_source: str,
    sop_title: str = "",
    extraction: dict | None = None,
) -> str:
    """Render a human-readable report."""
    lines: list[str] = []
    add = lines.append

    add("# P&ID / SOP Cross-Reference Report")
    add("")
    add(f"- **Drawings:** `{pid_source}`")
    add(f"- **Procedure:** `{sop_source}`" + (f" — *{sop_title}*" if sop_title else ""))
    if report.extraction_recall is not None:
        add(f"- **Estimated extraction recall:** {report.extraction_recall:.0%}")
    add("")

    verified = report.verified
    issues = report.issues
    by_severity = report.by_severity()

    add("## Summary")
    add("")
    add(f"**{len(verified)} checks verified** · **{len(issues)} findings**")
    if by_severity:
        add("")
        add("| Severity | Count |")
        add("|---|---|")
        for severity, count in sorted(by_severity.items(), key=lambda kv: kv[0]):
            add(f"| {severity} | {count} |")
    add("")

    # Verified first. A conforming pair of documents agrees, and that is a result.
    if verified:
        add("## Verified")
        add("")
        add("Checks that ran and agreed. Reported explicitly so a clean result is legible as a")
        add("result rather than as an absence of output.")
        add("")
        add("| Check | Subject | Outcome |")
        add("|---|---|---|")
        for finding in verified:
            subject = finding.subject or "—"
            add(f"| `{finding.check}` | {subject} | {finding.title} |")
        add("")

    if issues:
        add("## Findings")
        add("")
        for finding in sorted(issues, key=lambda f: (_SEVERITY_ORDER[f.severity], f.check)):
            marker = "⚠" if finding.severity in (Severity.CRITICAL, Severity.HIGH) else "•"
            add(f"### {marker} {finding.title}")
            add("")
            add(f"- **Check:** `{finding.check}`")
            add(f"- **Severity:** {finding.severity} · **Status:** {finding.status}")
            add(f"- **Confidence:** {finding.confidence:.0%}")
            if finding.sop_evidence:
                add(f"- **Procedure evidence:** {finding.sop_evidence}")
            if finding.pid_evidence:
                add(f"- **Drawing evidence:** {finding.pid_evidence}")
            if finding.graph_incomplete:
                add(
                    "- ⓘ This finding rests on something *not* being found, so it may reflect an "
                    "extraction gap rather than a document defect. Severity is capped accordingly."
                )
            add("")
            add(finding.detail)
            add("")
    else:
        add("## Findings")
        add("")
        add("None. Every check that ran agreed — see the verification table above.")
        add("")

    if extraction:
        add("## Extraction")
        add("")
        add("| Metric | Value |")
        add("|---|---|")
        for key, value in extraction.items():
            add(f"| {key} | {value} |")
        add("")

    if report.notes:
        add("## Notes")
        add("")
        for note in report.notes:
            add(f"- {note}")
        add("")

    add("---")
    add("")
    add(
        "*Verdicts in this report are produced by deterministic rules. No language model "
        "participates in deciding whether something is a finding.*"
    )
    add("")
    return "\n".join(lines)


def write_markdown(text: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p

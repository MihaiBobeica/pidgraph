"""Cross-reference engine.

Three layers, and the ordering reflects what each needs:

1. **Intra-document consistency** -- needs no second document at all. Duplicate tags,
   non-conformant identification, unresolved ambiguous symbols, orphaned components.
2. **Document agreement** -- the SOP against the drawings.
3. **Procedure feasibility** -- steps that name tags must reference things that exist.

Two design constraints run through all of it.

**Verdicts are deterministic.** A model may structure prose or write an explanation; it never
decides whether something is a finding. A compliance-adjacent report has to be reproducible and
auditable without an API key.

**The system under-claims.** Confidence propagates as the minimum over inputs, and findings that
rest on *absence* are capped in severity and carry an extraction-completeness flag. Reporting
"equipment missing from the drawing" when extraction merely missed it accuses a correct document of
being wrong, which is the worst output this system can produce.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from pidgraph.crossref.sop import Quantity, Requirement, SopDocument
from pidgraph.standards import isa
from pidgraph.standards.tags import Conformance, ParsedTag, TagKind


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(StrEnum):
    VERIFIED = "verified"
    """A check ran and the documents agree. Reported as a first-class result, not hidden."""
    FINDING = "finding"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class Finding:
    check: str
    status: Status
    severity: Severity
    title: str
    detail: str
    confidence: float
    subject: str | None = None
    pid_evidence: str | None = None
    sop_evidence: str | None = None
    graph_incomplete: bool = False
    """Set when the verdict depends on something not being found, rather than on a conflict."""

    def to_dict(self) -> dict:
        return {**asdict(self), "status": str(self.status), "severity": str(self.severity)}


@dataclass
class CrossReferenceReport:
    findings: list[Finding] = field(default_factory=list)
    extraction_recall: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def verified(self) -> list[Finding]:
        return [f for f in self.findings if f.status is Status.VERIFIED]

    @property
    def issues(self) -> list[Finding]:
        return [f for f in self.findings if f.status is not Status.VERIFIED]

    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.issues:
            counts[str(finding.severity)] = counts.get(str(finding.severity), 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict:
        return {
            "summary": {
                "verified": len(self.verified),
                "findings": len(self.issues),
                "by_severity": self.by_severity(),
                "extraction_recall": self.extraction_recall,
            },
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
        }


@dataclass
class PlantIndex:
    """What the drawings yielded, indexed for cross-referencing."""

    tags: dict[str, ParsedTag] = field(default_factory=dict)
    node_count: int = 0
    isolated_count: int = 0
    unresolved_shapes: int = 0
    text_regions: int = 0
    recognised_tags: int = 0

    @property
    def recall_estimate(self) -> float:
        """Rough fraction of text regions that yielded a usable tag.

        Deliberately conservative and used only to *cap* severity, never to raise it.
        """
        if not self.text_regions:
            return 0.0
        return min(1.0, self.recognised_tags / self.text_regions)

    def equipment(self) -> dict[str, ParsedTag]:
        return {k: v for k, v in self.tags.items() if v.kind is TagKind.EQUIPMENT}


# --- Layer 1: intra-document consistency --------------------------------------------------------


def check_tag_conformance(index: PlantIndex) -> list[Finding]:
    """Report identification that does not conform, without rejecting it."""
    out: list[Finding] = []
    for tag in index.tags.values():
        if tag.conformance is Conformance.NORMALISED:
            out.append(
                Finding(
                    check="tag_not_conformant",
                    status=Status.FINDING,
                    severity=Severity.LOW,
                    title=f"{tag.raw} does not follow the conformant letter order",
                    detail=(
                        f"Read as {tag.canonical}. "
                        + (tag.notes[0] if tag.notes else "")
                    ),
                    confidence=0.9,
                    subject=tag.canonical,
                    pid_evidence=tag.raw,
                )
            )
    return out


def check_duplicate_tags(index: PlantIndex, occurrences: dict[str, int]) -> list[Finding]:
    """A tag identifying two different objects is either a drafting error or a misread."""
    out: list[Finding] = []
    for tag, count in sorted(occurrences.items()):
        if count > 1 and tag in index.tags:
            out.append(
                Finding(
                    check="duplicate_tag",
                    status=Status.FINDING,
                    severity=Severity.MEDIUM,
                    title=f"{tag} appears {count} times",
                    detail=(
                        "A tag should identify one item. This is either a drafting error or two "
                        "objects were read as the same tag; the check cannot distinguish them."
                    ),
                    confidence=0.5,
                    subject=tag,
                )
            )
    return out


def check_unresolved_symbols(index: PlantIndex) -> list[Finding]:
    """Symbols whose class cannot be settled from geometry alone."""
    if not index.unresolved_shapes:
        return []
    return [
        Finding(
            check="symbol_requires_legend",
            status=Status.NEEDS_REVIEW,
            severity=Severity.INFO,
            title=f"{index.unresolved_shapes} symbols carry no resolved class",
            detail=(
                "Some symbols are genuinely ambiguous without the drawing's legend sheet -- the "
                "standard itself gives one shape two meanings. These are reported rather than "
                "guessed at."
            ),
            confidence=1.0,
            graph_incomplete=True,
        )
    ]


def check_safety_devices(index: PlantIndex) -> list[Finding]:
    """Confirm safety devices were identified, and surface any SIS tagging."""
    safety = [t for t in index.tags.values() if t.is_safety_device]
    sis = [t for t in index.tags.values() if t.is_sis]
    out: list[Finding] = []
    if safety:
        out.append(
            Finding(
                check="safety_devices_identified",
                status=Status.VERIFIED,
                severity=Severity.INFO,
                title=f"{len(safety)} self-actuated protective devices identified",
                detail=", ".join(sorted(t.canonical or t.raw for t in safety)),
                confidence=0.9,
            )
        )
    if sis:
        out.append(
            Finding(
                check="sis_tagging_present",
                status=Status.VERIFIED,
                severity=Severity.INFO,
                title=f"{len(sis)} safety-instrumented items identified",
                detail=(
                    "Recognised via the modifier the current standard assigns to SIS. The "
                    "project's base vocabulary predates that addition, so this depends on the "
                    "overlaid delta."
                ),
                confidence=0.8,
            )
        )
    return out


# --- Layer 2: document agreement ----------------------------------------------------------------


def _compare(field_name: str, sop: Quantity, pid: Quantity | None) -> tuple[bool, str]:
    if pid is None:
        return False, f"no {field_name} found on the drawing"
    if sop.unit != pid.unit:
        return False, f"unit mismatch: SOP {sop.unit} vs drawing {pid.unit}"
    if sop.matches(pid):
        return True, f"{field_name} agrees at {sop}"
    return False, f"{field_name} differs: SOP {sop} vs drawing {pid}"


def check_design_limits(
    requirements: list[Requirement],
    index: PlantIndex,
    pid_limits: dict[str, dict[str, Quantity]],
) -> list[Finding]:
    """Compare the SOP's limits against the drawing's nameplate data.

    Agreement is reported as a ``verified`` result. Conforming documents may legitimately agree
    everywhere, and a report that shows nothing in that case reads as broken rather than as a pass.
    """
    out: list[Finding] = []
    recall = index.recall_estimate

    for req in requirements:
        if not req.is_resolved:
            out.append(
                Finding(
                    check="sop_subject_unresolved",
                    status=Status.NEEDS_REVIEW,
                    severity=Severity.LOW,
                    title=f"Could not resolve an equipment tag from {req.subject_raw!r}",
                    detail="The requirement cannot be checked until its subject is identified.",
                    confidence=0.6,
                    sop_evidence=req.evidence,
                )
            )
            continue

        for tag in req.subject_tags:
            key = f"{tag}:{req.subject_part}" if req.subject_part else tag
            found = pid_limits.get(key) or pid_limits.get(tag)

            if found is None:
                # Absence-based: capped, flagged, and never critical. Extraction may simply have
                # missed the nameplate block.
                severity = Severity.MEDIUM if recall > 0.8 else Severity.LOW
                out.append(
                    Finding(
                        check="equipment_not_found_in_drawing",
                        status=Status.NEEDS_REVIEW,
                        severity=severity,
                        title=f"{tag} carries SOP limits but no drawing data was matched",
                        detail=(
                            "This may be an extraction gap rather than a document defect. "
                            f"Estimated extraction recall {recall:.0%}; severity is capped "
                            "accordingly and this is not reported as a conflict."
                        ),
                        confidence=min(0.5, max(recall, 0.1)),
                        subject=tag,
                        sop_evidence=req.evidence,
                        graph_incomplete=True,
                    )
                )
                continue

            for field_name, sop_quantity in req.quantities.items():
                pid_quantity = found.get(field_name)
                if pid_quantity is None:
                    # Absence is not a conflict. The drawing data may simply not have yielded
                    # this field, and reporting it as critical accuses a correct document on the
                    # strength of an extraction gap -- the exact failure the engine is designed
                    # to under-claim on.
                    out.append(
                        Finding(
                            check="design_limit",
                            status=Status.NEEDS_REVIEW,
                            severity=Severity.MEDIUM if recall > 0.8 else Severity.LOW,
                            title=(
                                f"{tag}"
                                f"{' ' + req.subject_part if req.subject_part else ''}: "
                                f"no {field_name} was read from the drawing"
                            ),
                            detail=(
                                "The comparison cannot run without the drawing-side value. "
                                "This is reported as unresolved, not as a conflict."
                            ),
                            confidence=min(0.5, max(recall, 0.1)),
                            subject=tag,
                            sop_evidence=req.evidence,
                            graph_incomplete=True,
                        )
                    )
                    continue
                agree, message = _compare(field_name, sop_quantity, pid_quantity)
                out.append(
                    Finding(
                        check="design_limit",
                        status=Status.VERIFIED if agree else Status.FINDING,
                        severity=Severity.INFO if agree else Severity.CRITICAL,
                        title=(
                            f"{tag}"
                            f"{' ' + req.subject_part if req.subject_part else ''}: {message}"
                        ),
                        detail=(
                            "Operating outside a design limit is a deviation with safety "
                            "consequences, so a genuine mismatch is critical."
                            if not agree
                            else "SOP and drawing agree."
                        ),
                        confidence=0.95 if agree else 0.9,
                        subject=tag,
                        sop_evidence=req.evidence,
                        pid_evidence=str(found.get(field_name)) if found.get(field_name) else None,
                    )
                )
    return out


def check_facility_scope(sop: SopDocument, drawing_titles: list[str]) -> list[Finding]:
    """Confirm the SOP and the drawings describe the same facility."""
    if not sop.facility_hints or not drawing_titles:
        return []
    haystack = " ".join(drawing_titles).lower()
    shared = sorted(h for h in sop.facility_hints if h in haystack)
    if shared:
        return [
            Finding(
                check="facility_scope",
                status=Status.VERIFIED,
                severity=Severity.INFO,
                title=f"SOP and drawings share facility scope ({', '.join(shared)})",
                detail=f"SOP title: {sop.title}",
                confidence=0.8,
                sop_evidence=sop.title,
            )
        ]
    return [
        Finding(
            check="facility_scope",
            status=Status.NEEDS_REVIEW,
            severity=Severity.MEDIUM,
            title="SOP and drawings may describe different facilities",
            detail=(
                f"No shared place name between the SOP title ({sop.title!r}) and the drawing "
                "titles. Cross-referencing two unrelated documents produces meaningless findings."
            ),
            confidence=0.5,
            sop_evidence=sop.title,
        )
    ]


# --- Layer 3: procedure feasibility ---------------------------------------------------------------


def check_referenced_tags(sop: SopDocument, index: PlantIndex) -> list[Finding]:
    """Every tag the SOP names should exist in the drawings."""
    import re

    out: list[Finding] = []
    pattern = re.compile(r"\b([A-Z]{1,4}-\d{2,4}(?:-\d{1,3})?[A-Z]?)\b")
    referenced: set[str] = set()
    for paragraph in sop.paragraphs:
        referenced.update(pattern.findall(paragraph.upper()))

    known = {t.canonical for t in index.tags.values() if t.canonical}
    for tag in sorted(referenced - known):
        out.append(
            Finding(
                check="sop_references_unknown_tag",
                status=Status.NEEDS_REVIEW,
                severity=Severity.LOW,
                title=f"SOP names {tag}, which was not found in the drawings",
                detail="May be an extraction gap or a reference to another sheet.",
                confidence=0.4,
                subject=tag,
                graph_incomplete=True,
            )
        )
    return out


# --- orchestration --------------------------------------------------------------------------------


def run(
    sop: SopDocument,
    index: PlantIndex,
    pid_limits: dict[str, dict[str, Quantity]],
    drawing_titles: list[str] | None = None,
    tag_occurrences: dict[str, int] | None = None,
) -> CrossReferenceReport:
    """Run every layer and collect the results."""
    report = CrossReferenceReport()
    report.extraction_recall = index.recall_estimate

    report.findings += check_tag_conformance(index)
    report.findings += check_duplicate_tags(index, tag_occurrences or {})
    report.findings += check_unresolved_symbols(index)
    report.findings += check_safety_devices(index)
    report.findings += check_facility_scope(sop, drawing_titles or [])
    report.findings += check_design_limits(sop.requirements, index, pid_limits)
    report.findings += check_referenced_tags(sop, index)

    if index.recall_estimate < 0.5:
        report.notes.append(
            f"Estimated extraction recall is {index.recall_estimate:.0%}. Absence-based findings "
            "are capped in severity and marked as possibly incomplete."
        )
    report.notes.append(
        "Verdicts are deterministic. No model participates in deciding whether something is a "
        "finding."
    )
    return report


def isa_edition_note() -> str:
    return (
        f"Safety semantics follow {isa.Edition.ISA_2009}; the base vocabulary is the reference "
        f"guide's ({isa.Edition.ISA_1984} letter table) with the SIS modifier overlaid."
    )

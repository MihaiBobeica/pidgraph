"""Cross-reference tests, including the fault-injection harness.

The supplied documents agree everywhere, so a passing run proves nothing about whether the
detector works. Correctness is therefore demonstrated by perturbing known-good inputs and
asserting each perturbation is caught -- where ground truth is exact by construction.
"""

from __future__ import annotations

import pytest

from pidgraph.crossref import checks as ck
from pidgraph.crossref.sop import (
    Quantity,
    Requirement,
    SopDocument,
    parse_quantity,
    resolve_subject,
)
from pidgraph.standards.tags import parse

TAGS = ["PI-715A", "DPIT-745-16", "PSV-715A", "F-715A", "F-715B", "V-745", "E-742", "AC-746"]


def make_index(**overrides) -> ck.PlantIndex:
    base = dict(
        tags={t.canonical: t for t in (parse(x) for x in TAGS) if t.canonical},
        node_count=480,
        isolated_count=188,
        unresolved_shapes=0,
        text_regions=1000,
        recognised_tags=900,
    )
    base.update(overrides)
    return ck.PlantIndex(**base)


def q(value, unit="psig", high=None) -> Quantity:
    return Quantity(value, high if high is not None else value, unit, str(value))


GOOD_LIMITS = {
    "F-715A": {"pressure": q(275), "temperature": q(100, "degF")},
    "F-715B": {"pressure": q(275), "temperature": q(100, "degF")},
    "V-745": {"pressure": q(300), "temperature": q(375, "degF")},
    "E-742:shell": {"pressure": q(300), "temperature": q(375, "degF")},
    "E-742:tube": {"pressure": q(300), "temperature": q(250, "degF")},
    "AC-746": {"pressure": q(350), "temperature": q(-20, "degF", 400)},
}


def requirement(ordinal, subject, pressure, temperature, unit="degF", high=None):
    tags, part = resolve_subject(subject)
    return Requirement(
        ordinal=ordinal,
        subject_raw=subject,
        subject_tags=tags,
        subject_part=part,
        quantities={
            "pressure": q(pressure),
            "temperature": Quantity(
                temperature, high if high is not None else temperature, unit, ""
            ),
        },
        evidence=subject,
    )


GOOD_REQUIREMENTS = [
    requirement(0, "F-715 A and B Particulate Filters", 275, 100),
    requirement(1, "V-745 Stabilizer Tower", 300, 375),
    requirement(2, "E-742 Exchanger (Shell)", 300, 375),
    requirement(3, "E-742 Exchanger (Tube)", 300, 250),
    requirement(4, "AC-746 After Cooler", 350, -20, high=400),
]


class TestQuantityParsing:
    def test_scalar_and_range(self):
        assert parse_quantity("275", "psig") == Quantity(275, 275, "psig", "275")
        rng = parse_quantity("-20 to 400", "degF")
        assert (rng.minimum, rng.maximum) == (-20, 400)

    def test_slash_is_a_range_only_in_a_known_unit_column(self):
        """A two-part slash value in a temperature column is a range."""
        rng = parse_quantity("-20/400", "degF")
        assert rng is not None and (rng.minimum, rng.maximum) == (-20, 400)

    def test_a_three_part_value_is_not_a_range(self):
        """A motor rating like 460/3/60 is volts, phases and hertz -- not a range."""
        assert parse_quantity("460/3/60", "degF") is None

    def test_units_must_match_to_agree(self):
        assert not q(275, "psig").matches(q(275, "barg"))


class TestHappyPath:
    def test_full_agreement_produces_verified_results_not_an_empty_report(self):
        """Conforming documents may legitimately agree. A blank report would read as broken."""
        report = ck.run(SopDocument(path="x", requirements=GOOD_REQUIREMENTS), make_index(),
                        GOOD_LIMITS)
        assert len(report.verified) >= 10
        assert not [f for f in report.issues if f.severity is ck.Severity.CRITICAL]

    def test_sub_components_are_compared_separately(self):
        """Shell and tube are two limits on one item and must not be merged."""
        report = ck.run(SopDocument(path="x", requirements=GOOD_REQUIREMENTS), make_index(),
                        GOOD_LIMITS)
        titles = " ".join(f.title for f in report.verified)
        assert "E-742 shell" in titles and "E-742 tube" in titles


class TestFaultInjection:
    """Each case perturbs a known-good input; ground truth is exact by construction."""

    def _run(self, requirements=None, limits=None, index=None):
        return ck.run(
            SopDocument(path="x", requirements=requirements or GOOD_REQUIREMENTS),
            index or make_index(),
            limits if limits is not None else GOOD_LIMITS,
        )

    def test_a_changed_pressure_is_caught_as_critical(self):
        mutated = list(GOOD_REQUIREMENTS)
        mutated[1] = requirement(1, "V-745 Stabilizer Tower", 250, 375)
        report = self._run(requirements=mutated)
        critical = [f for f in report.issues if f.severity is ck.Severity.CRITICAL]
        assert critical, "a design-limit conflict must be reported"
        assert any("V-745" in f.title for f in critical)

    def test_a_changed_temperature_is_caught(self):
        mutated = list(GOOD_REQUIREMENTS)
        mutated[3] = requirement(3, "E-742 Exchanger (Tube)", 300, 999)
        report = self._run(requirements=mutated)
        assert any(f.severity is ck.Severity.CRITICAL for f in report.issues)

    def test_a_flipped_range_still_compares_correctly(self):
        """Range order must not decide agreement; the limits are the same either way."""
        mutated = list(GOOD_REQUIREMENTS)
        mutated[4] = requirement(4, "AC-746 After Cooler", 350, 400, high=-20)
        report = self._run(requirements=mutated)
        assert not [f for f in report.issues if f.severity is ck.Severity.CRITICAL]

    def test_a_renamed_item_is_reported_but_not_as_a_conflict(self):
        """Absence is not a conflict. It may be an extraction gap, so it is capped and flagged."""
        mutated = list(GOOD_REQUIREMENTS)
        mutated[2] = requirement(2, "E-743 Exchanger (Shell)", 300, 375)
        report = self._run(requirements=mutated)
        absent = [f for f in report.issues if f.check == "equipment_not_found_in_drawing"]
        assert absent
        assert all(f.graph_incomplete for f in absent)
        assert all(f.severity is not ck.Severity.CRITICAL for f in absent)

    def test_a_unit_swap_is_not_silently_accepted(self):
        """275 psig and 275 barg are not the same limit."""
        limits = {
            **GOOD_LIMITS,
            "V-745": {"pressure": q(300, "barg"), "temperature": q(375, "degF")},
        }
        report = self._run(limits=limits)
        assert any(
            f.severity is ck.Severity.CRITICAL and "V-745" in f.title for f in report.issues
        )

    def test_low_recall_lowers_severity_of_absence_findings(self):
        """The system under-claims when it knows its own extraction was poor."""
        limits = {k: v for k, v in GOOD_LIMITS.items() if not k.startswith("V-745")}
        high = self._run(limits=limits, index=make_index(text_regions=1000, recognised_tags=900))
        low = self._run(limits=limits, index=make_index(text_regions=1000, recognised_tags=100))
        high_sev = [f.severity for f in high.issues if f.check == "equipment_not_found_in_drawing"]
        low_sev = [f.severity for f in low.issues if f.check == "equipment_not_found_in_drawing"]
        assert ck.Severity.MEDIUM in high_sev
        assert all(s is ck.Severity.LOW for s in low_sev)


class TestIntraDocumentChecks:
    def test_non_conformant_identification_is_reported(self):
        report = ck.run(SopDocument(path="x"), make_index(), {})
        assert any(f.check == "tag_not_conformant" for f in report.issues)

    def test_duplicate_tags_are_reported_without_asserting_the_cause(self):
        report = ck.run(SopDocument(path="x"), make_index(), {}, tag_occurrences={"PI-715A": 3})
        dup = [f for f in report.issues if f.check == "duplicate_tag"]
        assert dup and "cannot distinguish" in dup[0].detail

    def test_facility_mismatch_is_flagged(self):
        sop = SopDocument(path="x", title="Ashford Terminal Purge")
        report = ck.run(sop, make_index(), {}, drawing_titles=["MAJORSVILLE CGP"])
        assert any(f.check == "facility_scope" and f.status is ck.Status.NEEDS_REVIEW
                   for f in report.findings)

    def test_verdicts_are_deterministic(self):
        a = ck.run(SopDocument(path="x", requirements=GOOD_REQUIREMENTS), make_index(), GOOD_LIMITS)
        b = ck.run(SopDocument(path="x", requirements=GOOD_REQUIREMENTS), make_index(), GOOD_LIMITS)
        assert [f.to_dict() for f in a.findings] == [f.to_dict() for f in b.findings]


@pytest.mark.corpus
class TestRealDocument:
    def test_the_supplied_sop_parses_into_checkable_requirements(self):
        from pidgraph.crossref.sop import load
        from pidgraph.paths import InputNotFound, find_sop

        try:
            sop = load(find_sop())
        except InputNotFound as exc:
            pytest.skip(str(exc))
        assert len(sop.requirements) >= 5
        assert all(r.is_resolved for r in sop.requirements)
        # The two-train row must expand, or half the plant is lost.
        assert any(len(r.subject_tags) == 2 for r in sop.requirements)
        # The range row must survive as a range.
        assert any(not v.is_scalar for r in sop.requirements for v in r.quantities.values())

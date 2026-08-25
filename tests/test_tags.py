"""Tag parser tests.

The safety-gate cases are the ones that matter most: misclassifying a switch as a safety device,
or missing a safety-instrumented loop entirely, is a safety-relevant error rather than a cosmetic
one.
"""

from __future__ import annotations

import pytest

from pidgraph.standards import isa
from pidgraph.standards.tags import Conformance, TagKind, parse


class TestSafetySemantics:
    """docs/assumptions.md STD-01."""

    @pytest.mark.parametrize("tag", ["PSV-715A", "TSV-745", "PSE-101", "FSV-200", "TSE-300"])
    def test_self_actuated_protective_elements_are_safety_devices(self, tag):
        assert parse(tag).is_safety_device

    @pytest.mark.parametrize("tag", ["LSV-745", "ASE-100", "ZSV-200", "LSHH-745", "TSH-745"])
    def test_everything_else_with_an_s_is_a_switch_not_a_safety_device(self, tag):
        """The gate is the first letter plus protective function, not the trailing letters.

        Gating on trailing V or E instead would classify all of these as safety devices.
        """
        assert not parse(tag).is_safety_device

    def test_switch_s_is_not_treated_as_a_variable_modifier(self):
        """``LSHH`` is a level switch, not a "level safety" loop."""
        parsed = parse("LSHH-745")
        assert parsed.variable == "L"
        assert parsed.variable_modifier is None

    def test_sis_modifier_is_z_not_s(self):
        """The reference guide's table predates SIS, so this comes from the overlaid 2009 delta."""
        assert isa.SIS_MODIFIER == "Z"
        assert not parse("PSV-715A").is_sis


class TestNonConformantVariants:
    def test_leading_differential_is_normalised_and_reported(self):
        """The widely used form writes the modifier first; the conformant order is second."""
        parsed = parse("DPIT-745-16")
        assert parsed.canonical == "PDIT-745-16"
        assert parsed.conformance is Conformance.NORMALISED
        assert parsed.variable == "P"
        assert parsed.variable_modifier == "D"
        assert any("conformant order" in n for n in parsed.notes)

    def test_the_observed_form_is_retained_not_discarded(self):
        parsed = parse("DPIT-745-16")
        assert parsed.raw == "DPIT-745-16"

    def test_the_guides_own_lowercase_form_parses_identically(self):
        assert parse("PdI-715A").canonical == parse("PDI-715A").canonical


class TestRuleOrdering:
    def test_equipment_is_matched_before_instrument(self):
        """``P-745`` is a pump. Without the ordering it parses as a pressure loop."""
        assert parse("P-745").kind is TagKind.EQUIPMENT

    def test_equipment_train_suffix_is_kept(self):
        parsed = parse("F-715 A")
        assert parsed.kind is TagKind.EQUIPMENT
        assert parsed.canonical == "F-715A"

    def test_users_choice_valve_is_not_an_instrument_loop(self):
        parsed = parse("MV-715-01")
        assert parsed.kind is TagKind.VALVE
        assert parsed.loop_id is None
        assert any("user's-choice" in n for n in parsed.notes)


class TestLoopGrouping:
    def test_a_thermowell_and_its_indicator_share_a_loop(self):
        assert parse("TI-745-19").loop_id == parse("TW-745-19").loop_id

    def test_different_variables_do_not_share_a_loop(self):
        assert parse("PI-745-19").loop_id != parse("TI-745-19").loop_id


class TestLineNumbers:
    def test_variable_field_count_is_preserved(self):
        """Field arity is company convention, so extra fields are kept rather than dropped."""
        short = parse('6"-PL-2000-D')
        long = parse('1"-DC-3055-D-E-HT')
        assert short.kind is TagKind.LINE_NUMBER
        assert long.kind is TagKind.LINE_NUMBER
        assert short.fields["size"] == "6"
        assert long.fields["service"] == "DC"
        assert len(long.fields) > len(short.fields)

    def test_line_numbers_are_flagged_as_company_convention(self):
        assert any("company convention" in n for n in parse('6"-PL-2000-D').notes)


class TestNegatives:
    @pytest.mark.parametrize("text", ["PITTSBURGH", "PHILADELPHIA", "HOUSTON", "", "   "])
    def test_boilerplate_text_is_not_a_tag(self, text):
        """Title-block and footer text begins with valid function letters and must be rejected."""
        assert parse(text).conformance is Conformance.UNPARSED

    def test_connectors_are_distinguished_from_equipment(self):
        assert parse("[0301C]").kind is TagKind.OFF_PAGE_CONNECTOR


class TestFailureCodes:
    def test_exactly_five_failure_positions_and_fi_is_not_one(self):
        assert set(isa.FAILURE_POSITIONS) == {"FO", "FC", "FL", "FL/DO", "FL/DC"}
        assert "FI" not in isa.FAILURE_POSITIONS

    def test_fc_is_recorded_as_ambiguous(self):
        """The reference guide defines ``FC`` twice; context must resolve it."""
        assert "FC" in isa.AMBIGUOUS_ABBREVIATIONS
        assert len(isa.AMBIGUOUS_ABBREVIATIONS["FC"]) == 2


class TestAmbiguousShapes:
    def test_diamond_in_square_is_not_resolved_to_one_class(self):
        """The standard heads that column with two meanings; geometry cannot separate them."""
        candidates = isa.AMBIGUOUS_SHAPES["diamond_in_square"]
        assert len(candidates) >= 2
        assert any("safety instrumented" in c for c in candidates)

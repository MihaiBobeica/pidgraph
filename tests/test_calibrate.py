"""Calibration tests.

The headline test is :meth:`TestScaleInvariance.test_module_scales_and_symbol_ratio_is_invariant`.
It rescales a real drawing and asserts that the recovered module scales with it while the symbol
size *in modules* does not move. That is the guarantee that no absolute dimension survives in the
code: if any threshold were hardcoded in points, the ratio would drift.
"""

from __future__ import annotations

import pytest

from pidgraph.extract.calibrate import (
    CalibrationError,
    Scale,
    calibrate_document,
    calibrate_page,
    detect_sheet,
    narrow_stroke_width,
)
from pidgraph.paths import InputNotFound, find_pid

pymupdf = pytest.importorskip("pymupdf")


@pytest.fixture(scope="module")
def pid_path():
    try:
        return find_pid()
    except InputNotFound as exc:
        pytest.skip(str(exc))


def rescaled_copy(src_path, factor: float):
    """Return an in-memory PDF with every page geometrically scaled by ``factor``."""
    src = pymupdf.open(str(src_path))
    out = pymupdf.open()
    for page in src:
        rect = page.rect
        target = pymupdf.Rect(0, 0, rect.width * factor, rect.height * factor)
        new_page = out.new_page(width=target.width, height=target.height)
        new_page.show_pdf_page(target, src, page.number)
    src.close()
    return out


class TestSheetDetection:
    def test_recognises_standard_sheets_in_either_series(self):
        assert detect_sheet(11 * 72, 17 * 72) == ("ANSI_B", "ISA")
        assert detect_sheet(22 * 72, 34 * 72) == ("ANSI_D", "ISA")
        # ISO A1 in points.
        a1 = (594 / 25.4 * 72, 841 / 25.4 * 72)
        assert detect_sheet(*a1) == ("ISO_A1", "ISO")

    def test_orientation_does_not_matter(self):
        assert detect_sheet(17 * 72, 11 * 72) == detect_sheet(11 * 72, 17 * 72)

    def test_unrecognised_sheet_reports_unknown_rather_than_guessing(self):
        name, system = detect_sheet(300.0, 400.0)
        assert name == "custom"
        assert system == "unknown"


class TestObservables:
    def test_narrow_stroke_ignores_sparse_widths(self):
        """A single hairline must not outvote the real narrow class.

        Widths are weighted by the ink they draw, so one stray thin path cannot define the
        narrow stroke for the whole page.
        """
        pt = pymupdf.Point
        paths = [
            {"width": 0.05, "items": [("l", pt(0, 0), pt(0.1, 0))]},
            *[
                {"width": 0.5, "items": [("l", pt(0, 0), pt(100, 0))]}
                for _ in range(50)
            ],
        ]
        narrow, hist = narrow_stroke_width(paths)
        assert narrow == 0.5
        assert 0.05 in hist and 0.5 in hist


class TestSuppliedCorpus:
    """Calibration against the sample. Ratios are asserted; absolute values are only reported."""

    def test_recovers_a_module_with_agreeing_estimators(self, pid_path):
        scales = calibrate_document(str(pid_path))
        assert scales
        for scale in scales:
            trusted = [e for e in scale.estimators if e.trusted]
            assert len(trusted) >= 2, "need at least two estimators to cross-check"
            assert scale.confidence >= 0.9, scale.warnings

    def test_symbol_measures_the_standard_seven_modules(self, pid_path):
        """ISA Table 6.1 dimensions the device/function circle at 7 m.u. (8 as an option).

        Asserted as a ratio, so it holds whatever the plot scale.
        """
        for scale in calibrate_document(str(pid_path)):
            assert scale.symbol_modules is not None
            assert scale.symbol_modules == pytest.approx(7.0, abs=0.35)

    def test_derived_resolution_is_in_a_workable_band(self, pid_path):
        for scale in calibrate_document(str(pid_path)):
            assert 150 <= scale.render_dpi() <= 1600


class TestScaleInvariance:
    """The guarantee that no absolute dimension survives anywhere in the pipeline."""

    @pytest.mark.parametrize("factor", [0.5, 2.0])
    def test_module_scales_and_symbol_ratio_is_invariant(self, pid_path, factor):
        base = calibrate_page(pymupdf.open(str(pid_path))[0])
        scaled_doc = rescaled_copy(pid_path, factor)
        try:
            scaled = calibrate_page(scaled_doc[0])
        finally:
            scaled_doc.close()

        # The module is a length: it must track the rescale.
        assert scaled.module == pytest.approx(base.module * factor, rel=0.02)

        # The symbol size *in modules* is dimensionless: it must not move at all.
        assert base.symbol_modules is not None and scaled.symbol_modules is not None
        assert scaled.symbol_modules == pytest.approx(base.symbol_modules, rel=0.02)

        # Resolution is derived, so a smaller plot must demand a higher resolution.
        assert scaled.render_dpi() == pytest.approx(base.render_dpi() / factor, rel=0.02)

    def test_unit_system_is_stable_under_rescale_of_a_standard_sheet(self, pid_path):
        """Rescaling changes which sheet is matched, but must not silently change ratio tables.

        A doubled ANSI B page is ANSI D-ish; what matters is that the system stays ISA rather
        than flipping to ISO ratios, which would change every derived threshold.
        """
        scaled_doc = rescaled_copy(pid_path, 2.0)
        try:
            scaled = calibrate_page(scaled_doc[0])
        finally:
            scaled_doc.close()
        assert scaled.unit_system in ("ISA", "unknown")


class TestFailsLoudly:
    def test_blank_page_raises_rather_than_returning_a_guess(self):
        """A wrong module produces confident garbage everywhere, so refusing is the only safe exit."""
        doc = pymupdf.open()
        doc.new_page(width=11 * 72, height=17 * 72)
        try:
            with pytest.raises(CalibrationError):
                calibrate_page(doc[0])
        finally:
            doc.close()

    def test_scale_u_is_the_only_route_to_an_absolute_size(self):
        scale = Scale(unit_system="ISA", module=2.5, sheet="ANSI_B", page_width_pt=1.0, page_height_pt=1.0)
        assert scale.u(7.0) == 17.5
        assert scale.u(0.2) == 0.5

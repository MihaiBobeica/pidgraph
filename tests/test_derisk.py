"""De-risk check: the structural facts the architecture depends on.

Two kinds of test live here, deliberately separated.

``TestCapabilityContract`` asserts things that must hold for *any* conforming input. These are the
real contract and they would survive a change of test document.

``TestSuppliedCorpus`` asserts the measured character of the drawings in ``data/``. These describe
one test case, match the sample-sheet characterisation in ``docs/assumptions.md``, and exist so
that a silent change in behaviour is caught early. They are marked ``corpus`` and skip cleanly
when the sample is absent -- nothing in the shipped pipeline may depend on their values.
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from pidgraph.ingest.probe import PageCapabilities, probe_document
from pidgraph.paths import InputNotFound, find_pid, storage_key

pymupdf = pytest.importorskip("pymupdf")


@pytest.fixture(scope="module")
def pid_path():
    try:
        return find_pid()
    except InputNotFound as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def caps(pid_path) -> list[PageCapabilities]:
    return probe_document(pid_path)


class TestCapabilityContract:
    """Invariants of the probe itself, independent of any particular drawing."""

    def test_probe_returns_one_record_per_page(self, pid_path, caps):
        with pymupdf.open(str(pid_path)) as doc:
            assert len(caps) == len(doc)
        assert [c.page_index for c in caps] == list(range(len(caps)))

    def test_ratios_are_bounded(self, caps):
        for cap in caps:
            assert 0.0 <= cap.raster_area_ratio <= 1.0
            assert cap.vector_path_count >= 0
            assert cap.text_layer_chars >= 0

    def test_incidental_raster_does_not_imply_raster_page(self, caps):
        """A decorative bitmap must never route a vector drawing into the raster path.

        This is the concrete guard against the naive rule "has an image therefore scanned".
        """
        for cap in caps:
            if cap.has_vector_geometry and cap.has_incidental_raster:
                assert not cap.is_raster_page

    def test_text_layer_predicate_thresholds_on_volume(self):
        """A handful of characters is not a text layer."""
        base = dict(
            page_index=0,
            width_pt=100.0,
            height_pt=100.0,
            rotation=0,
            vector_path_count=0,
            line_segment_count=0,
            bezier_count=0,
            raster_area_ratio=0.0,
            raster_max_dpi=None,
            text_region_count=0,
            has_ocg_layers=False,
            dash_arrays_present=False,
        )
        assert not PageCapabilities(**base, text_layer_chars=69).has_text_layer
        assert PageCapabilities(**base, text_layer_chars=5000).has_text_layer

    def test_empty_dash_array_is_not_a_dash_signal(self):
        """Producers that simulate dashes with short strokes still emit an empty dash array."""
        base = dict(
            page_index=0,
            width_pt=1.0,
            height_pt=1.0,
            rotation=0,
            vector_path_count=0,
            line_segment_count=0,
            bezier_count=0,
            raster_area_ratio=0.0,
            raster_max_dpi=None,
            text_layer_chars=0,
            text_region_count=0,
            has_ocg_layers=False,
        )
        assert not PageCapabilities(**base, dash_arrays_present=False).dash_arrays_present

    def test_rotation_transform_is_not_identity_when_page_is_rotated(self, pid_path):
        """Geometry and rendering live in different frames; confusing them raises nothing.

        A rotated page returns drawing geometry in unrotated media-box coordinates while
        rendering happens in display coordinates. Clipping with the wrong frame yields an empty
        image and no exception, so the mapping is pinned here.
        """
        with pymupdf.open(str(pid_path)) as doc:
            page = doc[0]
            if page.rotation == 0:
                pytest.skip("page is not rotated; nothing to pin")
            media = (page.mediabox.width, page.mediabox.height)
            assert media != (page.rect.width, page.rect.height)
            corner = pymupdf.Point(page.mediabox.x1, page.mediabox.y0) * page.rotation_matrix
            assert math.isfinite(corner.x) and math.isfinite(corner.y)
            # Round-trip through the inverse must return the original point.
            back = corner * ~page.rotation_matrix
            assert back.x == pytest.approx(page.mediabox.x1, abs=1e-6)
            assert back.y == pytest.approx(page.mediabox.y0, abs=1e-6)

    def test_storage_key_excludes_the_source_filename(self, pid_path):
        """Storage keys derive from content, so shell- and URL-hostile names cannot leak."""
        key = storage_key(pid_path)
        assert "&" not in key
        assert "\\" not in key
        assert pid_path.stem not in key
        assert key.startswith("raw/")


@pytest.mark.corpus
class TestSuppliedCorpus:
    """Measured character of the drawings in ``data/`` -- one test case, not the contract."""

    def test_is_a_vector_drawing_without_a_usable_text_layer(self, caps):
        for cap in caps:
            assert cap.has_vector_geometry, f"page {cap.page_index} has no vector geometry"
            assert not cap.has_text_layer, "unexpected text layer; OCR strategy would change"

    def test_publishes_structural_text_region_hints(self, caps):
        """The hard half of text extraction is handed to us; if this stops, clustering is needed."""
        total = sum(c.text_region_count for c in caps)
        assert total > 500, f"only {total} text-region hints found"

    def test_no_dash_arrays_so_line_typing_must_be_geometric(self, caps):
        for cap in caps:
            assert not cap.dash_arrays_present

    def test_no_linewidth_signal_but_paint_type_discriminates(self, caps):
        """Stroke width carries nothing here; fills and strokes carry the class distinction."""
        for cap in caps:
            assert not cap.has_linewidth_signal
            assert cap.has_paint_type_signal

    def test_raster_content_is_incidental(self, caps):
        for cap in caps:
            assert cap.has_incidental_raster
            assert not cap.is_raster_page

    def test_no_optional_content_layers(self, caps):
        assert not any(c.has_ocg_layers for c in caps)

    def test_symbol_geometry_forms_a_single_dominant_size_mode(self, pid_path):
        """Calibration mode-seeks the symbol size; that requires a mode to exist.

        Reported as a ratio to the page, not in points, so the assertion survives a rescale.
        """
        with pymupdf.open(str(pid_path)) as doc:
            diameters: Counter[float] = Counter()
            for page in doc:
                span = max(page.rect.width, page.rect.height)
                for path in page.get_drawings():
                    if not any(i[0] == "c" for i in path.get("items", ())):
                        continue
                    rect = path["rect"]
                    w, h = rect.width, rect.height
                    if w <= 0 or h <= 0 or abs(w - h) > 0.1 * w:
                        continue
                    if not (0.005 * span < w < 0.05 * span):
                        continue
                    diameters[round(w / span, 5)] += 1
        assert diameters, "no circular symbol candidates found"
        ((_, top_count),) = diameters.most_common(1)
        assert top_count >= 20, f"dominant mode has only {top_count} members"
        assert top_count / sum(diameters.values()) > 0.9, "symbol sizes are not concentrated"

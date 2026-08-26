"""SOP load dispatch: Word, PDF tables, and plain text."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from pidgraph.crossref.sop import _requirements_from_grid, load
from pidgraph.preview import as_html, describe

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _write_docx(path: Path, paragraph: str = "Hello") -> None:
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}">
  <w:body>
    <w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Equipment</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Pressure (psig)</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc><w:p><w:r><w:t>V-100 Vessel</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>150</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
    <w:sectPr/>
  </w:body>
</w:document>"""
    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Test SOP</dc:title>
  <dc:creator>pidgraph</dc:creator>
</cp:coreProperties>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("docProps/core.xml", core)


def _write_limits_pdf(path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    x0, y0 = 72, 100
    col_w = [180, 150, 150]
    row_h = 24
    headers = ["Equipment", "Pressure (psig)", "Temperature (F)"]
    rows = [["V-100 Vessel", "150", "80"]]
    xs = [x0]
    for width in col_w:
        xs.append(xs[-1] + width)
    ys = [y0 + i * row_h for i in range(len(rows) + 2)]
    for y in ys:
        page.draw_line(pymupdf.Point(xs[0], y), pymupdf.Point(xs[-1], y))
    for x in xs:
        page.draw_line(pymupdf.Point(x, ys[0]), pymupdf.Point(x, ys[-1]))

    def put(col: int, row: int, text: str) -> None:
        page.insert_text(pymupdf.Point(xs[col] + 6, ys[row] + 16), text, fontsize=10)

    for col, header in enumerate(headers):
        put(col, 0, header)
    for row_i, row in enumerate(rows, start=1):
        for col, cell in enumerate(row):
            put(col, row_i, cell)
    doc.set_metadata({"title": "Plant SOP"})
    doc.save(str(path))
    doc.close()


def test_load_docx_lifts_table(tmp_path: Path) -> None:
    path = tmp_path / "sop.docx"
    _write_docx(path, "Plant procedure")
    sop = load(path)
    assert sop.title == "Test SOP"
    assert "Plant procedure" in sop.paragraphs
    assert any(r.subject_tags == ("V-100",) for r in sop.requirements)
    assert sop.requirements[0].quantities["pressure"].minimum == 150


def test_load_pdf_paragraphs_and_optional_table(tmp_path: Path) -> None:
    path = tmp_path / "sop.pdf"
    _write_limits_pdf(path)
    sop = load(path)
    assert any("V-100" in p for p in sop.paragraphs)
    if sop.requirements:
        assert any(r.subject_tags == ("V-100",) for r in sop.requirements)
        assert sop.requirements[0].quantities["pressure"].minimum == 150


def test_grid_helper_shared_by_pdf_and_docx() -> None:
    notes: list[str] = []
    rows = _requirements_from_grid(
        ["Equipment", "Pressure (psig)", "Temp (F)"],
        [["V-100 Vessel", "100 to 200", "50"]],
        0,
        notes,
    )
    assert len(rows) == 1
    assert rows[0].subject_tags == ("V-100",)
    assert rows[0].quantities["pressure"].minimum == 100
    assert rows[0].quantities["pressure"].maximum == 200
    assert not notes


def test_load_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "sop.txt"
    path.write_text("See V-100 before opening.", encoding="utf-8")
    sop = load(path)
    assert sop.paragraphs == ["See V-100 before opening."]
    assert sop.requirements == []


def test_load_rejects_legacy_doc(tmp_path: Path) -> None:
    path = tmp_path / "sop.doc"
    path.write_bytes(b"OLE")
    with pytest.raises(ValueError, match=r"legacy \.doc"):
        load(path)


def test_preview_docx_html(tmp_path: Path) -> None:
    path = tmp_path / "sop.docx"
    _write_docx(path, "Keep &amp; close V-100")
    html = as_html(path)
    assert "Test SOP" in html
    assert "Keep &amp; close V-100" in html
    assert "<table>" in html
    assert "V-100 Vessel" in html
    meta = describe(path)
    assert meta["kind"] == "docx" and meta["pages"] == 1


def test_preview_pdf_meta(tmp_path: Path) -> None:
    path = tmp_path / "sop.pdf"
    _write_limits_pdf(path)
    meta = describe(path)
    assert meta["kind"] == "pdf"
    assert meta["pages"] == 1

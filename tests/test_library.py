"""Library confinement tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pidgraph.library import LibraryError, confine, require_document, require_pdf, tree


def test_confine_stays_inside_root(tmp_path: Path) -> None:
    (tmp_path / "pid").mkdir()
    inside = confine("pid/diagram.pdf", root=tmp_path)
    assert inside == (tmp_path / "pid" / "diagram.pdf").resolve()
    assert inside.is_relative_to(tmp_path.resolve())


def test_confine_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(LibraryError):
        confine("../secret.pdf", root=tmp_path)
    with pytest.raises(LibraryError):
        confine("pid/../../secret.pdf", root=tmp_path)


def test_require_pdf_rejects_docx() -> None:
    with pytest.raises(LibraryError, match="PDF"):
        require_pdf(Path("sop.docx"))
    assert require_pdf(Path("drawing.PDF")).suffix.lower() == ".pdf"


def test_require_document_accepts_pdf_and_docx() -> None:
    assert require_document(Path("sop.docx")).suffix == ".docx"
    assert require_document(Path("drawing.PDF")).suffix.lower() == ".pdf"
    with pytest.raises(LibraryError, match=r"PDF and \.docx"):
        require_document(Path("notes.txt"))


def test_tree_lists_pdfs_and_docx(tmp_path: Path) -> None:
    (tmp_path / "pid").mkdir()
    (tmp_path / "pid" / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "sop").mkdir()
    (tmp_path / "sop" / "sop.docx").write_bytes(b"PK")
    (tmp_path / "sop" / "notes.txt").write_text("skip")
    listing = tree(tmp_path)
    names = {item["name"]: item for item in listing}
    assert "pid" in names and names["pid"]["type"] == "folder"
    assert names["pid"]["children"][0]["name"] == "a.pdf"
    assert names["pid"]["children"][0]["type"] == "pdf"
    sop_files = names["sop"]["children"]
    assert len(sop_files) == 1
    assert sop_files[0]["name"] == "sop.docx"
    assert sop_files[0]["type"] == "docx"


def test_library_cli_prints_tree_json(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pid").mkdir()
    (tmp_path / "pid" / "a.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("PIDGRAPH_INPUT_DIR", str(tmp_path))
    import json

    from pidgraph.library import main

    class Buf:
        def __init__(self) -> None:
            self.parts: list[str] = []

        def write(self, text: str) -> int:
            self.parts.append(text)
            return len(text)

    buf = Buf()
    monkeypatch.setattr("sys.stdout", buf)
    assert main() == 0
    payload = json.loads("".join(buf.parts))
    assert payload["tree"][0]["name"] == "pid"
    assert payload["tree"][0]["children"][0]["name"] == "a.pdf"

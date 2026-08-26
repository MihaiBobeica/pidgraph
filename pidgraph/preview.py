"""Preview a library document for the review UI.

PDF pages stay PNG via :mod:`pidgraph.render`. Word files have no page raster in this stack, so
the same OOXML walk the SOP parser uses is turned into a small HTML document.
"""

from __future__ import annotations

import json
import sys
import zipfile
from html import escape
from pathlib import Path
from xml.etree import ElementTree

from pidgraph.crossref.sop import DC, W, _grid_cells, _text_of

_PAPER_CSS = """
body { margin: 0; background: #070b0f; }
.paper {
  background: #f4f1ea; color: #1a1a1a;
  max-width: 800px; margin: 24px auto; padding: 48px 56px;
  font: 14px/1.5 Georgia, "Times New Roman", serif;
  min-height: 90vh;
}
.paper h1 { font-size: 18px; margin: 0 0 16px; }
.paper p { margin: 0 0 10px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0;
        font: 13px/1.4 ui-sans-serif, system-ui, sans-serif; }
th, td { border: 1px solid #c8c0b4; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #ebe4d8; }
"""


def describe(path: str | Path) -> dict:
    """Kind and page count for the review UI's page buttons."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(str(p)) as doc:
            return {"kind": "pdf", "pages": int(doc.page_count), "suffix": suffix}
    if suffix == ".docx":
        return {"kind": "docx", "pages": 1, "suffix": suffix}
    raise ValueError(f"unsupported preview format: {suffix or '(none)'}")


def as_html(path: str | Path) -> str:
    """HTML preview. PDF is rendered as PNG elsewhere; this is for Word (and plain text)."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".docx":
        title, body = _docx_body(p)
        return _wrap(title, body)
    if suffix in {".txt", ".md"}:
        text = p.read_text(encoding="utf-8", errors="replace")
        paragraphs = "".join(f"<p>{escape(line)}</p>" for line in text.splitlines() if line.strip())
        return _wrap(p.stem, paragraphs or "<p></p>")
    raise ValueError("HTML preview is for .docx; PDF pages are rendered as PNG")


def _wrap(title: str, body: str) -> str:
    heading = f"<h1>{escape(title)}</h1>" if title else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title or 'document')}</title>"
        f"<style>{_PAPER_CSS}</style></head>"
        f"<body><article class='paper'>{heading}{body}</article></body></html>"
    )


def _docx_body(p: Path) -> tuple[str, str]:
    with zipfile.ZipFile(p) as archive:
        body_xml = archive.read("word/document.xml").decode("utf-8")
        try:
            core_xml = archive.read("docProps/core.xml").decode("utf-8")
        except KeyError:
            core_xml = ""
    title = ""
    if core_xml:
        core = ElementTree.fromstring(core_xml)
        title = (core.findtext(f"{DC}title") or "").strip()
    root = ElementTree.fromstring(body_xml)
    body = root.find(f"{W}body")
    if body is None:
        return title, "<p></p>"
    parts: list[str] = []
    _emit(body, parts)
    return title, "".join(parts) or "<p></p>"


def _emit(element, parts: list[str]) -> None:
    if element.tag == f"{W}p":
        text = (_text_of(element) or "").strip()
        if text:
            parts.append(f"<p>{escape(text)}</p>")
        return
    if element.tag == f"{W}tbl":
        parts.append(_table_html(element))
        return
    for child in element:
        _emit(child, parts)


def _table_html(table) -> str:
    rows_html: list[str] = []
    for index, row in enumerate(table.findall(f"{W}tr")):
        cell_tag = "th" if index == 0 else "td"
        cells = _grid_cells(row)
        rows_html.append(
            "<tr>"
            + "".join(f"<{cell_tag}>{escape(cell)}</{cell_tag}>" for cell in cells)
            + "</tr>"
        )
    return f"<table>{''.join(rows_html)}</table>"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2 or args[0] not in {"--meta", "--html"}:
        print("usage: python -m pidgraph.preview --meta|--html <path>", file=sys.stderr)
        return 2
    path = args[1]
    try:
        if args[0] == "--meta":
            sys.stdout.buffer.write(json.dumps(describe(path)).encode("utf-8"))
        else:
            sys.stdout.buffer.write(as_html(path).encode("utf-8"))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

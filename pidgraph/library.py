"""Path confinement for the data library.

Every library listing is relative to :func:`data_root`. A path that escapes that root, or a file
that is not a PDF or ``.docx``, is refused. The review UI lists the tree by running this module,
so the same walk the tests assert is the one the pane shows.

Drawings stay PDF-only at extract time (:func:`require_pdf`). Procedures are PDF or Word, so the
tree lists both.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pidgraph.paths import data_root

PDF_SUFFIX = ".pdf"
DOCX_SUFFIX = ".docx"
DOCUMENT_SUFFIXES = {PDF_SUFFIX, DOCX_SUFFIX}


class LibraryError(ValueError):
    """A library request that would leave the data root or write a disallowed type."""


def confine(relative: str, *, root: Path | None = None) -> Path:
    """Resolve ``relative`` under the data root. Raises :class:`LibraryError` on escape."""
    base = (root or data_root()).resolve()
    text = (relative or "").replace("\\", "/").strip("/")
    if not text:
        return base
    if ".." in Path(text).parts:
        raise LibraryError("path escapes the data directory")
    candidate = (base / text).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise LibraryError("path escapes the data directory") from exc
    return candidate


def require_pdf(path: Path) -> Path:
    if path.suffix.lower() != PDF_SUFFIX:
        raise LibraryError("only PDF files are accepted")
    return path


def require_document(path: Path) -> Path:
    if path.suffix.lower() not in DOCUMENT_SUFFIXES:
        raise LibraryError("only PDF and .docx files are accepted")
    return path


def tree(root: Path | None = None) -> list[dict]:
    """Folder tree of PDFs and Word files. Other files are omitted; empty folders still appear."""
    base = (root or data_root()).resolve()
    if not base.is_dir():
        return []
    return _walk(base, base)


def _walk(directory: Path, base: Path) -> list[dict]:
    entries: list[dict] = []
    try:
        children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return entries
    for child in children:
        if child.name.startswith("."):
            continue
        rel = child.relative_to(base).as_posix()
        if child.is_dir():
            entries.append(
                {
                    "name": child.name,
                    "path": rel,
                    "type": "folder",
                    "children": _walk(child, base),
                }
            )
        elif child.is_file() and child.suffix.lower() in DOCUMENT_SUFFIXES:
            kind = "docx" if child.suffix.lower() == DOCX_SUFFIX else "pdf"
            entries.append({"name": child.name, "path": rel, "type": kind})
    return entries


def main(_argv: list[str] | None = None) -> int:
    """Print ``{root, tree}`` as JSON. Used by the review UI library pane."""
    payload = {"root": str(data_root().resolve()), "tree": tree()}
    sys.stdout.write(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

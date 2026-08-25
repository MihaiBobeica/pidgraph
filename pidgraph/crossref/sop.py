# ruff: noqa: RUF001 -- this module normalises the confusable dash characters that document
# producers emit, so it must name them literally.
"""SOP parsing.

Reads an Office Open XML document with the standard library only. A dedicated document library
would be one more dependency for a job that is a zip file containing XML, and the same code path
serves the fault-injection harness, which needs to rewrite the document rather than only read it.

Encoding is handled explicitly. These documents carry degree signs and typographic ellipses, and
reading them without naming UTF-8 produces mojibake that makes a temperature column unrecognisable
to the parser rather than raising.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
DC = "{http://purl.org/dc/elements/1.1/}"


@dataclass(frozen=True)
class Quantity:
    """A physical quantity with its unit, kept as a range so scalars are a degenerate case.

    Bounds are ordered on construction. A source may write a range either way round -- and one
    written "400 to -20" describes exactly the same limits as "-20 to 400" -- so normalising here
    means no comparison has to remember, and a transposed range cannot masquerade as a conflict.
    """

    minimum: float
    maximum: float
    unit: str
    raw: str

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            low, high = self.maximum, self.minimum
            object.__setattr__(self, "minimum", low)
            object.__setattr__(self, "maximum", high)

    @property
    def is_scalar(self) -> bool:
        return self.minimum == self.maximum

    def matches(self, other: Quantity, tolerance: float = 1e-6) -> bool:
        if self.unit != other.unit:
            return False
        return (
            abs(self.minimum - other.minimum) <= tolerance
            and abs(self.maximum - other.maximum) <= tolerance
        )

    def __str__(self) -> str:
        body = f"{self.minimum:g}" if self.is_scalar else f"{self.minimum:g} to {self.maximum:g}"
        return f"{body} {self.unit}".strip()


@dataclass(frozen=True)
class Requirement:
    """One checkable claim lifted from the document."""

    ordinal: int
    subject_raw: str
    subject_tags: tuple[str, ...]
    subject_part: str | None
    quantities: dict[str, Quantity]
    evidence: str

    @property
    def is_resolved(self) -> bool:
        return bool(self.subject_tags)


@dataclass
class SopDocument:
    path: str
    title: str = ""
    author: str = ""
    revision: str = ""
    status: str = ""
    paragraphs: list[str] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def facility_hints(self) -> set[str]:
        """Place-like words from the title, used to check the SOP and drawings share scope."""
        words = re.findall(r"[A-Z][a-z]{3,}", self.title)
        return {w.lower() for w in words}


# --- unit parsing --------------------------------------------------------------------------------

_PRESSURE_UNITS = {"psig": "psig", "psia": "psia", "psi": "psi", "barg": "barg", "bar": "bar"}
_TEMPERATURE_UNITS = {"f": "degF", "c": "degC", "degf": "degF", "degc": "degC"}

_RANGE = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*(?:to|through|\.\.\.|–|—|/)\s*(-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
_SCALAR = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_quantity(text: str, unit: str) -> Quantity | None:
    """Parse a scalar or a range into a :class:`Quantity`.

    ``/`` is deliberately accepted as a range separator *only* here, where the column already
    establishes that the value is a temperature or a pressure. In free text ``/`` is ambiguous --
    a motor rating like ``460/3/60`` is volts, phases and hertz, not a range -- so range
    interpretation is gated on there being exactly two numeric parts in a known-unit context.
    """
    cleaned = unicodedata.normalize("NFKC", text or "").strip()
    if not cleaned:
        return None

    match = _RANGE.match(cleaned)
    if match:
        lo, hi = float(match.group(1)), float(match.group(2))
        return Quantity(min(lo, hi), max(lo, hi), unit, cleaned)

    match = _SCALAR.match(cleaned)
    if match:
        value = float(match.group(1))
        return Quantity(value, value, unit, cleaned)
    return None


def unit_from_header(header: str) -> tuple[str, str] | None:
    """Map a column header to ``(field name, unit)``."""
    text = unicodedata.normalize("NFKC", header or "").lower()
    for key, unit in _PRESSURE_UNITS.items():
        if key in text:
            return "pressure", unit
    if "temp" in text:
        for key, unit in _TEMPERATURE_UNITS.items():
            if key in text.replace("°", "deg"):
                return "temperature", unit
        return "temperature", "degF"
    return None


# --- subject resolution ---------------------------------------------------------------------------

_TAG_SEPARATORS = r"(?:and|/|,|&)"
_TAG_IN_TEXT = re.compile(
    rf"\b([A-Z]{{1,3}}-\d{{2,4}})\s*((?:[A-Z]\b(?:\s*{_TAG_SEPARATORS}\s*[A-Z]\b)*)?)",
    re.IGNORECASE,
)
_PART = re.compile(r"\((shell|tube|body|jacket)\)", re.IGNORECASE)


def resolve_subject(text: str) -> tuple[tuple[str, ...], str | None]:
    """Extract equipment tags and any sub-component from a descriptive subject.

    Handles the common convention of naming two trains in one row -- "F-715 A and B" is two
    pieces of equipment, and treating it as one loses half the plant.
    """
    normalised = unicodedata.normalize("NFKC", text or "").strip()
    part_match = _PART.search(normalised)
    part = part_match.group(1).lower() if part_match else None

    tags: list[str] = []
    for match in _TAG_IN_TEXT.finditer(normalised.upper()):
        base = match.group(1)
        parts = re.split(rf"\s*{_TAG_SEPARATORS}\s*", match.group(2) or "", flags=re.IGNORECASE)
        trains = [t for t in parts if t.strip()]
        if trains:
            tags.extend(f"{base}{t.strip()}" for t in trains)
        else:
            tags.append(base)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered = [t for t in tags if not (t in seen or seen.add(t))]
    return tuple(ordered), part


# --- document reading -------------------------------------------------------------------------


def _text_of(element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{W}t"))


def load(path: str | Path) -> SopDocument:
    """Read an Office Open XML document into paragraphs, tables and requirements."""
    p = Path(path)
    doc = SopDocument(path=str(p))

    with zipfile.ZipFile(p) as archive:
        # Explicit UTF-8: these files carry degree signs and typographic ellipses.
        body_xml = archive.read("word/document.xml").decode("utf-8")
        try:
            core_xml = archive.read("docProps/core.xml").decode("utf-8")
        except KeyError:
            core_xml = ""

    if core_xml:
        core = ElementTree.fromstring(core_xml)
        doc.title = (core.findtext(f"{DC}title") or "").strip()
        doc.author = (core.findtext(f"{DC}creator") or "").strip()
        doc.revision = (core.findtext(f"{CP}revision") or "").strip()

    root = ElementTree.fromstring(body_xml)
    body = root.find(f"{W}body")
    if body is None:
        doc.notes.append("document has no body")
        return doc

    for child in body:
        if child.tag == f"{W}p":
            text = unicodedata.normalize("NFKC", _text_of(child)).strip()
            if text:
                doc.paragraphs.append(text)
        elif child.tag == f"{W}tbl":
            doc.requirements.extend(_requirements_from_table(child, len(doc.requirements)))

    if not doc.requirements:
        doc.notes.append("no checkable requirements found; the document may be prose-only")
    return doc


def _requirements_from_table(table, start_ordinal: int) -> list[Requirement]:
    """Lift a limits table into requirements.

    The header row establishes which unit each column carries, which is what allows ``/`` to be
    read as a range separator safely.
    """
    rows = table.findall(f"{W}tr")
    if len(rows) < 2:
        return []

    headers = [_text_of(cell) for cell in rows[0].findall(f"{W}tc")]
    columns: dict[int, tuple[str, str]] = {}
    for index, header in enumerate(headers):
        mapped = unit_from_header(header)
        if mapped:
            columns[index] = mapped
    if not columns:
        return []

    out: list[Requirement] = []
    ordinal = start_ordinal
    for row in rows[1:]:
        cells = [_text_of(cell) for cell in row.findall(f"{W}tc")]
        if not cells:
            continue
        subject = unicodedata.normalize("NFKC", cells[0]).strip()
        if not subject:
            continue
        quantities: dict[str, Quantity] = {}
        for index, (field_name, unit) in columns.items():
            if index < len(cells):
                quantity = parse_quantity(cells[index], unit)
                if quantity is not None:
                    quantities[field_name] = quantity
        if not quantities:
            continue
        tags, part = resolve_subject(subject)
        out.append(
            Requirement(
                ordinal=ordinal,
                subject_raw=subject,
                subject_tags=tags,
                subject_part=part,
                quantities=quantities,
                evidence=" | ".join(c.strip() for c in cells if c.strip()),
            )
        )
        ordinal += 1
    return out

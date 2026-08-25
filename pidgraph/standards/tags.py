"""Tag parsing.

Ordered rules, first match wins. Ordering is load-bearing: an equipment tag and an instrument tag
have the same shape, so the equipment rule must run first or every vessel is parsed as a loop.

Every parse records a **conformance verdict** alongside the result. Industry variants are
normalised and reported, never silently rewritten and never rejected -- a drawing that writes the
differential modifier in the widely-used but non-conformant order is still readable, and saying so
is itself a useful finding.

What is *not* standardised lives in project vocabulary: line-number field schemas, equipment class
letters and user's-choice letters are company convention, and hardcoding one contractor's grammar
is the surest way to build something that works on exactly one client's drawings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from pidgraph.standards import isa


class Conformance(StrEnum):
    LISTED = "listed"
    """Decomposes cleanly against the letter tables."""
    GRAMMAR_VALID = "grammar_valid"
    """Well-formed but uses a combination the tables do not list."""
    NORMALISED = "nonconformant_normalised"
    """A recognised industry variant, rewritten to the conformant form. Both are retained."""
    UNPARSED = "unparsed"


class TagKind(StrEnum):
    INSTRUMENT = "instrument"
    VALVE = "valve"
    EQUIPMENT = "equipment"
    LINE_NUMBER = "line_number"
    OFF_PAGE_CONNECTOR = "off_page_connector"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedTag:
    raw: str
    kind: TagKind
    conformance: Conformance
    canonical: str | None = None
    prefix: str | None = None
    sequence: str | None = None
    suffix: str | None = None
    function_letters: str | None = None
    variable: str | None = None
    variable_modifier: str | None = None
    loop_id: str | None = None
    is_safety_device: bool = False
    is_sis: bool = False
    fields: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.conformance is not Conformance.UNPARSED


@dataclass
class ProjectVocabulary:
    """Company convention. Seeded per project, never hardcoded.

    The reference guide is explicit that user's-choice letters must be documented on the drawing's
    legend sheet. When the legend sheet is not supplied these entries are inferences and are
    flagged as such rather than presented as fact.
    """

    equipment_classes: dict[str, str] = field(
        default_factory=lambda: {
            "F": "filter / separator",
            "V": "vessel / tower",
            "E": "heat exchanger",
            "P": "pump",
            "AC": "air cooler",
            "T": "tank",
            "C": "compressor",
        }
    )
    users_choice_letters: dict[str, str] = field(
        default_factory=lambda: {"M": "Manual (so MV = manual valve)"}
    )
    line_service_codes: dict[str, str] = field(default_factory=dict)
    inferred: bool = True
    """True when no legend sheet was supplied, so these are inferences."""


DEFAULT_VOCABULARY = ProjectVocabulary()

# --- patterns ----------------------------------------------------------------------------------

_LINE_NUMBER = re.compile(
    r"""^(?P<size>\d{1,3}(?:[-\s]\d{1,2}/\d{1,2})?|\d{1,2}/\d{1,2})\s*["″”]\s*-\s*
        (?P<body>[A-Z0-9][A-Z0-9\-]*)$""",
    re.VERBOSE,
)
_EQUIPMENT = re.compile(
    r"^(?P<cls>[A-Z]{1,3})-(?P<num>\d{2,4})\s*(?P<train>[A-Z](?:\s*/\s*[A-Z])*)?$"
)
_VALVE = re.compile(r"^(?P<fn>[A-Z]{2,4})-(?P<unit>\d{2,4})-(?P<seq>\d{1,3})(?P<sfx>[A-Z]{0,2})$")
_INSTRUMENT = re.compile(
    r"^(?P<fn>[A-Z]{1,6})-(?P<unit>\d{2,4})(?:-(?P<seq>\d{1,3}))?(?P<sfx>[A-Z]{0,2})$"
)
_CONNECTOR = re.compile(r"^\[?(?P<ref>\d{3,4}[A-Z]{0,2}|[A-Z]\d{2}[A-Z])\]?$")

# Recognised industry variant: the differential modifier written before the variable rather than
# after it. The reference guide itself writes the conformant order with a lower-case modifier.
_LEADING_DIFFERENTIAL = re.compile(r"^D(?P<var>[FPTLW])(?P<rest>[A-Z]*)$")


# ruff: noqa: RUF001 -- this module deliberately handles the confusable dash and quote
# characters that CAD exporters emit; naming them literally is the point.
def _normalise(raw: str) -> tuple[str, list[str]]:
    """Upper-case, collapse whitespace, and unify the several dash and quote characters used."""
    notes: list[str] = []
    text = raw.strip().upper()
    for quote in ("″", "”", "’"):  # prime, right double, right single
        text = text.replace(quote, '"')
    for dash in ("‐", "‑", "‒", "–", "—"):  # hyphen..em dash
        text = text.replace(dash, "-")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    if text != raw.strip():
        notes.append("normalised case, dashes and quotes")
    return text, notes


def _split_function(function: str) -> tuple[str, str | None, str]:
    """Split function letters into (variable, variable modifier, succeeding letters).

    ``S`` in second position is the trap. It is *Safety* only for a self-actuated
    emergency-protective element -- the closed set in :data:`isa.SAFETY_DEVICES` -- and *Switch*
    everywhere else. Gating instead on the trailing letters would classify ``LSV``, ``ASE`` and
    ``ZSV`` as safety devices, and gating on nothing would make ``LSHH`` a "level safety" loop
    rather than a level switch. See docs/assumptions.md STD-01.
    """
    if not function:
        return "", None, ""
    variable = function[0]
    rest = function[1:]
    if not rest:
        return variable, None, ""

    candidate = rest[0]
    if candidate == "S" and not isa.is_safety_device(function):
        return variable, None, rest  # Switch, an output function -- not a modifier.
    if isa.lookup(isa.VARIABLE_MODIFIERS, candidate) and len(rest) > 1:
        return variable, candidate, rest[1:]
    return variable, None, rest


def parse(raw: str, vocab: ProjectVocabulary | None = None) -> ParsedTag:
    """Parse one tag. Rule order is deliberate and documented inline."""
    vocab = vocab or DEFAULT_VOCABULARY
    text, notes = _normalise(raw)
    if not text:
        return ParsedTag(raw=raw, kind=TagKind.UNKNOWN, conformance=Conformance.UNPARSED)

    # R1 line number -- the only class beginning with a size and an inch mark.
    match = _LINE_NUMBER.match(text)
    if match:
        parts = match.group("body").split("-")
        fields = {"size": match.group("size")}
        # Field arity varies by project, so unmatched parts are preserved rather than dropped.
        names = ["service", "sequence", "spec", "extra1", "extra2"]
        for name, value in zip(names, parts, strict=False):
            fields[name] = value
        if len(parts) > len(names):
            fields["unparsed_fields"] = "-".join(parts[len(names):])
        return ParsedTag(
            raw=raw, kind=TagKind.LINE_NUMBER, conformance=Conformance.GRAMMAR_VALID,
            canonical=text, fields=fields,
            notes=(*notes, "line-number fields are company convention, not ISA-normative"),
        )

    # R2 off-page connector -- checked before equipment so a bare sheet reference is not
    # mistaken for an equipment number.
    if text.startswith("[") or (_CONNECTOR.match(text) and not _EQUIPMENT.match(text)):
        match = _CONNECTOR.match(text)
        if match:
            return ParsedTag(
                raw=raw, kind=TagKind.OFF_PAGE_CONNECTOR, conformance=Conformance.GRAMMAR_VALID,
                canonical=match.group("ref"), notes=tuple(notes),
            )

    # R3 equipment -- MUST precede the instrument rule. "P-745" is a pump, not a pressure loop,
    # and only the project vocabulary can tell them apart.
    match = _EQUIPMENT.match(text)
    if match and match.group("cls") in vocab.equipment_classes:
        train = (match.group("train") or "").replace(" ", "")
        extra = ["equipment class letters are company convention"] if vocab.inferred else []
        return ParsedTag(
            raw=raw, kind=TagKind.EQUIPMENT, conformance=Conformance.GRAMMAR_VALID,
            canonical=f"{match.group('cls')}-{match.group('num')}{train}",
            prefix=match.group("cls"), sequence=match.group("num"), suffix=train or None,
            notes=(*notes, *extra),
        )

    # R4 valve and R5 instrument share a shape; both run through the same decomposition.
    match = _VALVE.match(text) or _INSTRUMENT.match(text)
    if not match:
        return ParsedTag(raw=raw, kind=TagKind.UNKNOWN, conformance=Conformance.UNPARSED,
                         notes=tuple(notes))

    function = match.group("fn")
    canonical_fn = function
    conformance = Conformance.LISTED

    # Recognised industry variant: leading differential. Normalise, but keep the observed form.
    variant = _LEADING_DIFFERENTIAL.match(function)
    if variant:
        canonical_fn = f"{variant.group('var')}D{variant.group('rest')}"
        conformance = Conformance.NORMALISED
        notes.append(
            f"'{function}' writes the differential modifier before the variable; the conformant "
            f"order is '{canonical_fn}' (the modifier is a column-2 letter)"
        )

    variable, modifier, _succeeding = _split_function(canonical_fn)
    if isa.lookup(isa.VARIABLES, variable) is None:
        conformance = Conformance.GRAMMAR_VALID
        notes.append(f"'{variable}' is not a listed first letter")

    unit = match.group("unit")
    seq = match.groupdict().get("seq")
    suffix = match.groupdict().get("sfx") or None

    kind = TagKind.INSTRUMENT
    if function.startswith("MV") or (
        function[:1] in vocab.users_choice_letters and function.endswith("V")
    ):
        # A user's-choice letter with a valve output is a manual valve, not an instrument loop.
        kind = TagKind.VALVE
        notes.append(
            f"'{function[:1]}' is a user's-choice letter; meaning comes from the project legend"
        )

    canonical = f"{canonical_fn}-{unit}" + (f"-{seq}" if seq else "") + (suffix or "")
    loop = f"{variable}{modifier or ''}-{unit}" + (f"-{seq}" if seq else "")

    return ParsedTag(
        raw=raw,
        kind=kind,
        conformance=conformance,
        canonical=canonical,
        prefix=canonical_fn,
        sequence=unit if seq is None else f"{unit}-{seq}",
        suffix=suffix,
        function_letters=canonical_fn,
        variable=variable,
        variable_modifier=modifier,
        loop_id=None if kind is TagKind.VALVE else loop,
        is_safety_device=isa.is_safety_device(canonical_fn),
        is_sis=isa.is_sis(modifier),
        notes=tuple(notes),
    )


def parse_many(raws: list[str], vocab: ProjectVocabulary | None = None) -> list[ParsedTag]:
    return [parse(raw, vocab) for raw in raws]


def conformance_report(tags: list[ParsedTag]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tag in tags:
        counts[str(tag.conformance)] = counts.get(str(tag.conformance), 0) + 1
    return dict(sorted(counts.items()))

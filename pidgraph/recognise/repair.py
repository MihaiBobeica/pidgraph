"""Grammar-constrained repair of recognised text.

An optical recogniser reading a CAD stroke font makes a predictable, small set of mistakes: it
inserts spaces inside a tag, and it confuses characters that look alike at hairline weight -- 1
against I, 0 against O and D, 8 against B, 4 against A, 5 against S.

Repair is only allowed to *narrow* uncertainty. A candidate is accepted only when it parses as a
valid tag under the identification grammar, and only when exactly one candidate does. If several
repairs are equally valid the read stays unrepaired, because choosing between them would be
guessing -- and a confidently wrong tag is worse than an unread one: it joins to the wrong
component and every downstream claim about it is false while looking sound.

Every repair records what changed, so a reader can see that a tag was corrected rather than read.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from pidgraph.standards.tags import Conformance, ParsedTag, TagKind, parse

# Confusions worth trying, in both directions. Deliberately short: each additional pair multiplies
# the candidate space and raises the chance of manufacturing a plausible wrong answer.
CONFUSIONS: dict[str, tuple[str, ...]] = {
    "I": ("1",),
    "1": ("I",),
    "O": ("0",),
    "0": ("O", "D"),
    "D": ("0",),
    "8": ("B",),
    "B": ("8",),
    "4": ("A",),
    "A": ("4",),
    "5": ("S",),
    "S": ("5",),
    "2": ("Z",),
    "Z": ("2",),
}

MAX_SUBSTITUTIONS = 0
"""Character substitution is **off by default**, on evidence.

The idea is sound only when the grammar is tight enough to reject nonsense. Ours cannot be: line
numbers are company convention with a variable field count, so the parser must accept a wide range
of shapes. Measured on the real cache, substitution repaired 7 reads and produced results like
``4-14`` to ``A-14``, ``S08`` to ``508`` and ``2-D5S`` to ``Z-05S`` -- each grammatically valid and
each meaningless. Despacing, by contrast, is unambiguous and keeps its default.

The failure mode this avoids is the expensive one. An unread tag is visibly absent; a confidently
wrong tag joins to the wrong component, and every downstream claim about it is false while looking
sound. Raise the budget only against a project vocabulary narrow enough to make a wrong repair
fail to parse.
"""


@dataclass(frozen=True)
class Repair:
    original: str
    repaired: str
    parsed: ParsedTag
    substitutions: int
    note: str

    @property
    def changed(self) -> bool:
        return self.original != self.repaired


def _despace(text: str) -> str:
    """Remove spaces that fall inside an identifier.

    A tag never contains a space, but the recogniser inserts them at stroke gaps. Spacing between
    separate words is preserved, so descriptive text is not mangled.
    """
    if " " not in text:
        return text
    # Only collapse when the result looks like a single identifier: letters, digits and separators.
    candidate = text.replace(" ", "")
    if re.fullmatch(r'[A-Z0-9\-/".]+', candidate):
        return candidate
    return text


def _variants(text: str, budget: int) -> list[str]:
    """Candidate strings within ``budget`` character substitutions."""
    positions = [i for i, ch in enumerate(text) if ch in CONFUSIONS]
    if not positions:
        return []
    out: list[str] = []
    for count in range(1, budget + 1):
        for chosen in itertools.combinations(positions, count):
            options = [CONFUSIONS[text[i]] for i in chosen]
            for replacement in itertools.product(*options):
                chars = list(text)
                for index, char in zip(chosen, replacement, strict=True):
                    chars[index] = char
                out.append("".join(chars))
    return out


def repair(text: str, budget: int = MAX_SUBSTITUTIONS) -> Repair | None:
    """Return a repaired, grammatically valid tag, or ``None`` if none is unambiguous.

    With the default budget only despacing is applied; see :data:`MAX_SUBSTITUTIONS`.
    """
    raw = (text or "").strip().upper()
    if not raw:
        return None

    despaced = _despace(raw)
    direct = parse(despaced)
    if direct.conformance is not Conformance.UNPARSED and direct.kind is not TagKind.UNKNOWN:
        note = "spaces removed" if despaced != raw else "read directly"
        return Repair(raw, despaced, direct, 0, note)

    if budget <= 0:
        return None

    # Only now try substitutions, and only accept an unambiguous outcome.
    accepted: list[tuple[str, ParsedTag]] = []
    for candidate in _variants(despaced, budget):
        parsed = parse(candidate)
        if parsed.conformance is Conformance.UNPARSED or parsed.kind is TagKind.UNKNOWN:
            continue
        # Equivalent canonical forms are one answer, not several.
        if all(parsed.canonical != existing.canonical for _, existing in accepted):
            accepted.append((candidate, parsed))
        if len(accepted) > 1:
            # Ambiguous. Leaving it unread is the safe outcome.
            return None

    if not accepted:
        return None
    candidate, parsed = accepted[0]
    changes = sum(1 for a, b in zip(despaced, candidate, strict=False) if a != b)
    return Repair(
        raw, candidate, parsed, changes,
        f"{changes} character substitution{'s' if changes != 1 else ''} to reach a valid tag",
    )


def repair_all(texts: list[str]) -> tuple[list[Repair], dict[str, int]]:
    """Repair a batch and report what happened, so the rate is visible rather than assumed."""
    repairs: list[Repair] = []
    stats = {"input": len(texts), "direct": 0, "repaired": 0, "unrepairable": 0}
    for text in texts:
        result = repair(text)
        if result is None:
            stats["unrepairable"] += 1
            continue
        repairs.append(result)
        stats["repaired" if result.substitutions else "direct"] += 1
    return repairs, stats

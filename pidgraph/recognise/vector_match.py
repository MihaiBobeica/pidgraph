"""Vector text recognition: read CAD lettering from its strokes.

The extraction pipeline already holds the exact pen strokes of every glyph on the page. Matching
those strokes against a stroke alphabet is both stricter and cheaper than rasterising them and
running a raster OCR engine: there is no anti-aliasing, no threshold, no resolution choice --
the failure modes that dominate raster OCR on hairline CAD text simply do not exist.

The pipeline of this module:

1. Transform a region's marks into the row frame (vertical rows are unrotated first), and remove
   the lettering slant -- oblique styles are standard in CAD shape fonts, and the slant betrays
   itself in the stems.
2. Segment marks into characters by dynamic programming over the mark order: candidate splits
   are scored by how well each side matches the alphabet, so an inter-character gap and the
   internal gap of a two-stroke character (a quote) are told apart by evidence, not a threshold.
3. Match each character's resampled point cloud against every template with a symmetric chamfer
   distance, normalised by the row's lettering height.
4. Resolve the confusable families by grammar. Engineering lettering has legitimate near-twins
   -- 0/O/D, 1/I, 8/B, 5/S -- that no shape matcher can honestly separate, because they are not
   separable by shape. What separates them in practice is context: a tag reads ``PI-107``, never
   ``PI-1O7``. Shape narrows each character to a family; the identification grammar picks the
   member that makes the whole string legal. When the grammar cannot decide, the geometric best
   stands, at reduced confidence.

**Confidence is margin, not fit.** Outside its confusable family, a character's best match must
beat the runner-up clearly, or the read is refused and the region falls through to raster OCR --
an unread label is recoverable, a wrong one poisons every downstream join.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise, product

from pidgraph.recognise.glyphs import CELL_H, GLYPHS

REJECT_DISTANCE = 0.12
"""Chamfer distance (in letter heights) above which a character match is refused outright."""

MIN_FAMILY_MARGIN = 0.25
"""The best match outside the winner's confusable family must be at least this much worse."""

PER_CHAR_COST = 0.008
"""Constant added per character in the segmentation search: a minimum-description-length nudge,
so splitting one glyph into two cheap fragments does not out-score reading it whole."""

MAX_CHAR_MARKS = 4
"""No character in the alphabet has more strokes than this; bounds the segmentation search."""

SAMPLE_STEP = 0.06
"""Resampling step along strokes, in letter heights."""

CONFUSABLE_FAMILIES: tuple[frozenset[str], ...] = (
    # The round family is wide on purpose: every member is a closed or nearly closed loop, and
    # at single-stroke weight they sit within each other's matching noise. A near-tie *inside*
    # a family is expected and resolved by grammar; the margin gate below only fires on
    # confusion *across* families, which is the kind that indicates a genuinely bad read.
    frozenset({"0", "O", "D", "Q", "C", "G", "6"}),
    frozenset({"1", "I"}),
    frozenset({"8", "B"}),
    frozenset({"5", "S"}),
    frozenset({"2", "Z"}),
    frozenset({"4", "A"}),
)


def _family(char: str) -> frozenset[str]:
    for fam in CONFUSABLE_FAMILIES:
        if char in fam:
            return fam
    return frozenset({char})


@dataclass(frozen=True)
class CharMatch:
    char: str
    distance: float
    margin: float
    candidates: tuple[str, ...]
    """Family members close enough to be the true reading; grammar chooses between them."""

    @property
    def confidence(self) -> float:
        fit = max(0.0, 1.0 - self.distance / REJECT_DISTANCE)
        sep = min(1.0, self.margin / 1.5)
        return round(min(0.99, 0.5 + 0.5 * min(fit, sep) + 0.2 * sep), 3)


@dataclass(frozen=True)
class RegionRead:
    text: str
    confidence: float
    chars: tuple[CharMatch, ...]
    grammar_resolved: bool


def _resample(strokes: list[list[tuple[float, float]]], step: float) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for stroke in strokes:
        for (ax, ay), (bx, by) in pairwise(stroke):
            length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            count = max(1, int(length / step))
            for i in range(count + 1):
                t = i / count
                points.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        if len(stroke) == 1:
            points.append(stroke[0])
    return points


@lru_cache(maxsize=1)
def _templates():
    """Template point clouds, normalised to letter height 1, once per process."""
    import numpy as np

    out = []
    for char, strokes in GLYPHS.items():
        scaled = [[(x / CELL_H, y / CELL_H) for x, y in stroke] for stroke in strokes]
        pts = np.asarray(_resample(scaled, SAMPLE_STEP), dtype=np.float64)
        xs = pts[:, 0]
        out.append((char, pts - [xs.min(), 0.0], float(xs.max() - xs.min()), len(strokes)))
    return out


def _chamfer(a, b) -> float:
    import numpy as np

    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return float(d.min(axis=1).mean() + d.min(axis=0).mean()) / 2.0


def _match_char(points, width: float, mark_count: int = 0) -> CharMatch | None:
    """Best template for one character cloud. ``points`` are row-frame, height-normalised."""
    import numpy as np

    cloud = np.asarray(points, dtype=np.float64)
    cloud = cloud - [cloud[:, 0].min(), 0.0]

    scores: list[tuple[float, str]] = []
    for char, template, t_width, stroke_count in _templates():
        # Width is a cheap prefilter, not a verdict: mismatched aspect cannot be the same glyph.
        if abs(t_width - width) > 0.30:
            continue
        # Stroke count is shape evidence unique to the vector domain: a B is three pen strokes
        # where an 8 is two, a 0 is one where a D is two. Raster matching cannot see this;
        # here it cleanly separates the families that point distance alone cannot.
        penalty = 0.025 * abs(stroke_count - mark_count) if mark_count else 0.0
        scores.append((_chamfer(cloud, template) + penalty, char))
    if not scores:
        return None
    scores.sort()
    best_d, best_c = scores[0]
    if best_d > REJECT_DISTANCE:
        return None

    family = _family(best_c)
    outside = next((d for d, c in scores if c not in family), best_d * 10)
    margin = (outside - best_d) / max(best_d, 1e-9)
    if margin < MIN_FAMILY_MARGIN:
        return None

    # Family members within the tie band stay in play for the grammar. The band is narrow:
    # grammar and priors may only overrule geometry where geometry genuinely cannot tell, or a
    # cleanly drawn S would be "corrected" into a 5 by a prior that was never meant for it.
    candidates = tuple(c for d, c in scores if c in family and d <= best_d + 0.010)
    return CharMatch(best_c, best_d, margin, candidates or (best_c,))


def _row_frame(marks, orientation: str):
    """Each mark as (x0, x1, strokes) in the row frame, plus the lettering height.

    Vertical rows are written bottom-up and rotated a quarter-turn anticlockwise on the sheet
    (the drafting convention), so unrotating maps sheet-y to row-x descending and sheet-x to
    row-y.
    """
    x0s, y0s, x1s, y1s = (
        [m.bbox.x0 for m in marks],
        [m.bbox.y0 for m in marks],
        [m.bbox.x1 for m in marks],
        [m.bbox.y1 for m in marks],
    )
    if orientation == "vertical":
        top = max(y1s)
        left = min(x0s)
        height = max(x1s) - left
        entries = []
        for m in marks:
            strokes = [[(top - p.y, p.x - left) for p in (s.a, s.b)] for s in m.segments]
            entries.append((top - m.bbox.y1, top - m.bbox.y0, strokes))
    else:
        top = min(y0s)
        height = max(y1s) - top
        entries = []
        for m in marks:
            strokes = [[(p.x, p.y - top) for p in (s.a, s.b)] for s in m.segments]
            entries.append((m.bbox.x0, m.bbox.x1, strokes))
    return sorted(entries, key=lambda e: (e[0] + e[1]) / 2), height


def _deshear(entries, height: float):
    """Estimate and remove the lettering slant.

    Engineering lettering is legitimately oblique -- slanted styles are standard in CAD shape
    fonts -- and a slant of a few degrees moves every point by a large fraction of the matching
    budget. The slant betrays itself in the stems: a stroke that is vertical in the letterform
    acquires exactly ``dx/dy = -slant`` when sheared, so the median over near-vertical strokes
    recovers it robustly. Rows with no stems (a lone hyphen) estimate zero and lose nothing.

    After removal, per-mark x-extents are recomputed from the corrected points, because the
    original bounding boxes belong to the sheared geometry.
    """
    ratios = []
    for _, _, strokes in entries:
        for stroke in strokes:
            (ax, ay), (bx, by) = stroke[0], stroke[-1]
            dy = by - ay
            if abs(dy) > 0.55 * height and abs(bx - ax) < 0.5 * abs(dy):
                ratios.append((bx - ax) / dy)
    if not ratios:
        return entries, 0.0
    ratios.sort()
    mid = len(ratios) // 2
    # A true median, interpolated for even counts: the legs of an A or a V contribute an exactly
    # balanced +/-r pair, and picking the upper-middle element instead of averaging the middles
    # turns that symmetric pair into a spurious slant of r.
    slant = -ratios[mid] if len(ratios) % 2 else -(ratios[mid - 1] + ratios[mid]) / 2.0
    if abs(slant) < 0.02:
        return entries, 0.0

    out = []
    for _, _, strokes in entries:
        fixed = [[(x - slant * (height - y), y) for x, y in stroke] for stroke in strokes]
        xs = [x for stroke in fixed for x, _ in stroke]
        out.append((min(xs), max(xs), fixed))
    return sorted(out, key=lambda e: (e[0] + e[1]) / 2), slant


def _resolve_by_grammar(chars: list[CharMatch]) -> tuple[str, bool]:
    """Choose within confusable families so the whole string is grammatical.

    Bounded enumeration: only ambiguous characters branch, capped so a pathological string
    cannot explode. If exactly the geometric best parses, or nothing does, geometry stands; a
    unique parsing alternative wins; several parsing alternatives keep the geometric best among
    them, because grammar has said all of them are words and shape is the remaining evidence.
    """
    from pidgraph.standards.tags import parse

    geometric = "".join(c.char for c in chars)
    options = [c.candidates for c in chars]
    combos = 1
    for o in options:
        combos *= len(o)
    if combos <= 1:
        return geometric, False
    if combos > 128:
        return geometric, False

    legal = ["".join(combo) for combo in product(*options) if parse("".join(combo)).ok]
    if not legal:
        return geometric, False

    def digit_context_penalty(candidate: str) -> int:
        # The same convention that bans I and O as train letters exists because a letter
        # between digits reads as a digit. Applied only at the positions shape left open: an
        # ambiguous O whose neighbour is a digit is a 0; unambiguous characters are never
        # second-guessed.
        penalty = 0
        for index, c in enumerate(chars):
            if len(c.candidates) < 2:
                continue
            chosen = candidate[index]
            neighbours = candidate[max(0, index - 1) : index] + candidate[index + 1 : index + 2]
            if chosen.isalpha() and any(ch.isdigit() for ch in neighbours):
                penalty += 1
        return penalty

    ranked = sorted(legal, key=digit_context_penalty)
    top = digit_context_penalty(ranked[0])
    contenders = [c for c in ranked if digit_context_penalty(c) == top]
    if geometric in contenders:
        return geometric, False
    return contenders[0], True


def read_region(marks, orientation: str) -> RegionRead | None:
    """Read one text region from its vector marks, or refuse.

    Dynamic programming over mark order: state ``i`` is "the first ``i`` marks are spent", and a
    transition consumes the next 1..MAX_CHAR_MARKS marks as one character. The segmentation that
    reads best overall wins, which is what disambiguates a quote's two strokes from two adjacent
    characters -- both segmentations are tried, and only one of them matches the alphabet.
    """
    usable = [m for m in marks if m.segments]
    if not usable or any(m.curves for m in marks):
        return None  # curved lettering is not in the alphabet; let raster OCR try
    base_entries, height = _row_frame(usable, orientation)
    if height <= 0:
        return None
    scale = 1.0 / height

    def attempt(entries) -> list[CharMatch] | None:
        n = len(entries)
        no_path = float("inf")
        best: list[float] = [no_path] * (n + 1)
        best[0] = 0.0
        choice: list[tuple[int, CharMatch] | None] = [None] * (n + 1)

        for end in range(1, n + 1):
            for start in range(max(0, end - MAX_CHAR_MARKS), end):
                if best[start] == no_path:
                    continue
                # A split is only legal at a real inter-character boundary: consecutive
                # characters never overlap along the row, so a boundary between x-overlapping
                # marks (a glyph's own strokes -- an 8's midbar inside its outline) is not a
                # place a character can end. Without this, a two-stroke glyph splits into two
                # cheap fragments that read as spurious punctuation.
                if start > 0 and entries[start][0] < entries[start - 1][1] - 0.12 * height:
                    continue
                group = entries[start:end]
                span = (max(e[1] for e in group) - min(e[0] for e in group)) * scale
                if span > 1.05:
                    continue
                points = _resample(
                    [[(x * scale, y * scale) for x, y in stroke] for e in group for stroke in e[2]],
                    SAMPLE_STEP,
                )
                if not points:
                    continue
                match = _match_char(points, span, end - start)
                if match is None:
                    continue
                cost = best[start] + match.distance + PER_CHAR_COST
                if cost < best[end]:
                    best[end] = cost
                    choice[end] = (start, match)

        if best[n] == no_path or choice[n] is None:
            return None
        out: list[CharMatch] = []
        cursor = n
        while cursor > 0:
            step = choice[cursor]
            if step is None:
                return None
            out.append(step[1])
            cursor = step[0]
        out.reverse()
        return out

    # The slant estimate is a hypothesis, not a fact: the legs of an A, V, W or 7 pass any
    # workable stem gate, and a row dominated by them estimates a large slant for perfectly
    # upright lettering. So both interpretations are read and the better one stands -- the same
    # reading-is-the-test rule the rest of the pipeline uses. Upright wins ties.
    sheared_entries, slant = _deshear(base_entries, height)
    upright = attempt(base_entries)
    sheared = attempt(sheared_entries) if abs(slant) >= 0.02 else None

    def mean_distance(read: list[CharMatch]) -> float:
        return sum(c.distance for c in read) / len(read)

    if upright is None and sheared is None:
        return None
    if sheared is None or (
        upright is not None and mean_distance(upright) <= mean_distance(sheared)
    ):
        chars = upright
    else:
        chars = sheared

    text, resolved = _resolve_by_grammar(chars)
    confidence = min(c.confidence for c in chars)
    if resolved:
        confidence = round(confidence * 0.92, 3)
    return RegionRead(
        text=text, confidence=confidence, chars=tuple(chars), grammar_resolved=resolved
    )

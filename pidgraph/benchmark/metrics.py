"""Scoring.

Three rules make these numbers mean something.

**Scoring happens in drawing coordinates**, never pixels, so a result does not move when render
resolution changes.

**Matching is one-to-one.** Predictions are matched to truth by a greedy pass over descending
overlap with a gate, so one large prediction cannot claim several truth objects and inflate recall.

**Every figure carries its denominator and an interval.** At these sample sizes a bare percentage
is close to meaningless -- a perfect four-out-of-four has a 95% lower bound below a coin flip -- so
the score type cannot represent a point estimate without one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_REPORTABLE = 5
"""Below this many truth instances, a rate is not reported at all -- only the raw counts."""


@dataclass(frozen=True)
class Score:
    """A rate with its denominator and a confidence interval. There is no way to omit them."""

    hits: int
    total: int
    low: float
    high: float
    label: str = ""

    @property
    def value(self) -> float | None:
        """The point estimate, or ``None`` when the sample is too small to report one."""
        if self.total < MIN_REPORTABLE:
            return None
        return self.hits / self.total

    def __str__(self) -> str:
        if self.total == 0:
            return f"{self.label}: no instances"
        if self.value is None:
            return f"{self.label}: {self.hits}/{self.total} (n<{MIN_REPORTABLE}, rate not reported)"
        return (
            f"{self.label}: {self.value:.1%} [{self.low:.1%}-{self.high:.1%}] "
            f"n={self.total}"
        )

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "hits": self.hits,
            "total": self.total,
            "value": self.value,
            "ci_low": self.low,
            "ci_high": self.high,
            "reportable": self.total >= MIN_REPORTABLE,
        }


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval.

    Chosen over the normal approximation because it stays inside [0,1] and remains sensible at
    the extremes -- which is exactly where these samples sit.
    """
    if total == 0:
        return (0.0, 0.0)
    p = hits / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def score(hits: int, total: int, label: str = "") -> Score:
    low, high = wilson(hits, total)
    return Score(hits=hits, total=total, low=low, high=high, label=label)


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(ax1 - ax0, 0) * max(ay1 - ay0, 0)
    area_b = max(bx1 - bx0, 0) * max(by1 - by0, 0)
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def match(
    truth: list[tuple[str, tuple[float, float, float, float]]],
    predicted: list[tuple[str, tuple[float, float, float, float]]],
    threshold: float = 0.3,
) -> dict[str, str]:
    """Greedy one-to-one matching on overlap.

    One-to-one matters: without it a single oversized prediction covering three truth objects
    would count as three hits, and recall would look excellent while the graph was wrong.
    """
    pairs: list[tuple[float, str, str]] = []
    for truth_id, truth_box in truth:
        for pred_id, pred_box in predicted:
            overlap = iou(truth_box, pred_box)
            if overlap >= threshold:
                pairs.append((overlap, truth_id, pred_id))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    used_truth: set[str] = set()
    used_pred: set[str] = set()
    mapping: dict[str, str] = {}
    for _, truth_id, pred_id in pairs:
        if truth_id in used_truth or pred_id in used_pred:
            continue
        mapping[truth_id] = pred_id
        used_truth.add(truth_id)
        used_pred.add(pred_id)
    return mapping


def sweep(
    truth: list[tuple[str, tuple[float, float, float, float]]],
    predicted: list[tuple[str, tuple[float, float, float, float]]],
    thresholds: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7),
) -> dict[float, tuple[Score, Score]]:
    """Precision and recall across overlap thresholds.

    Reported as a sweep rather than at one threshold, because a single threshold is an arbitrary
    claim and small symbols are penalised disproportionately by a strict one.
    """
    out: dict[float, tuple[Score, Score]] = {}
    for threshold in thresholds:
        mapping = match(truth, predicted, threshold)
        hits = len(mapping)
        out[threshold] = (
            score(hits, len(predicted), f"precision@{threshold}"),
            score(hits, len(truth), f"recall@{threshold}"),
        )
    return out


def edge_scores(
    truth_edges: list[tuple[str, str]],
    predicted_edges: list[tuple[str, str]],
    node_mapping: dict[str, str],
) -> tuple[Score, Score]:
    """Edge precision and recall, conditioned on the node matching.

    Edges are compared only where both endpoints were matched, so a connectivity figure is not
    silently reporting a detection failure instead.
    """
    translated = set()
    for source, target in truth_edges:
        if source in node_mapping and target in node_mapping:
            translated.add(frozenset((node_mapping[source], node_mapping[target])))
    predicted = {frozenset(e) for e in predicted_edges if e[0] != e[1]}
    hits = len(translated & predicted)
    return (
        score(hits, len(predicted), "edge precision"),
        score(hits, len(translated), "edge recall"),
    )

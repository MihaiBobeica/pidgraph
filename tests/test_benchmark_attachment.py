"""Attachment scoring: the metric must punish exactly the failures it exists to expose.

Handcrafted truth/predicted pairs rather than generated ones, so each case states one property:
conditioning on the node matching, canonical-string comparison, the unmatched-tagged raw count,
and per-(pair, line) claim deduplication.
"""

from __future__ import annotations

from dataclasses import dataclass

from pidgraph.benchmark import metrics


@dataclass(frozen=True)
class Sym:
    id: str
    tag: str


@dataclass(frozen=True)
class Label:
    text: str
    edge: tuple[str, str] | None = None


def test_attachment_perfect() -> None:
    truth = [Sym("a", "PI-101"), Sym("b", "MV-100-01")]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall, unmatched = metrics.attachment_scores(
        truth, mapping, {"ka": "PI-101", "kb": "MV-100-01"}
    )
    assert (precision.hits, precision.total) == (2, 2)
    assert (recall.hits, recall.total) == (2, 2)
    assert unmatched == 0


def test_attachment_wrong_tag_is_a_precision_and_recall_miss() -> None:
    truth = [Sym("a", "PI-101"), Sym("b", "PI-102")]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall, _ = metrics.attachment_scores(
        truth, mapping, {"ka": "PI-101", "kb": "PI-999"}
    )
    assert (precision.hits, precision.total) == (1, 2)
    assert (recall.hits, recall.total) == (1, 2)


def test_attachment_missing_tag_hits_recall_not_precision() -> None:
    truth = [Sym("a", "PI-101"), Sym("b", "PI-102")]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall, _ = metrics.attachment_scores(truth, mapping, {"ka": "PI-101"})
    assert (precision.hits, precision.total) == (1, 1)
    assert (recall.hits, recall.total) == (1, 2)


def test_attachment_is_conditioned_on_node_matching() -> None:
    """An undetected symbol is a detection miss, not an attachment miss."""
    truth = [Sym("a", "PI-101"), Sym("b", "PI-102")]
    precision, recall, _ = metrics.attachment_scores(truth, {"a": "ka"}, {"ka": "PI-101"})
    assert (recall.hits, recall.total) == (1, 1)
    assert (precision.hits, precision.total) == (1, 1)


def test_attachment_unmatched_tagged_is_a_raw_count() -> None:
    """A tag on a node that matches no truth symbol is reported, not folded into a rate."""
    truth = [Sym("a", "PI-101")]
    precision, recall, unmatched = metrics.attachment_scores(
        truth, {"a": "ka"}, {"ka": "PI-101", "phantom": "MV-100-01"}
    )
    assert unmatched == 1
    assert precision.total == 1
    assert recall.total == 1


def test_attachment_compares_canonical_forms() -> None:
    """Truth tags pass through the parser, so an equivalent written form still scores."""
    truth = [Sym("a", "pi - 101")]
    precision, recall, _ = metrics.attachment_scores(truth, {"a": "ka"}, {"ka": "PI-101"})
    assert (recall.hits, recall.total) == (1, 1)
    assert (precision.hits, precision.total) == (1, 1)


def test_line_attachment_hit_and_conditioning() -> None:
    labels = [
        Label('1"-D2S', edge=("a", "b")),
        Label('2"-P101', edge=("b", "c")),  # c undetected: out of both denominators
        Label("PI-101", edge=None),  # symbol label: ignored
    ]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall = metrics.line_attachment_scores(
        labels, mapping, [("ka", "kb", '1"-D2S')]
    )
    assert (precision.hits, precision.total) == (1, 1)
    assert (recall.hits, recall.total) == (1, 1)


def test_line_attachment_wrong_pair_is_a_precision_miss() -> None:
    labels = [Label('1"-D2S', edge=("a", "b"))]
    mapping = {"a": "ka", "b": "kb", "c": "kc"}
    precision, recall = metrics.line_attachment_scores(
        labels, mapping, [("ka", "kb", '1"-D2S'), ("kb", "kc", '1"-D2S')]
    )
    assert (precision.hits, precision.total) == (1, 2)
    assert (recall.hits, recall.total) == (1, 1)


def test_line_attachment_deduplicates_parallel_claims() -> None:
    """The same (pair, line) reached through parallel edges is one claim, not several."""
    labels = [Label('1"-D2S', edge=("a", "b"))]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall = metrics.line_attachment_scores(
        labels,
        mapping,
        [("ka", "kb", '1"-D2S'), ("kb", "ka", '1"-D2S')],
    )
    assert (precision.hits, precision.total) == (1, 1)
    assert (recall.hits, recall.total) == (1, 1)


def test_line_attachment_ignores_edges_outside_the_matched_set() -> None:
    labels = [Label('1"-D2S', edge=("a", "b"))]
    mapping = {"a": "ka", "b": "kb"}
    precision, recall = metrics.line_attachment_scores(
        labels, mapping, [("kx", "ky", '3"-CS150')]
    )
    assert (precision.hits, precision.total) == (0, 0)
    assert (recall.hits, recall.total) == (0, 1)

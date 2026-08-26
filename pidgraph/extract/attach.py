"""Convention-text binding: put tags and line numbers on the graph elements they describe.

The pass runs after topology assembly and holds one hard safety property: **it never creates,
deletes, or rewires nodes or edges -- it only sets ``label``, extra attributes and ``confidence``
on objects that already exist.** A previous attachment change that also touched promotion cost
157 real-drawing nodes before it was caught; keeping this pass attribute-only makes that class of
regression structurally impossible rather than merely tested for.

Four phases, in order:

1. **Bubble composition.** An instrument's tag is drawn as stacked rows inside its circle --
   function letters over the loop number. Rows are separate text regions and neither parses
   alone; joined top-to-bottom they parse as one tag, which is the identity the bubble carries.
2. **Adjacent assignment.** Remaining parsed tags bind to compatible nodes by *bbox gap* (edge to
   edge, so a long string abutting a node is near regardless of where its centre is), globally
   and one-to-one -- greedy over ascending gap, the same discipline the benchmark matcher uses.
3. **Legacy radius.** Unread or unparsed regions associate with still-unlabelled nodes by the
   original centre-distance rule: an unread label is an extraction gap worth showing, not
   evidence of absence.
4. **Line numbers onto edges.** A line number designates the piping segment -- the run between
   components -- so it annotates every edge lying on the labelled conductor, never a node.

Thresholds are in modules via ``scale.u`` so they follow the drawing's own proportions. Values
were tuned on development seeds 0-9 and validated on held-out seeds; they are conventions
observed on drawings, not standards, and are reported as such.

Tags that parse but bind nowhere are returned in the stats ledger with a reason, and surface as
a graph warning -- degrading visibly rather than dropping silently.
"""

from __future__ import annotations

import math
from typing import Any

from pidgraph.extract.assemble import NodeKind, node_bbox, node_centre
from pidgraph.extract.calibrate import Scale
from pidgraph.extract.lines import Polyline
from pidgraph.extract.primitives import BBox
from pidgraph.extract.text import TextRegion
from pidgraph.standards.tags import ParsedTag, TagKind, parse

ATTACH_GAP_MODULES = 2.0
"""Maximum bbox-to-bbox gap for a parsed tag to bind to a node. Tuned, not normative."""

LINE_GAP_MODULES = 2.0
"""Maximum perpendicular distance from a line-number's centre to its conductor."""

KIND_BONUS_MODULES = 0.3
"""Sorting bonus for the drafting-preferred node kind, same magnitude as the read bias."""

READ_BIAS_MODULES = 0.3
"""Legacy pass: prefer read regions over unread at equal footing (unchanged behaviour)."""

LEGACY_RADIUS_MODULES = 1.0
"""Legacy pass: added to the node's half-extent, exactly the original rule."""

SELF_BINDING_IOU = 0.5
"""A region and a node occupying the same box are the same ink: by drafting convention a tag
sits beside (or inside, and much smaller than) its symbol, so near-coincident extents mean the
text's own strokes were promoted to a node, and binding them together fabricates identity."""

ORIENTATION_TOLERANCE_DEG = 20.0
"""A line label reads along the run it names; beyond this angle it belongs to a crossing line."""

_NODE_TAG_KINDS = frozenset(
    {TagKind.INSTRUMENT, TagKind.VALVE, TagKind.EQUIPMENT, TagKind.OFF_PAGE_CONNECTOR}
)


def _rect_gap(a: BBox, b: BBox) -> float:
    """Euclidean gap between two boxes: zero when they touch or overlap."""
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0.0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0.0)
    return math.hypot(dx, dy)


def _iou(a: BBox, b: BBox) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union > 0 else 0.0


def _tag_attributes(
    parsed: ParsedTag, orientation: str, method: str, distance_modules: float, raw: str
) -> dict[str, str]:
    """Everything the parse recovered, as strings -- flattened onto the NetworkX node.

    The decomposed fields exist so a consumer (the cross-reference engine, the query agent) can
    ask about prefixes, loops and safety devices without re-parsing; discarding them here was
    exactly the defect this module replaces.
    """
    attributes = {
        "text_orientation": orientation,
        "tag_canonical": parsed.canonical or "",
        "tag_kind": str(parsed.kind),
        "conformance": str(parsed.conformance),
        "tag_raw": raw,
        "attach_method": method,
        "attach_distance_modules": f"{distance_modules:.2f}",
    }
    if parsed.prefix:
        attributes["tag_prefix"] = parsed.prefix
    if parsed.sequence:
        attributes["tag_sequence"] = parsed.sequence
    if parsed.suffix:
        attributes["tag_suffix"] = parsed.suffix
    if parsed.function_letters:
        attributes["function_letters"] = parsed.function_letters
    if parsed.variable:
        attributes["variable"] = parsed.variable
    if parsed.variable_modifier:
        attributes["variable_modifier"] = parsed.variable_modifier
    if parsed.loop_id:
        attributes["loop_id"] = parsed.loop_id
    if parsed.is_safety_device:
        attributes["safety_device"] = "true"
    if parsed.is_sis:
        attributes["is_sis"] = "true"
    return attributes


def _retag(
    graph: Any, key: str, *, label: str, attributes: dict[str, str], confidence: float
) -> None:
    node = graph.nodes[key]
    node["label"] = label
    node["confidence"] = confidence
    node.update(attributes)


def _line_ids(data: dict) -> list[int]:
    raw = data.get("line_ids") or []
    if isinstance(raw, str):
        return [int(part) for part in raw.split(",") if part]
    return [int(v) for v in raw]


def attach_all(
    graph: Any,
    regions: list[TextRegion],
    lines: list[Polyline],
    scale: Scale,
    *,
    attach_gap_modules: float | None = None,
    line_gap_modules: float | None = None,
) -> dict:
    """Bind convention text to the graph. Mutates labels/attributes only; returns the ledger."""
    from pidgraph.extract.assemble import _distance_to_segment

    unit = max(scale.u(1.0), 1e-9)
    attach_gate = scale.u(attach_gap_modules or ATTACH_GAP_MODULES)
    line_gate = scale.u(line_gap_modules or LINE_GAP_MODULES)
    kind_bonus = scale.u(KIND_BONUS_MODULES)

    parsed: dict[int, ParsedTag] = {}
    for index, region in enumerate(regions):
        if region.text:
            candidate = parse(region.text)
            if candidate.ok and candidate.canonical:
                parsed[index] = candidate
    node_tag_pool = {i for i, p in parsed.items() if p.kind in _NODE_TAG_KINDS}
    line_pool = {i for i, p in parsed.items() if p.kind is TagKind.LINE_NUMBER}

    claimed: set[int] = set()
    tagged_nodes: set[str] = set()
    unbound: list[dict[str, str]] = []
    composed = 0

    # --- phase 1: bubble row composition --------------------------------------------------
    for key, data in list(graph.nodes(data=True)):
        if data.get("kind") != NodeKind.INSTRUMENT:
            continue
        box = node_bbox(data)
        members = [
            i
            for i, region in enumerate(regions)
            if i not in claimed
            and i not in line_pool
            and region.text
            and box.contains(region.centre)
        ]
        if not members:
            continue
        members.sort(key=lambda i: regions[i].bbox.y0)
        texts = [regions[i].text or "" for i in members]
        composite: ParsedTag | None = None
        joined_raw = ""
        for joined in ("-".join(texts), "".join(texts)):
            candidate = parse(joined)
            if (
                candidate.ok
                and candidate.canonical
                and candidate.kind in (TagKind.INSTRUMENT, TagKind.VALVE)
            ):
                composite = candidate
                joined_raw = joined
                break
        if composite is None:
            # Rows exist but do not compose into a tag: a misread stays a visible gap. The
            # rows remain unclaimed, so the legacy pass may still associate one as a label.
            continue
        read_confidence = min(regions[i].text_confidence for i in members)
        _retag(
            graph,
            key,
            label=composite.canonical or joined_raw,
            attributes=_tag_attributes(
                composite, regions[members[0]].orientation, "bubble_rows", 0.0, joined_raw
            ),
            # A node is only as trustworthy as its weakest input; for a composed tag that is
            # the worst row read.
            confidence=min(float(data["confidence"]), max(read_confidence, 0.1)),
        )
        claimed.update(members)
        node_tag_pool -= set(members)
        tagged_nodes.add(key)
        composed += 1

    # --- phase 2: global one-to-one assignment of parsed tags ------------------------------
    allowed: dict[TagKind, frozenset[str]] = {
        TagKind.INSTRUMENT: frozenset({NodeKind.INSTRUMENT, NodeKind.UNKNOWN}),
        TagKind.VALVE: frozenset({NodeKind.COMPONENT, NodeKind.UNKNOWN, NodeKind.JUNCTION}),
        TagKind.EQUIPMENT: frozenset({NodeKind.COMPONENT, NodeKind.UNKNOWN, NodeKind.JUNCTION}),
        TagKind.OFF_PAGE_CONNECTOR: frozenset(
            {NodeKind.COMPONENT, NodeKind.UNKNOWN, NodeKind.JUNCTION}
        ),
    }
    preferred: dict[TagKind, str | None] = {
        TagKind.INSTRUMENT: NodeKind.INSTRUMENT,
        TagKind.VALVE: NodeKind.COMPONENT,
        TagKind.EQUIPMENT: NodeKind.COMPONENT,
        TagKind.OFF_PAGE_CONNECTOR: None,
    }
    pairs: list[tuple[float, int, str, float]] = []
    for r_index in sorted(node_tag_pool):
        region = regions[r_index]
        tag = parsed[r_index]
        for key, data in graph.nodes(data=True):
            if key in tagged_nodes:
                continue
            if data.get("kind") not in allowed[tag.kind]:
                continue
            box = node_bbox(data)
            if _iou(region.bbox, box) >= SELF_BINDING_IOU:
                continue
            gap = _rect_gap(region.bbox, box)
            if gap > attach_gate:
                continue
            adjusted = gap - (kind_bonus if data.get("kind") == preferred[tag.kind] else 0.0)
            pairs.append((adjusted, r_index, key, gap))
    pairs.sort(key=lambda p: (p[0], p[1], p[2]))
    for _, r_index, key, gap in pairs:
        if r_index in claimed or key in tagged_nodes:
            continue
        region = regions[r_index]
        tag = parsed[r_index]
        data = graph.nodes[key]
        _retag(
            graph,
            key,
            label=region.text or "",
            attributes=_tag_attributes(
                tag, region.orientation, "adjacent", gap / unit, region.text or ""
            ),
            confidence=min(float(data["confidence"]), max(region.text_confidence, 0.1)),
        )
        claimed.add(r_index)
        tagged_nodes.add(key)

    for r_index in sorted(node_tag_pool - claimed):
        tag = parsed[r_index]
        unbound.append(
            {
                "text": regions[r_index].text or "",
                "kind": str(tag.kind),
                "reason": f"no compatible node within {ATTACH_GAP_MODULES:.1f} modules",
            }
        )

    # --- phase 3: legacy radius for unread and unparsed regions ----------------------------
    legacy_pairs: list[tuple[float, int, str, float]] = []
    for r_index, region in enumerate(regions):
        if r_index in claimed or r_index in parsed:
            continue
        for key, data in graph.nodes(data=True):
            if key in tagged_nodes:
                continue
            box = node_bbox(data)
            radius = max(box.width, box.height) / 2 + scale.u(LEGACY_RADIUS_MODULES)
            distance = region.centre.dist(node_centre(data))
            adjusted = distance - (scale.u(READ_BIAS_MODULES) if region.text else 0.0)
            if adjusted < radius:
                legacy_pairs.append((adjusted, r_index, key, distance))
    legacy_pairs.sort(key=lambda p: (p[0], p[1], p[2]))
    legacy_bound = 0
    for _, r_index, key, distance in legacy_pairs:
        if r_index in claimed or key in tagged_nodes:
            continue
        region = regions[r_index]
        data = graph.nodes[key]
        label = region.text or f"region@{region.centre.x:.0f},{region.centre.y:.0f}"
        _retag(
            graph,
            key,
            label=label,
            attributes={
                "text_orientation": region.orientation,
                "attach_method": "legacy_radius",
                "attach_distance_modules": f"{distance / unit:.2f}",
            },
            confidence=float(data["confidence"]),
        )
        claimed.add(r_index)
        tagged_nodes.add(key)
        legacy_bound += 1

    # --- phase 4: line numbers annotate the edges of their conductor -----------------------
    line_attrs_written = 0
    orientation_tolerance = math.radians(ORIENTATION_TOLERANCE_DEG)
    for r_index in sorted(line_pool):
        region = regions[r_index]
        tag = parsed[r_index]
        region_angle = 0.0 if region.orientation == "horizontal" else math.pi / 2
        best: tuple[tuple[float, float, int], Polyline] | None = None
        for line in lines:
            difference = abs(line.angle - region_angle)
            difference = min(difference, math.pi - difference)
            if difference > orientation_tolerance:
                continue
            distance, _ = _distance_to_segment(region.centre, line.start, line.end)
            if distance > line_gate:
                continue
            key = (distance, -line.length, line.id)
            if best is None or key < best[0]:
                best = (key, line)
        if best is None:
            unbound.append(
                {
                    "text": region.text or "",
                    "kind": str(tag.kind),
                    "reason": (
                        f"no conductor within {LINE_GAP_MODULES:.1f} modules "
                        "with compatible orientation"
                    ),
                }
            )
            continue
        (distance, _neg_len, _lid), line = best
        payload = {
            "line_number": tag.canonical or "",
            "line_attach_distance_modules": f"{distance / unit:.2f}",
            "line_read_confidence": f"{region.text_confidence:.2f}",
        }
        for name, value in tag.fields.items():
            payload[f"line_{name}"] = value
        carried = 0
        already = 0
        for _u, _v, _k, edata in graph.edges(keys=True, data=True):
            if line.id not in _line_ids(edata):
                continue
            if edata.get("line_number"):
                already += 1
                continue
            edata.update(payload)
            carried += 1
        if carried:
            claimed.add(r_index)
            line_attrs_written += 1
        else:
            unbound.append(
                {
                    "text": region.text or "",
                    "kind": str(tag.kind),
                    "reason": (
                        "conductor already labelled" if already else "conductor carries no edges"
                    ),
                }
            )

    stats = {
        "parsed_regions": len(node_tag_pool) + len(line_pool),
        "composed_bubbles": composed,
        "bound_nodes": len(tagged_nodes) - legacy_bound,
        "bound_edges": line_attrs_written,
        "legacy_labels": legacy_bound,
        "unbound": unbound,
    }
    if unbound:
        preview = "; ".join(f"{u['text']} ({u['reason']})" for u in unbound[:6])
        more = ", ..." if len(unbound) > 6 else ""
        graph.graph.setdefault("warnings", []).append(
            f"{len(unbound)} convention tags parsed but not bound: {preview}{more}"
        )
    return stats

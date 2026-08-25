"""Synthetic drawing generation.

The graph is authored *before* it is drawn, so ground truth is exact at every level at once --
symbols, their classes and positions, conductors, and the topology connecting them. Hand-labelling
gives bounding boxes; only generation gives topology, and topology is what the whole system is
ultimately claiming to recover.

The generator is also the only source of truth that can be *varied on purpose*. Sampling across
modules, sheet sizes, densities and orientations is what measures generalisation, as opposed to
measuring how well the pipeline fits the one drawing it was developed against.

Two limitations are stated rather than discovered later. Synthetic drawings are cleaner and more
regular than real ones, so these numbers are an upper bound. And a grammar that only emits valid
drawings teaches a system the grammar rather than the domain, which is why malformed productions
are generated deliberately.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

# Module values are drawn from a range spanning the plausible plot scales rather than fixed, so a
# pipeline that hardcodes any absolute dimension fails on most samples.
MODULE_RANGE = (1.6, 4.0)
SHEETS = {"ANSI_B": (11 * 72, 17 * 72), "ANSI_D": (22 * 72, 34 * 72), "ISO_A1": (1684, 2384)}

SYMBOL_MODULES = 7.0
"""Device circle diameter, in modules. The standard's dimension."""


@dataclass(frozen=True)
class TruthSymbol:
    id: str
    kind: str
    tag: str
    x: float
    y: float
    radius: float

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (
            self.x - self.radius, self.y - self.radius,
            self.x + self.radius, self.y + self.radius,
        )


@dataclass(frozen=True)
class TruthEdge:
    source: str
    target: str
    style: str


@dataclass
class TruthGraph:
    """The authored graph. Everything the pipeline is expected to recover."""

    symbols: list[TruthSymbol] = field(default_factory=list)
    edges: list[TruthEdge] = field(default_factory=list)
    module: float = 2.4
    sheet: str = "ANSI_B"
    width: float = 0.0
    height: float = 0.0
    defects: list[str] = field(default_factory=list)
    """Deliberate malformations, so a scorer can tell a generator quirk from a pipeline error."""

    def symbol(self, symbol_id: str) -> TruthSymbol | None:
        return next((s for s in self.symbols if s.id == symbol_id), None)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "sheet": self.sheet,
            "width": self.width,
            "height": self.height,
            "defects": self.defects,
            "symbols": [
                {"id": s.id, "kind": s.kind, "tag": s.tag, "x": s.x, "y": s.y, "radius": s.radius}
                for s in self.symbols
            ],
            "edges": [
                {"source": e.source, "target": e.target, "style": e.style} for e in self.edges
            ],
        }


def _tag(kind: str, index: int) -> str:
    if kind == "instrument":
        return f"PI-{100 + index}"
    if kind == "valve":
        return f"MV-{100 + index}-01"
    return f"V-{100 + index}"


def author(
    seed: int,
    *,
    trains: int | None = None,
    density: float = 1.0,
    include_defects: bool = False,
) -> TruthGraph:
    """Author a plant graph.

    Layout follows process-drawing convention -- left-to-right flow along a header with equipment
    on a baseline and instruments above it -- because a randomly placed drawing is either trivially
    easy or so unlike reality that nothing measured on it transfers.
    """
    rng = random.Random(seed)
    module = rng.uniform(*MODULE_RANGE)
    sheet = rng.choice(sorted(SHEETS))
    width, height = SHEETS[sheet]
    radius = SYMBOL_MODULES * module / 2

    graph = TruthGraph(module=module, sheet=sheet, width=width, height=height)
    trains = trains or rng.randint(2, 4)

    margin = width * 0.1
    usable = width - 2 * margin
    baseline = height * 0.5

    counter = 0
    for train in range(trains):
        y = baseline + (train - (trains - 1) / 2) * height * 0.18
        per_train = max(3, int(4 * density))
        spacing = usable / (per_train + 1)
        previous: str | None = None

        for step in range(per_train):
            x = margin + spacing * (step + 1)
            kind = "valve" if step % 2 else "equipment"
            symbol_id = f"s{counter}"
            graph.symbols.append(
                TruthSymbol(
                    symbol_id, kind, _tag(kind, counter), x, y,
                    radius * (1.6 if kind == "equipment" else 1.0),
                )
            )
            if previous is not None:
                graph.edges.append(TruthEdge(previous, symbol_id, "solid"))
            previous = symbol_id
            counter += 1

            # An instrument above the header, joined by a signal line.
            if rng.random() < 0.6 * density:
                inst_id = f"s{counter}"
                graph.symbols.append(
                    TruthSymbol(inst_id, "instrument", _tag("instrument", counter),
                                x, y - height * 0.07, radius)
                )
                graph.edges.append(TruthEdge(symbol_id, inst_id, "dashed"))
                counter += 1

    if include_defects:
        # Malformed productions. A grammar that only emits valid drawings teaches the grammar.
        if len(graph.symbols) > 3:
            duplicate = graph.symbols[1]
            graph.symbols.append(
                TruthSymbol(f"s{counter}", duplicate.kind, duplicate.tag,
                            duplicate.x, duplicate.y + height * 0.25, duplicate.radius)
            )
            graph.defects.append("duplicate_tag")
            counter += 1
        graph.defects.append("crossing_without_junction")

    return graph


def draw(graph: TruthGraph, path: str | Path) -> Path:
    """Render an authored graph to a PDF.

    Line weights follow the standard's ratios to the module rather than absolute widths, so a
    pipeline that recovers the module can recover everything else.
    """
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=graph.width, height=graph.height)
    module = graph.module
    # Line widths follow the convention the sheet series implies. Mixing them -- ISA widths on an
    # ISO sheet -- makes a sample internally inconsistent, and calibration then recovers a module
    # wrong by exactly the ratio between the two conventions.
    narrow = 0.1 if graph.sheet.startswith("ISO") else 0.2
    process_w = 2 * narrow * module
    signal_w = narrow * module

    # Border, to exercise frame detection.
    inset = module * 6
    page.draw_rect(
        pymupdf.Rect(inset, inset, graph.width - inset, graph.height - inset),
        color=(0, 0, 0), width=process_w,
    )

    for edge in graph.edges:
        a, b = graph.symbol(edge.source), graph.symbol(edge.target)
        if a is None or b is None:
            continue
        start = pymupdf.Point(a.x, a.y)
        end = pymupdf.Point(b.x, b.y)
        if edge.style == "dashed":
            # Simulated with short strokes, as real exporters do -- the declared dash attribute
            # cannot be relied upon, and the pipeline must cope with that.
            total = math.hypot(end.x - start.x, end.y - start.y)
            step = module * 1.2
            drawn = 0.0
            while drawn < total:
                t0 = drawn / total
                t1 = min((drawn + step * 0.6) / total, 1.0)
                dash_a = pymupdf.Point(
                    start.x + (end.x - start.x) * t0, start.y + (end.y - start.y) * t0
                )
                dash_b = pymupdf.Point(
                    start.x + (end.x - start.x) * t1, start.y + (end.y - start.y) * t1
                )
                page.draw_line(dash_a, dash_b, color=(0, 0, 0), width=signal_w)
                drawn += step
        else:
            page.draw_line(start, end, color=(0, 0, 0), width=process_w)

    for symbol in graph.symbols:
        centre = pymupdf.Point(symbol.x, symbol.y)
        if symbol.kind == "instrument":
            page.draw_circle(centre, symbol.radius, color=(0, 0, 0), width=signal_w)
        elif symbol.kind == "valve":
            r = symbol.radius
            page.draw_polyline(
                [
                    pymupdf.Point(symbol.x - r, symbol.y - r),
                    pymupdf.Point(symbol.x + r, symbol.y + r),
                    pymupdf.Point(symbol.x + r, symbol.y - r),
                    pymupdf.Point(symbol.x - r, symbol.y + r),
                    pymupdf.Point(symbol.x - r, symbol.y - r),
                ],
                color=(0, 0, 0), width=signal_w,
            )
        else:
            r = symbol.radius
            page.draw_rect(
                pymupdf.Rect(symbol.x - r, symbol.y - r * 1.4, symbol.x + r, symbol.y + r * 1.4),
                color=(0, 0, 0), width=process_w,
            )

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    doc.close()
    return out


def corpus(
    count: int, directory: str | Path, *, seed0: int = 0, defects: bool = False
) -> list[tuple[Path, TruthGraph]]:
    """Generate a corpus, varying module, sheet size and density across samples."""
    out: list[tuple[Path, TruthGraph]] = []
    base = Path(directory)
    for index in range(count):
        rng = random.Random(seed0 + index)
        graph = author(
            seed0 + index,
            density=rng.choice([0.6, 1.0, 1.4]),
            include_defects=defects and index % 3 == 0,
        )
        path = draw(graph, base / f"synthetic_{index:03d}.pdf")
        out.append((path, graph))
    return out

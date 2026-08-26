# Benchmark results

These numbers come from synthetic drawings, not from the sample sheets in `data/`. The correct graph is authored first — every symbol, every edge, every tag — and the drawing is rendered from it afterwards, so nothing here is scored against output the pipeline produced itself. That is the only way topology is known exactly. ISA and ISO size symbols as ratios to a module; the generator varies that module, the sheet size, and the density from sample to sample, which is why a hardcoded point size would fail on most of these drawings rather than passing quietly.

The corpus is seeds 500 through 529. Development was tuned against seeds 0 through 9 only, so anything from seed 500 up is held out. Rates are exact-string matches in drawing coordinates, each with a Wilson interval. One wrong character in a tag is a miss: `PT-101` is not `PI-101`, and character error rate would hide that. Any rate with fewer than five instances behind it is withheld rather than printed.

The generator uses this repository’s stroke alphabet (`recognise/glyphs.py`; `benchmark/strokefont.py` imports it). What is measured is segmentation and matching under randomised size, weight, tracking, shear, and jitter — the same hairline SHX-style strokes the real sheets use. It is not transfer to a font the matcher has never seen. Only the real drawing measures that. Synthetic drawings are cleaner than real ones, so the table is an upper bound.

## Calibration

The module is over-determined: the narrow stroke and the instrument bubble each predict it through a published ratio (ISA Table 6.3: signal line 0.2 measurement units; Table 6.1: bubble 7). Agreement is the confidence signal. All thirty held-out sheets recovered a module and a sheet size. The median error is 7.5 percent; the worst is 15 percent. Downstream thresholds are multiples of whatever was recovered, so a 7.5 percent miss scales the whole page rather than breaking a single hardcoded gate.

| Metric | Value |
|---|---|
| Samples | 30 |
| Module recovered | 30/30 |
| Sheet size identified | 30/30 |
| Median module error | 7.50% |
| Worst module error | 15.01% |

## Detection and connectivity

Symbols here are the instrument bubbles, valves, and other shapes the assembler has to group before it can bind a line. Edges are those bindings: endpoint on a port, or two endpoints coinciding. Text is exact-string. Attachment is whether the right tag landed on the right node. Line attachment is the same idea for line numbers on conductors.

| Metric | Result |
|---|---|
| symbol precision | symbol precision@0.3: 99.8% [99.1%-100.0%] n=623 |
| symbol recall | symbol recall@0.3: 99.4% [98.4%-99.8%] n=626 |
| edge precision | edge precision: 99.6% [98.6%-99.9%] n=518 |
| edge recall | edge recall: 99.4% [98.3%-99.8%] n=519 |
| text precision | text precision: 95.4% [93.7%-96.6%] n=819 |
| text recall | text recall: 93.0% [91.0%-94.5%] n=840 |
| attachment precision | attachment precision: 96.7% [94.9%-97.9%] n=577 |
| attachment recall | attachment recall: 89.7% [87.1%-91.9%] n=622 |
| line precision | line attachment precision: 100.0% [96.1%-100.0%] n=94 |
| line recall | line attachment recall: 90.4% [83.2%-94.7%] n=104 |

Predicted unique edges sit on the authored connectivity (518 predicted against 519 truth pairs). The attachment recall gap is the conservative rule as a number: a tag that cannot bind one-to-one is left unbound rather than assigned to the nearest neighbour and silently duplicating a parallel train.

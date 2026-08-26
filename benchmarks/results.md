# Benchmark results

Protocol: graph authored first, PDF rendered from it, pipeline scored against that truth. Seeds 500–529 (held-out; development used 0–9). Rates are exact-string in drawing coordinates, with Wilson intervals; n < 5 withheld. Generator uses the matcher's stroke alphabet (`recognise/glyphs.py` / `benchmark/strokefont.py`) — segmentation and matching under noise, not font transfer. Synthetic, so an upper bound.

## Calibration

| Metric | Value |
|---|---|
| Samples | 30 |
| Module recovered | 30/30 |
| Sheet size identified | 30/30 |
| Median module error | 7.50% |
| Worst module error | 15.01% |

## Detection and connectivity

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

Predicted unique edges sit on authored connectivity (n=518 against 519 truth pairs). Module and sheet size vary per sample, so a hardcoded point size would fail on most of these drawings.

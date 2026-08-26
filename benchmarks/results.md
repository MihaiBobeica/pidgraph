# Benchmark results

These numbers come from synthetic drawings. We wrote down the correct graph first and rendered the drawing from it afterwards, so nothing here is scored against output the pipeline produced itself.

The corpus is seeds 500 through 529. Development was tuned against seeds 0 through 9 only, so anything from seed 500 up is held out. Rates are exact-string matches in drawing coordinates, each with a Wilson interval. Any rate with fewer than five instances behind it is withheld rather than printed.

The generator uses this repository’s stroke alphabet (`recognise/glyphs.py`; `benchmark/strokefont.py` imports it). What is measured is segmentation and matching under randomised size, weight, tracking, shear, and jitter. It is not transfer to a font the matcher has never seen. Only the real drawing measures that. Synthetic drawings are cleaner than real ones, so treat everything here as an upper bound.

Module and sheet size vary from sample to sample, so any absolute dimension hardcoded in the pipeline would fail on most of these drawings rather than passing quietly.

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

Predicted unique edges sit on the authored connectivity (518 predicted against 519 truth pairs).

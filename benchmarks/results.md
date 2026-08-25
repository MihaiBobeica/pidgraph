# Benchmark results

Scored against synthetic drawings whose ground truth was authored before rendering.

## Calibration

| Metric | Value |
|---|---|
| Samples | 10 |
| Module recovered | 10/10 |
| Sheet size identified | 10/10 |
| Median module error | 0.01% |
| Worst module error | 0.01% |

## Detection and connectivity

| Metric | Result |
|---|---|
| symbol precision | symbol precision@0.3: 100.0% [97.7%-100.0%] n=166 |
| symbol recall | symbol recall@0.3: 99.4% [96.7%-99.9%] n=167 |
| edge precision | edge precision: 46.2% [38.7%-54.0%] n=160 |
| edge recall | edge recall: 54.4% [46.0%-62.5%] n=136 |

## Notes

- Truth is authored before the drawing is rendered, so no part of the pipeline contributed to it.
- Module and sheet size are varied across samples, so any hardcoded absolute dimension would fail on most of them.
- Synthetic drawings are cleaner and more regular than real ones. These are an upper bound, not a prediction of field performance.
- Rates below n=5 are withheld; every reported rate carries its denominator and a Wilson interval.

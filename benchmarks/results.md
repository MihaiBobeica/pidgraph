# Benchmark results

Scored against synthetic drawings whose ground truth was authored before rendering.

## Calibration

| Metric | Value |
|---|---|
| Samples | 12 |
| Module recovered | 12/12 |
| Sheet size identified | 12/12 |
| Median module error | 0.01% |
| Worst module error | 0.01% |

## Detection and connectivity

| Metric | Result |
|---|---|
| symbol precision | symbol precision@0.3: 100.0% [98.2%-100.0%] n=212 |
| symbol recall | symbol recall@0.3: 99.5% [97.4%-99.9%] n=213 |
| edge precision | edge precision: 45.7% [39.0%-52.5%] n=208 |
| edge recall | edge recall: 54.0% [46.6%-61.2%] n=176 |

## Notes

- Truth is authored before the drawing is rendered, so no part of the pipeline contributed to it.
- Module and sheet size are varied across samples, so any hardcoded absolute dimension would fail on most of them.
- Synthetic drawings are cleaner and more regular than real ones. These are an upper bound, not a prediction of field performance.
- Rates below n=5 are withheld; every reported rate carries its denominator and a Wilson interval.

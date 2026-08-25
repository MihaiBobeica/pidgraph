# Benchmark results

Scored against synthetic drawings whose ground truth was authored before rendering.

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
| symbol precision | symbol precision@0.3: 99.7% [98.8%-99.9%] n=624 |
| symbol recall | symbol recall@0.3: 99.4% [98.4%-99.8%] n=626 |
| edge precision | edge precision: 41.4% [38.7%-44.2%] n=1253 |
| edge recall | edge recall: 100.0% [99.3%-100.0%] n=519 |
| text precision | text precision: 99.0% [98.0%-99.5%] n=717 |
| text recall | text recall: 99.0% [98.0%-99.5%] n=717 |

## Notes

- Corpus seeds 500..529. Development tuned against seeds 0..9; a run from seed 500 is held-out data no change was fitted to.
- Truth is authored before the drawing is rendered, so no part of the pipeline contributed to it.
- Text figures measure the vector glyph matcher plus raster fallback. The generator renders the matcher's own stroke alphabet (one definition, stated in code), so these figures cover segmentation and matching under randomised size, weight, tracking, shear and jitter -- not transfer to a foreign shape font, which only the real drawing measures.
- Module and sheet size are varied across samples, so any hardcoded absolute dimension would fail on most of them.
- Synthetic drawings are cleaner and more regular than real ones. These are an upper bound, not a prediction of field performance.
- Rates below n=5 are withheld; every reported rate carries its denominator and a Wilson interval.

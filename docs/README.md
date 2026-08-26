# Documentation

The root [`README`](../README.md) is the entry point: what a piping and instrumentation diagram is, how to install, how to run `check`, and the held-out table. The pages below carry citations, rejected options, and operational detail that do not belong in that file.

Recommended reading order:

1. [`architecture.md`](architecture.md) — one page from PDF marks to a NetworkX graph, then from that graph and a procedure to a report. File paths live here.
2. [`assumptions.md`](assumptions.md) — what extraction, tag parsing, findings, and the held-out claim stand on. A row from this file must not be copied into the code as a constant.
3. [`tradeoffs.md`](tradeoffs.md) — approaches already tried or rejected, and why. A proposed alternative is likely already recorded here.
4. [`../benchmarks/results.md`](../benchmarks/results.md) — how the precision and recall numbers were produced, and what they do not mean.

The remaining two are small:

| File | What it is for |
|---|---|
| [`related-sop.md`](related-sop.md) | An unimplemented idea: a drawing should be linked to a procedure by a person before the two are checked against each other. |
| [`reference/README.md`](reference/README.md) | The Kimray guide is the vocabulary for these oil-and-gas abbreviations. It is not in this repository. |

[`../samples/`](../samples/) is what `check` produced on the drawing and procedure that shipped with the repository. Live runs still write under `outputs/`.

The files under `data/` are a test case. They are not a source of thresholds. The sample drawing’s module happens to be 2.4 points; putting `2.4` in the code would make every later drawing a special case.

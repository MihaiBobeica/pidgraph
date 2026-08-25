# pidgraph

Converts P&ID engineering drawings into a standards-conformant plant graph and cross-references it
against a Standard Operating Procedure.

**Design principle: the supplied documents are one test case, not the specification.** No code
branches on facts about them. Every dimensional threshold is derived from the drawing at run time,
and the guarantee is enforced by a test that rescales a real drawing and asserts the extracted
graph is unchanged.

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
```

```bash
.venv/Scripts/python -m pidgraph.cli doctor
```

```bash
.venv/Scripts/python -m pidgraph.cli check
```

Commands: `doctor` · `probe` · `extract` · `recognise` · `check`.

`doctor` needs nothing beyond Python and reports what is missing. `check` runs the whole pipeline
and writes `outputs/report.md`, `outputs/findings.jsonl` and `outputs/graph.json`.

`extract` and `check` write the graph three ways: the project's own JSON, **GraphML**, and
**node-link JSON**. The latter two load directly into NetworkX:

```python
import networkx as nx
g = nx.read_graphml("outputs/graph.graphml")   # MultiDiGraph, 584 nodes / 1262 edges
nx.shortest_path(g.to_undirected(), source, target)
```

Node attributes carry class, confidence and true drawing coordinates, so a consumer can lay the
graph out as drawn. All commands accept `--pid` and `--sop` to override input discovery.

**Text recognition** uses Tesseract if the binary is present — no key, no network. Results are
cached by crop content hash into `codebook/text_cache.json` and committed, so the pipeline is
offline and deterministic after the first pass.

---

## How it works

```
adapters -> calibration -> recognition -> semantics -> graph -> cross-reference
```

**Calibration recovers the drawing's own module.** Symbol geometry is normatively defined in a
per-drawing dimensionless unit: the standard fixes only its minimum and requires symbols to
preserve the table *ratios* when scaled. So an absolute threshold in points is an assumption about
one plot, and the quantity to recover is the module. It is over-determined — the narrow stroke
width and the dominant symbol diameter each predict it through a different published ratio — and
their agreement is the confidence signal.

On the supplied drawings both estimators give **2.4000 pt** to four decimals across all three
sheets, and the instrument circle then measures **exactly 7.00 modules**, which is the dimension
the standard specifies. Render resolution derives to 600 dpi rather than being fixed.

**Recognition ranks strategies by what the page actually offers**, measured rather than assumed.
This drawing carries both an embedded logo bitmap and a vestigial 69-character text layer, either
of which would misroute a naive "has an image, therefore scanned" check.

**Connectivity comes from endpoint proximity and port binding only.** Two conductors crossing
without a jump are not connected; emitting a junction there fabricates an edge, and a fabricated
edge is structurally identical to a real one, so nothing downstream can detect it.

**The graph is evidence-based.** Conductors are bound to symbols *before* deciding what becomes a
node, so a shape that no conductor reaches, was not dimensionally identified, and is below
equipment scale is not promoted. Candidates dropped this way are counted and reported.

---

## Standards

The convention is taken from the reference guide in [`docs/reference/`](docs/reference/), with the
current standard's additions overlaid as a labelled delta. **Three editions are in play**, and the
schema records which one each row claims:

- the guide's letter table is the **1984** table despite its cover citing 2009 — it carries a
  modifier 2009 deleted and has no Safety Instrumented System entry at all;
- the verified rule set is **2009**;
- the current standard is **2024**.

Adopting the guide wholesale would leave the parser unable to recognise SIS tagging, so that
addition is overlaid explicitly.

Two rules worth naming. `S` in second position means *Safety* only for a self-actuated
emergency-protective element — a closed set of five tags — and *Switch* everywhere else; gating on
the trailing letters instead would classify `LSV`, `ASE` and `ZSV` as safety devices. And the
widely used `DPIT` form writes the differential modifier before the variable; the conformant order
is `PDIT`. It is normalised, reported as a finding, and the observed form retained.

---

## Cross-referencing

Three layers: intra-document consistency (needs no second document), document agreement, and
procedure feasibility.

**Verdicts are deterministic.** A model may write prose; it never decides whether something is a
finding. A compliance-adjacent report has to be reproducible and auditable without an API key.

**The system under-claims.** Findings that rest on *absence* are capped in severity and carry an
extraction-completeness flag, because reporting "missing from the drawing" when extraction merely
missed it accuses a correct document of being wrong.

**Agreement is reported as a first-class result.** The supplied documents agree on every design
limit, and a report that showed nothing in that case would read as a broken tool rather than a
clean pass.

Because a passing run therefore proves nothing, correctness is demonstrated by **fault injection**
— perturbing known-good inputs and asserting each perturbation is caught, where ground truth is
exact by construction. Changed limits, renamed equipment, unit swaps and transposed ranges are each
covered.

---

## What works, and what does not

Measured on the supplied drawings:

| | |
|---|---|
| Calibration | module recovered at confidence 1.00 on all sheets; two estimators agree to 4 dp |
| Instrument symbols | **43** found across three sheets, matching a manual count |
| Text regions | 1073 recovered; structural hints cover 84–92 % of marks |
| Graph | 480 nodes, 299 edges, ~16 s |
| Cross-reference | 5 procedure requirements parsed, including a two-train row and a range |
| Text recognition | 617 regions, 349 read (56%), **89 parsing as valid tags (25%)** with local OCR |
| Graph output | NetworkX `MultiDiGraph`, also written as GraphML and node-link JSON |

**Known gaps, stated plainly:**

- **Text recognition reads 25% of regions as valid tags.** That runs on local OCR with no key, and
  the committed cache makes it reproducible — but a half-scale CAD stroke font is close to a worst
  case for it. Reads like `MV-715-14A` and `1/2"-D2S` are exact; `MV-713-15B` is one character
  wrong. It is not yet good enough to drive the design-limit comparison, so those still report as
  unresolved. The cross-reference engine is complete and its fault-injection suite passes; this is
  a weak input, not a missing capability.
- **Roughly 40 % of nodes are isolated.** The graph reports this on itself rather than hiding it.
- **Dash typing is partial.** An individual dash is shorter than the minimum length separating a
  conductor from a glyph mark, so most never reach line tracing as conductors. Investigation
  confirmed the short marks outside text regions do not form chains. Line role is therefore
  intended to be settled by what a conductor connects.
- **The raster path is not implemented.** The pipeline refuses a raster page rather than returning
  an empty graph.

---

## Testing

```bash
.venv/Scripts/python -m pytest
```

74 tests. The ones that matter most:

- **scale invariance** — rescales a real drawing 0.5× and 2× and asserts the module tracks the
  rescale while symbol-size-in-modules does not move. This is what proves no absolute dimension
  survives in the code.
- **fault injection** — every cross-reference perturbation is caught.
- **safety semantics** — the `S`-gate and SIS cases.
- **negative tests** — title-block boilerplate like `PITTSBURGH` begins with valid function letters
  and must be rejected as a tag.

Tests are split into a general **capability contract** and assertions about the **supplied corpus**,
so nothing in the pipeline can come to depend on one test document.

---

## Documentation

| | |
|---|---|
| [`docs/assumptions.md`](docs/assumptions.md) | Every assumption with source and confidence (verified / likely / uncertain / refuted), plus what was refuted and corrected, what remains uncertain and its fallback, and which choices are decisions rather than facts. Living document. |
| [`docs/architecture.md`](docs/architecture.md) | Components, failure model, calibration, standards core, evaluation design. |
| [`docs/tradeoffs.md`](docs/tradeoffs.md) | Every tension with the options considered **including those rejected**. |
| [`docs/reference/`](docs/reference/) | The reference guide this project treats as its source of truth for convention. |

---

## A note on the input path

The assignment documents the drawing at `data/pid/`; the shipped folder is `data/p&id/`. Both are
probed. That `&` is the PowerShell call operator, a `cmd.exe` separator and a URL query separator —
and `urllib.parse` truncates a path containing it *without raising*. Nothing here interpolates a
path into a shell string or a URL, and storage keys derive from a content hash rather than a
filename.

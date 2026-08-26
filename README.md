# pidgraph

Vector P&ID → NetworkX `MultiDiGraph` → rules engine vs SOP. Thresholds are multiples of the drawing's module `U`. Crossing lines are not joined. Raster / scanned pages are refused.

## Install

Python 3.11+. From the repo root:

Windows:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

```bash
.venv\Scripts\python -m pidgraph.cli doctor
```

(`bin` instead of `Scripts` on Unix.) `doctor` needs nothing but Python. Tesseract is optional (raster text fallback). Ollama is optional (Ask pane). Env vars: [`.env.example`](.env.example).

## Run

Put the drawing under `data/pid/` or `data/p&id/` (`.pdf`) and the procedure under `data/sop/` (`.docx`, `.pdf`, `.txt`, `.md`). The repo ships `data/p&id/diagram.pdf` and `data/sop/sop.docx`. Override with `--pid` / `--sop`.

```bash
.venv\Scripts\python -m pidgraph.cli check
```

Writes:

- `outputs/graph.nodelink.json` — plant graph (NetworkX node-link JSON); also `outputs/<sha256>/graph.nodelink.json`
- `outputs/report.md` — cross-reference
- `outputs/findings.jsonl` — same findings, one object per line

```python
import json
import networkx as nx

raw = json.loads(open("outputs/graph.nodelink.json", encoding="utf-8").read())
g = nx.node_link_graph(raw, edges="edges")
g.number_of_nodes(), g.number_of_edges()
nx.shortest_path(g.to_undirected(), source, target)
```

Nodes: `kind`, `dexpi_class`, `tag_canonical`, `x0,y0,x1,y1`, `confidence`. Edges: `style`, `evidence`, and `line_number` when a line label bound. Edge direction is assembly order, not process flow.

| Command | What it does |
|---|---|
| `probe` | Per-page capabilities (vectors, text, dash arrays, raster) |
| `extract` | Graph only |
| `recognise` | Text yield |
| `benchmark` | Synthetic precision / recall |
| `migrate --apply` | Optional Postgres (`DATABASE_URL`) |

## Approach

Calibration recovers the drawing's own module `U`; later thresholds are multiples of `U`, not point sizes. Per page, `pipeline.run_page` probes what the PDF actually offers, then: calibrate → primitives → frame → lines → text → recognise (vector stroke match, optional Tesseract) → symbols → assemble. Conductors are recovered before text because simulated dashes are glyph-sized. Crossing lines are not joined.

The plant graph is a NetworkX `MultiDiGraph` in node-link JSON. Tags use the ISA-5.1 grammar; unknown shapes stay `unknown`. Cross-reference is a rules engine (`crossref/checks.py`): a model may phrase an answer, it does not decide a finding.

Pipeline order, graph contract, UI: [`docs/architecture.md`](docs/architecture.md). Rejected options: [`docs/tradeoffs.md`](docs/tradeoffs.md).

## Assumptions

Load-bearing ones; the numbered register is [`docs/assumptions.md`](docs/assumptions.md).

- Born-digital vector PDFs only. Raster / scanned pages are refused, not turned into an empty graph.
- The sample drawing in `data/` is a test case. Geometric constants in code are ratios of `U`, never sizes measured off that sheet.
- Kimray's letter table is ISA-5.1-1984. Safety semantics follow ISA-5.1-2009 (`Z` for SIS). Annex guidance is not reported as a violation.
- Nameplate design-limit blocks are not read from the drawing. Absence-based SOP comparisons are capped and marked `needs_review`.
- Held-out scores are synthetic, on the matcher's own stroke alphabet — an upper bound, not font transfer. Protocol: [`benchmarks/results.md`](benchmarks/results.md).

## Test

```bash
.venv\Scripts\python -m pytest
```

Scale invariance (no hardcoded point sizes), SOP fault injection, ISA tag safety, title-block words that are not tags. `tests/test_crossref.py` is how SOP correctness is shown: the shipped procedure agrees with the drawing, so faults are injected.

Held-out sweep (slow; 30 drawings):

```bash
.venv\Scripts\python -m pidgraph.cli benchmark --count 30 --seed0 500 --dir outputs/sweep_corpus --out benchmarks
```

| | precision | recall |
|---|---|---|
| Symbols | 99.8% [99.1–100] n=623 | 99.4% [98.4–99.8] n=626 |
| Edges | 99.6% [98.6–99.9] n=518 | 99.4% [98.3–99.8] n=519 |
| Text | 95.4% [93.7–96.6] n=819 | 93.0% [91.0–94.5] n=840 |
| Tag attachment | 96.7% [94.9–97.9] n=577 | 89.7% [87.1–91.9] n=622 |

## Sample data

Inputs (shipped): `data/p&id/diagram.pdf`, `data/sop/sop.docx`.

Outputs of `pidgraph check` on those files (committed snapshot):

| File | What |
|---|---|
| [`samples/graph.nodelink.json`](samples/graph.nodelink.json) | Plant graph — 384 nodes, 570 edges |
| [`samples/report.md`](samples/report.md) | Cross-reference report |
| [`samples/findings.jsonl`](samples/findings.jsonl) | Same findings, one JSON object per line |

`outputs/` is the live write target and is gitignored. Re-run `check` to refresh it.

## UI

```bash
cd web
npm install
npm run dev
```

`http://localhost:3000`. Left: `data/` tree (PDF / `.docx`; add or remove files, not folders). Middle: Graph or Doc. Right: SOP findings and Ask. Drawing PDFs are extracted; paths under `sop/` (or any `.docx`) are previewed.

Ask tools: `find_tag`, `describe`, `neighbors`, `walk`. Ollama phrases the result if it is up; otherwise the tools still run. `check` and the UI do not need a database. `pidgraph migrate --apply` persists when `DATABASE_URL` is set.

Compose `pipeline` runs the CLI image (`python:3.13-slim-bookworm`). Compose `web` is Node-only and cannot extract — use `npm run dev` against a local `.venv`.

Docs map: [`docs/`](docs/README.md).

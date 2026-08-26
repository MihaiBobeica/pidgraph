# pidgraph

Vector P&ID → NetworkX `MultiDiGraph` → rules engine vs SOP. Thresholds are multiples of the drawing's module `U`. Crossing lines are not joined. Raster / scanned pages are refused.

System map, graph contract, and pipeline order: [`docs/architecture.md`](docs/architecture.md). Citations and measured constants: [`docs/assumptions.md`](docs/assumptions.md).

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

(`bin` instead of `Scripts` on Unix.) `doctor` needs nothing but Python. Tesseract is optional (raster text fallback). Ollama is optional (Ask pane).

Drawings are probed under `data/pid/` and `data/p&id/` (`.pdf` only). Procedures under `data/sop/` (`.docx`, `.pdf`, `.txt`, `.md`). Override with `--pid` / `--sop`. Env vars: [`.env.example`](.env.example).

## Run

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

## UI

```bash
cd web
npm install
npm run dev
```

`http://localhost:3000`. Left: `data/` tree (PDF / `.docx`; add or remove files, not folders). Middle: Graph or Doc. Right: SOP findings and Ask. Drawing PDFs are extracted; paths under `sop/` (or any `.docx`) are previewed.

Ask tools: `find_tag`, `describe`, `neighbors`, `walk`. Ollama phrases the result if it is up; otherwise the tools still run. `check` and the UI do not need a database. `pidgraph migrate --apply` persists when `DATABASE_URL` is set.

Compose `pipeline` runs the CLI image (`python:3.13-slim-bookworm`). Compose `web` is Node-only and cannot extract — use `npm run dev` against a local `.venv`.

## Scores

Held-out synthetic, seeds 500–529, n as shown. Generator draws the matcher's own stroke alphabet — upper bound, not transfer. Protocol: [`benchmarks/results.md`](benchmarks/results.md).

| | precision | recall |
|---|---|---|
| Symbols | 99.8% [99.1–100] n=623 | 99.4% [98.4–99.8] n=626 |
| Edges | 99.6% [98.6–99.9] n=518 | 99.4% [98.3–99.8] n=519 |
| Text | 95.4% [93.7–96.6] n=819 | 93.0% [91.0–94.5] n=840 |
| Tag attachment | 96.7% [94.9–97.9] n=577 | 89.7% [87.1–91.9] n=622 |

## Test

```bash
.venv\Scripts\python -m pytest
```

Scale invariance, SOP fault injection, ISA tag safety, title-block negatives.

```bash
.venv\Scripts\python -m pidgraph.cli benchmark --count 30 --seed0 500 --dir outputs/sweep_corpus --out benchmarks
```

Docs map: [`docs/`](docs/README.md).

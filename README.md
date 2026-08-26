# pidgraph

A piping and instrumentation diagram is how the plant is plumbed and instrumented. A standard operating procedure is how it is supposed to be run. This repository turns the drawing into a NetworkX graph and writes down where that graph and the procedure disagree.

Geometric thresholds follow the drawing’s own module, not a size we measured off one plot. Lines that cross without a jump are left unjoined. A scanned page is refused rather than turned into an empty graph.

## Install

You need Python 3.11 or newer. From the repository root, create a virtual environment and install the package with the development extras.

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

Then run the environment check. On Unix, use `bin` instead of `Scripts`.

```bash
.venv\Scripts\python -m pidgraph.cli doctor
```

`doctor` needs nothing but Python. It tells you what is present and what is missing. Tesseract is optional; without it, raster lettering is left unread. Ollama is optional; without it, the Ask pane still runs the graph tools, it just does not phrase the answer. Configuration knobs live in [`.env.example`](.env.example).

## Run

Place the drawing under `data/pid/` or `data/p&id/` (PDF only) and the procedure under `data/sop/` (Word, PDF, plain text, or Markdown). This checkout already ships `data/p&id/diagram.pdf` and `data/sop/sop.docx`. Pass `--pid` and `--sop` if you do not want that discovery.

```bash
.venv\Scripts\python -m pidgraph.cli check
```

That extracts the graph, compares it to the procedure, and writes three files. `outputs/graph.nodelink.json` is the plant graph in NetworkX node-link JSON; a copy also lands at `outputs/<sha256>/graph.nodelink.json` so two drawings do not overwrite each other. `outputs/report.md` is the human-readable cross-reference. `outputs/findings.jsonl` is the same findings, one JSON object per line.

To load the graph:

```python
import json
import networkx as nx

raw = json.loads(open("outputs/graph.nodelink.json", encoding="utf-8").read())
g = nx.node_link_graph(raw, edges="edges")
g.number_of_nodes(), g.number_of_edges()
nx.shortest_path(g.to_undirected(), source, target)
```

Nodes carry a kind, a DEXPI class where we know it, a canonical tag, drawing-space coordinates, and a confidence. Edges carry a line style, the evidence for the connection, and a line number when a label bound. Edge direction is the order the assembler walked the drawing, not process flow.

Other commands:

| Command | What it does |
|---|---|
| `probe` | Reports what each page actually offers: vectors, a text layer, dash arrays, raster. |
| `extract` | Builds the graph and stops there. |
| `recognise` | Prints how much lettering was read. |
| `benchmark` | Draws synthetic sheets and scores precision and recall. |
| `migrate --apply` | Applies the optional Postgres schema when `DATABASE_URL` is set. |

## Approach

Each page is asked what it actually contains before anything is assumed. Calibration recovers the drawing’s own module. Later thresholds are multiples of that unit, so an absolute size in points would be a fact about one plot, not a rule.

The title block and furniture are stripped. Conductors are recovered before lettering, because a simulated dash is about the size of a glyph and only chaining can tell the two apart. Stroke lettering is read from the pen paths that are already in the file; Tesseract is the fallback when the matcher refuses. Letter-shaped marks that no recogniser could read are returned to the symbol pool, then symbols are grouped, then line ends are bound to ports. A fabricated edge looks identical to a real one later, so crossing lines without a jump are not joined.

The plant graph is a NetworkX `MultiDiGraph`. Tags are parsed with the ISA-5.1 grammar. Unknown shapes stay `unknown` rather than being forced to the nearest class. The cross-reference is a rules engine: a language model may phrase an answer, it does not decide a finding.

The page-by-page map and the graph contract live in [`docs/architecture.md`](docs/architecture.md). Options we already rejected live in [`docs/tradeoffs.md`](docs/tradeoffs.md).

## Assumptions

We only extract born-digital vector PDFs. The sample drawing in `data/` is a test case; nothing measured off that sheet may become a constant in the code. Kimray’s letter table is the 1984 ISA table, not the 2009 edition its cover claims, so Safety Instrumented System tagging (`Z`) is overlaid from the later standard. Annex guidance is not reported as a violation. Nameplate design-limit blocks are not read from the drawing, because pinning a lone pressure to the wrong vessel is worse than leaving the comparison unresolved. The held-out scores are synthetic, and the generator draws this matcher’s own stroke alphabet, so treat them as an upper bound rather than a prediction on an unseen font.

The numbered register, with citations, is [`docs/assumptions.md`](docs/assumptions.md). How the scores were produced is [`benchmarks/results.md`](benchmarks/results.md).

## Test

```bash
.venv\Scripts\python -m pytest
```

The important groups are scale invariance (no hardcoded point sizes), fault injection against the procedure, ISA tag safety semantics, and title-block words that merely look like tags. The shipped procedure agrees with the shipped drawing, so correctness of the rules is shown by mutating the procedure in `tests/test_crossref.py`, not by waiting for a real discrepancy.

To re-run the held-out sweep (slow: it renders and extracts thirty drawings):

```bash
.venv\Scripts\python -m pidgraph.cli benchmark --count 30 --seed0 500 --dir outputs/sweep_corpus --out benchmarks
```

These figures are from those thirty drawings (seeds 500–529). Development only saw seeds 0–9. The generator draws the matcher’s own letters, so read the text row narrowly: this is segmentation and matching under noise, not transfer to a foreign font. Treat the whole table as an upper bound on real drawings.

| | precision | recall |
|---|---|---|
| Symbols | 99.8% [99.1–100] n=623 | 99.4% [98.4–99.8] n=626 |
| Edges | 99.6% [98.6–99.9] n=518 | 99.4% [98.3–99.8] n=519 |
| Text | 95.4% [93.7–96.6] n=819 | 93.0% [91.0–94.5] n=840 |
| Tag attachment | 96.7% [94.9–97.9] n=577 | 89.7% [87.1–91.9] n=622 |

## Sample data

The drawing and procedure that shipped with the repository are `data/p&id/diagram.pdf` and `data/sop/sop.docx`. Running `pidgraph check` on those files produced the snapshot in `samples/`:

| File | What |
|---|---|
| [`samples/graph.nodelink.json`](samples/graph.nodelink.json) | The plant graph: 384 nodes and 570 edges. |
| [`samples/report.md`](samples/report.md) | The cross-reference report. |
| [`samples/findings.jsonl`](samples/findings.jsonl) | The same findings, one JSON object per line. |

Live runs still write under `outputs/`, which is gitignored. Run `check` again to refresh it.

## Review UI

There is an optional browser for looking at the graph, paging through the PDF, previewing the Word procedure, and jumping from a mismatch to a tag.

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:3000`. The left pane is the `data/` tree (PDF and Word only; you can add or remove files, not folders). The middle pane is the graph or the document. The right pane is procedure findings and Ask. Drawing PDFs are extracted; anything under `sop/`, or any Word file, is previewed instead.

Ask uses `find_tag`, `describe`, `neighbors`, and `walk`. If Ollama is running, it phrases the result; if it is not, the tools still answer. Neither `check` nor the UI needs a database. `pidgraph migrate --apply` persists to Postgres when `DATABASE_URL` is set.

`docker compose` can run the command-line image (`python:3.13-slim-bookworm`). The web image is Node-only and cannot extract; for that, use `npm run dev` against a local virtual environment.

A map of the rest of the documentation is in [`docs/`](docs/README.md).

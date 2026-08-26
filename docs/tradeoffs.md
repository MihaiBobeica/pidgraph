# Trade-offs

These decisions still shape the code. A proposed alternative is likely already recorded here. The measurements and clause numbers live in [`assumptions.md`](assumptions.md).

## Probe per stage, not a vector fork

Real pages mix good geometry with a useless text layer. The sample drawing is a born-digital CAD plot whose text layer is a logo footer. Forking the whole pipeline into “vector” versus “raster” would discard that geometry the moment `/Contents` looked empty. Each stage (lines, symbols, text) picks from a probe of what the page actually has. Raster ingest is specified and currently refused rather than returning an empty graph — an empty graph that reports success is the worst failure this pipeline can produce.

## Endpoints, never crossings

On a piping and instrumentation diagram, two pipes that cross are usually passing at different elevations. The drafter draws a small jump (a hop) to mark a noticed crossing, and draws nothing when the lines simply do not connect. Endpoints are joined; crossings are not. A fabricated edge is structurally identical to a real one later — the graph cannot mark it as a guess — and a missed genuine hop is the cheaper error.

## Recover the module

ISA-5.1 clause 4.1.6 requires symbols to keep the size ratios in the tables when the drawing is scaled. Clause 6 defines those sizes in measurement units and fixes only a minimum; the actual length is a free per-drawing parameter. ISO 81714-1 calls the same quantity M. Absolute point sizes are facts about one plot (the sample’s module happens to be 2.4 points against a 7-unit bubble). The module is recovered rather than hardcoded. Calibration may fail; failure is preferred to silently fitting the sample sheet.

## Greedy one-to-one labels

A tag sits beside its symbol, or stacked inside the instrument bubble. Nearest-neighbour by centre swaps tags on parallel trains: the long string that belongs to the nearer vessel is closer, by centre, to the farther one. Labels are assigned greedy and one-to-one over ascending box gap, with a small bonus for the drafting-preferred kind (`extract/attach.py`). A text region labels at most one node. Attachment never creates, deletes, or rewires topology; a previous change that also touched promotion cost 157 real-drawing nodes.

## Node-link JSON, not a graph database

The on-disk form is NetworkX node-link JSON. Postgres is an optional persist when `DATABASE_URL` is set, not the primary store. Neo4j, GraphML, and a custom `graph.json` were not taken. DEXPI 1.4 serialises as Proteus Schema 4.2.0; DEXPI 2.0 replaces Proteus, so class names are the stable surface and serialisation stays behind an adapter.

## Unknown stays unknown

Classes are DEXPI names; tags follow the ISA grammar. Unknown symbols stay `unknown`. Forcing the nearest class hides template overfit, and the standard itself gives some shapes two meanings until the legend is read (a diamond-in-square is “alternate choice or SIS” after 2009, and programmable logic only on older drawings). Those cases are listed rather than guessed.

## Rules decide findings

A report that touches how a plant is supposed to be run has to be auditable without an API key. Rules decide findings. A model may only phrase them. The Ask pane is optional local Ollama; without it the graph tools still answer.

## Author the graph, then render it

Synthetic graphs are authored first, then rendered. That is the only way topology is known exactly. The held-out table is an upper bound and is labelled as one: the generator draws this matcher’s own stroke alphabet. Fine-tuning on the three real sheets was rejected. Training and holding out on the same handful is not possible, and doing so would destroy the only independent measurement available.

## Exact-string text, drawing-space scores

Text accuracy is exact-string, not character error rate. One wrong character in a tag is a different component: `PT-101` is not `PI-101`. Grammar-constrained substitution was measured: it “repaired” seven reads and produced `4-14`→`A-14`, `S08`→`508`, `2-D5S`→`Z-05S` — each grammatically valid, each meaningless. Substitution is off. Despacing (`MV-71 5-01`→`MV-715-01`) is unambiguous and remains.

Scores are computed in drawing coordinates, never pixels, so a resolution change does not move the number.

## Local files

The command line and the files are local. The UI is Next.js shelling `python -m pidgraph.*`. There is no Python HTTP server and no hosted worker. Docker Compose is optional, and the web image cannot extract.

## Annexes are advice

ISA-5.1-2024 moved annexes A and B into technical reports that are explicitly nonmandatory. Annex guidance is not reported as a violation.

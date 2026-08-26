# Trade-offs

These are decisions that still shape the code. If you are about to propose an alternative, it is probably already here. Citations live in [`assumptions.md`](assumptions.md).

Real pages mix good geometry with a useless text layer, so we did not fork the whole pipeline into vector versus raster. Each stage (lines, symbols, text) picks from a probe of what the page actually has. Raster ingest is specified and currently refused rather than returning an empty graph.

We join endpoints and never crossings. A fabricated edge is structurally identical to a real one, and missing a genuine hop is the cheaper mistake.

We recover the drawing’s own module instead of hardcoding point sizes. Absolute thresholds are facts about one plot. Calibration can fail; we would rather it fail than silently fit the sample sheet.

Labels are assigned greedy and one-to-one over ascending box gap, with a small bonus for the drafting-preferred kind (`extract/attach.py`). Nearest-neighbour swaps tags on parallel trains. A text region labels at most one node.

The on-disk form is NetworkX node-link JSON. Postgres is an optional persist when `DATABASE_URL` is set, not the primary store. Neo4j, GraphML, and a custom `graph.json` were not taken.

Classes are DEXPI names; tags follow the ISA grammar. Unknown symbols stay `unknown`. Forcing the nearest class hides template overfit.

Rules decide findings. A model may only phrase them. The Ask pane is optional local Ollama.

Synthetic graphs are authored first, then rendered. That is the only way topology is known exactly. The held-out table is an upper bound and is labelled as one. Fine-tuning on the three real sheets was rejected: you cannot train and hold out on the same handful.

Text accuracy is exact-string, not character error rate. One wrong character in a tag is a different component.

Scores are computed in drawing coordinates, never pixels, so a resolution change does not move the number.

The command line and the files are local. The UI is Next.js shelling `python -m pidgraph.*`. There is no Python HTTP server and no hosted worker. Docker Compose is optional.

Annex guidance in the standards is advisory. It is not reported as a violation.

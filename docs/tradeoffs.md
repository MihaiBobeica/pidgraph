# Trade-offs

Decisions that still shape the code. Citations: [`assumptions.md`](assumptions.md).

**Capability per stage, not a vector/raster fork.** Real pages mix good geometry with a useless text layer. Each stage picks from a probe. Raster ingest is specified and currently refused.

**Join endpoints, never crossings.** A fabricated edge is structurally identical to a real one.

**Recover the module `U` instead of hardcoding point sizes.** Absolute thresholds are facts about one plot. Calibration can fail.

**Greedy one-to-one over ascending bbox gap for labels, not nearest-neighbour.** Global sort plus a kind bonus; a text region labels at most one node (`extract/attach.py`).

**NetworkX node-link JSON on disk.** Postgres is optional persist (`DATABASE_URL`), not the primary store. Neo4j / GraphML / a custom `graph.json` were not taken.

**DEXPI class names, ISA tag grammar.** Unknown symbols stay `unknown`.

**Rules decide findings; a model may only phrase them.** Ask is optional local Ollama.

**Synthetic graphs first, then render.** Topology is known exactly. The held-out table is an upper bound. Fine-tuning on the three real sheets was rejected.

**Exact-string accuracy for text, not character error rate.** One wrong character in a tag is a different component.

**Score in drawing coordinates**, never pixels.

**Local CLI and files.** Next.js shells `python -m pidgraph.*`; there is no Python HTTP server and no hosted worker. Docker Compose is optional.

**Normative vs advisory standards.** Annex guidance is not reported as a violation.

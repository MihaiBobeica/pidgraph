# Engineering Trade-offs Considered

Every significant tension, the options weighed, where it landed, and what that costs. **Options that
were rejected are recorded with what they would have bought** — the rejections carry as much
information as the choices.

`Rev?` = cost to reverse later: **easy** (config), **med** (a module), **hard** (schema or architecture).

See also: [`architecture.md`](architecture.md) for the design, [`assumptions.md`](assumptions.md) for
what each decision rests on.

---

## 1. Extraction

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Exactness on rich inputs vs generality across all inputs | (a) vector-only, exact on born-digital · (b) raster-only, universal · (c) capability-driven strategies | **(c)** | Two or three implementations per problem to build and test | hard |
| One pipeline fork vs per-stage strategy | (a) binary vector/raster fork · (b) per-stage resolution on a measured capability descriptor | **(b)** | More plumbing. Justified because a real page often needs the best option for one stage and the worst for another — a fork cannot express that | hard |
| Connectivity from intersections vs endpoints | (a) detect crossings as junctions · (b) endpoint proximity + symbol-port binding only | **(b)** | Genuine hops may be missed. Accepted because a fabricated edge is structurally identical to a real one and undetectable downstream — the asymmetry is decisive | hard |
| Greedy vs global label association | (a) nearest-neighbour · (b) Hungarian assignment with a margin recorded as confidence | **(b)** | O(n³). Greedy silently swaps tags on parallel equipment trains and valve manifolds, mislabelling two nodes at once | med |
| Graph fidelity | (a) semantic nodes only · (b) full planar graph including junctions · (c) both | **(c)** — build planar, filter junctions from the default view | Larger graph and one extra predicate everywhere | med |
| Text-region proposal | (a) structural hints from the source · (b) geometric clustering · (c) connected components | **All three, ranked by capability** | Fallback paths must be built even when the preferred one works on the sample | med |

## 2. Calibration

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Absolute thresholds vs derived scale | (a) constants tuned on a sample · (b) recover the drawing's own module | **(b)** | Calibration becomes a new failure mode; mitigated by cross-checking independent estimators. Non-negotiable: absolute point sizes are plot artifacts | hard |
| Which estimator anchors scale | (a) stroke width · (b) modal text cap height · (c) sheet size · (d) zone-grid pitch | **(b) primary, (a) secondary with a sanity gate, (c) as a unit-system prior only, (d) opportunistic** | Text must be measured as ink extent, not a font operand. Sheet size cannot recover plot scale on its own | med |
| Stroke width: discard or use | (a) discard as unreliable · (b) use as a scale proxy · (c) use as a *class* proxy | **(c)** — and (a) for scale | Initially discarded outright, which threw away a standards-mandated node/edge-type prior. Being scale-invariant is exactly what makes it a clean class signal | med |
| Symbol size: predict or detect | (a) predict from the module · (b) mode-seek the radius histogram, then validate against the module | **(b)** | Requires enough instances to form a mode. The mode is the strongest single signal in a P&ID and needs no external anchor | med |
| Render resolution | (a) fixed DPI · (b) derived from cap height | **(b)** | A drawing at a different plot scale renders at a different DPI automatically; a fixed value is either wasteful or below the legibility floor | easy |

## 3. Data model

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Graph storage | (a) relational nodes/edges in Postgres · (b) Neo4j · (c) Apache AGE · (d) one JSON blob per drawing | **(a)** | Wordier traversals than Cypher. (b) splits "documents with the graph" across two stores; (c) is unavailable on the platform; (d) cannot be queried or partially updated | hard |
| Vocabulary | (a) invent enums · (b) adopt a published information model | **(b)** — DEXPI, foreign-key enforced | Must track spec editions and their restructuring. Gains interoperability and a conformance claim that is checkable rather than asserted | hard |
| Enums vs lookup tables | (a) Postgres enums · (b) seeded lookup tables | **(b)** for the class vocabulary, enums only for closed sets | Slightly slower joins; avoids a migration hazard when a new class appears at runtime | hard |
| Spatial queries | (a) PostGIS · (b) plain numeric bounding boxes | **(b)** | No GiST spatial SQL. Spatial joins happen in-process during extraction and client-side in the UI, so PostGIS would be operational weight for a query never issued | med |
| Entity resolution | (a) exact tag grammar · (b) trigram fuzzy · (c) embeddings | **(a) primary, (b) prose only, (c) optional third tier** | Trigram similarity on tag identifiers binds near-identical tags to the wrong component — restricted to descriptive text | easy |
| Write path | (a) REST client · (b) direct Postgres connection | **(b)** | Two access paths to maintain. Buys one real transaction, which removes an entire class of half-written-graph workarounds | med |
| Run handling | (a) overwrite · (b) versioned runs | **(b)** | More rows; enables run-to-run diffing and makes re-extraction non-destructive | hard |
| Identity | (a) database UUID · (b) content-addressed stable key | **Both** — UUID as primary key, stable key as semantic identity | The key generator must survive small coordinate perturbation, which needs a test | hard |

## 4. Recognition

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Symbol recognition | (a) shape codebook built per drawing · (b) trained object detector · (c) template matching | **(a) primary, (c) raster fallback, (b) optional** | The codebook needs a labelling bootstrap. (b) has no training data without the generator; (c) is brittle to scale and rotation without normalisation | med |
| Text recognition | (a) per-glyph shape codebook · (b) crop OCR · (c) local transformer OCR | **(b)**, cached and committed | (a) was tried and **measured not to converge** — the cluster tail is real, not a normalisation bug. Reported as a negative result with numbers | med |
| Unknown symbols | (a) force to nearest known class · (b) explicit `unknown` class routed to review | **(b)** | A review surface to build. Forcing is how template overfit becomes invisible | med |
| Ambiguous symbols | (a) pick the most likely class · (b) emit candidates plus a `requires_legend` flag | **(b)** | Downstream must handle unresolved classes. Some standard symbols are genuinely ambiguous without a legend sheet — guessing would be wrong on a large fraction of real drawings | med |

## 5. Evaluation

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Ground truth | (a) exhaustive hand labelling · (b) model-proposed with spot check · (c) synthetic generation from known graphs · (d) public annotated dataset | **(c) primary, (d) external validity, (a)/(b) on a small held-out real set** | Synthetic is cleaner than reality, so it is an upper bound — reported as such. Only (c) gives exact truth at the *topology* level | hard |
| Synthetic randomisation | (a) appearance only · (b) structure only · (c) both, each axis mapped to a named failure mode | **(c)** | Appearance is cheap and structure is expensive, so the pull is toward (a) — which leaves association and connectivity failures undefended while metrics look thorough | med |
| Grammar scope | (a) only valid drawings · (b) include deliberately malformed productions | **(b)** | More generator complexity. A grammar that emits only valid drawings teaches the model the generator, not the domain | med |
| Generator role | (a) evaluation tool built last · (b) development substrate built early | **(b)** | Grammar, symbol library, layout engine and renderer land on the critical path. Buys a debuggable loop for the highest-variance extraction work | hard |
| Real drawings | (a) fine-tune on them · (b) validate and calibrate only | **(b)** | Fine-tuning unlocks only with enough real labelled drawings to hold out a genuine test set. On a handful you cannot both fine-tune and validate | med |
| Detection matching | (a) single IoU threshold · (b) swept with a reported curve | **(b)** | More computation. A single threshold is an arbitrary claim, and small symbols are penalised disproportionately | easy |
| Text metric | (a) character error rate · (b) exact-string accuracy | **(b) headline, (a) diagnostic** | Looks worse. CER hides exactly the single-character errors that change which component a tag refers to | easy |
| Scoring space | (a) pixels · (b) drawing coordinates | **(b)** | A little conversion code. In pixel space every score moves when render resolution changes | med |
| Statistics | (a) point estimates · (b) intervals with denominators, enforced by the formatter type | **(b)** | Uglier tables. At these sample sizes a bare percentage certifies almost nothing | med |
| Rejected approaches | (a) omit them · (b) report with their numbers | **(b)** | A negative result with data is stronger evidence of rigour than silence | easy |

## 6. Cross-reference

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Who decides a finding | (a) model judgement · (b) deterministic rules, model restricted to prose | **(b)** | More code. A compliance-adjacent report must be auditable and reproducible without an API key | hard |
| Coverage | (a) document-comparison checks only · (b) three layers, including intra-drawing consistency needing no second document | **(b)** | More checks to tune. Layer 1 alone produces nothing when the documents legitimately agree | med |
| Full agreement | (a) report nothing · (b) report verified matches as first-class results | **(b)** | A larger report. A blank "no discrepancies" screen reads as broken rather than as a pass | easy |
| Absence-based findings | (a) assert them · (b) cap severity and flag extraction completeness | **(b)** | Fewer dramatic findings. Accusing a correct document of being wrong is the worst output this system can produce | med |
| Correctness demonstration | (a) wait for a real discrepancy · (b) fault injection with catalogued perturbations | **(b)** | A mutation harness to build. Ground truth is then exact by construction | easy |
| Non-conformant input | (a) reject · (b) normalise silently · (c) normalise, retain the original, and report | **(c)** | A conformance taxonomy. Silent rewriting loses information; rejection loses the drawing | easy |
| Guidance vs conformance | (a) treat all standard material as rules · (b) separate normative from advisory tiers | **(b)** | Two tiers to maintain. Some standard annex material is explicitly non-mandatory — reporting violations against it would be reporting non-violations | med |

## 7. UI

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Stack | (a) Next.js reading the database directly · (b) SPA plus an API service · (c) Python-native dashboard · (d) desktop | **(a)** | A second toolchain in the repo. (b) adds a service with no added capability here; (c) cannot do the synchronised deep-zoom overlay well; (d) is hardest for a reviewer to run | hard |
| Read path | (a) direct database reads · (b) an API layer | **(a)** | Query logic moves clientward and the schema becomes the public contract. No user-facing mutation needs business logic beyond review actions | med |
| Graph layout | (a) force-directed · (b) hierarchical/orthogonal · (c) as-drawn from real coordinates | **(c) per sheet, (b) for the merged cross-sheet graph** | Two layout modes. Force-directed produces a hairball that undermines credibility with anyone who reads piping drawings | easy |
| Overlay rendering | (a) one element per hotspot · (b) a single transformed vector overlay | **(b)** | Manual transform maths. Per-hotspot overlays repaint every element each frame and collapse to single-digit frame rates | med |
| Uncertainty | (a) present a clean graph · (b) expose a confidence layer | **(b)** | Admits imperfection visibly. It is simultaneously the most honest and the most distinctive thing in the interface | easy |
| Progress signalling | (a) database notifications · (b) realtime subscriptions or polling | **(b)** | Notification delivery through a connection pooler is undocumented and unreliable | easy |
| Build order | (a) breadth first · (b) dual pane and findings first, extras cut from the outside in | **(b)** | Some features may not ship. A polished shell over a weak pipeline is the classic failure of this kind of project | easy |

## 8. Deployment

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Where the pipeline runs | (a) hosted background worker · (b) in-process inside the web service · (c) locally, hosting only the UI | **(c)** | No hosted ingestion on the free tier. Forced: the free tier has no background workers, spins services down, has an ephemeral disk, and gives 512 MB — async ingestion cannot fit | med |
| Job transport | (a) a queue table as the API · (b) an HTTP service · (c) a local CLI | **(c)**, with the others documented for the paid path | Batch ingestion is a fine model for this workload; removes a service and its auth surface | easy |
| Database connection | (a) direct · (b) session pooler · (c) transaction pooler | **(b)** | Fewer poolable connections. Direct is IPv6-only and fails from IPv4 egress; transaction mode drops session features | easy |
| Artefact storage | (a) local disk · (b) object storage always, including in local dev | **(b)** | Slower dev loop. Hosted filesystems are ephemeral, so exercising the storage path late means discovering it broken in production | med |
| Container contents | (a) mirror the dev environment · (b) deliberately diverge — headless imaging, no deep-learning stack | **(b)** | Requirements must be curated rather than frozen from the environment | easy |
| Base image | (a) newest slim tag · (b) pin the previous stable Debian release | **(b)** | Slightly older packages. The newest release renamed many library packages and removed others, which breaks copied build recipes | easy |

## 9. Scope and process

| Tension | Options considered | Landed | Cost accepted | Rev? |
|---|---|---|---|---|
| Breadth vs depth | (a) five things at 70 % · (b) a strict cut order with a protected core | **(b)** | Some optional items will not ship | easy |
| What is cut last | (a) features · (b) evaluation | **Never evaluation** | A working system with unjustified numbers is worth less than a partial system with honest ones | easy |
| Standards seeding | (a) seed the full published vocabulary · (b) seed what the corpus actually uses | **(b)**, scripted so widening it is a re-run | Coverage gaps on unusual drawings, surfaced as `unknown` rather than mis-classified | easy |
| Conflicting standard editions | (a) pick one silently · (b) name the target edition and record it as data | **(b)** | Every seeded row carries an edition. Without it a conformance claim is unfalsifiable | hard |
| Third-party libraries with network-copyleft terms | (a) use in the deployed service · (b) confine to offline validation · (c) relicense the project | **(b)** | Hand-written serialisation instead of a library. Keeps the licence question out of the deployment | med |
| Assumption tracking | (a) document once · (b) a living register updated in the same commit as any change | **(b)** | Ongoing discipline. A register that goes stale is worse than none, because it is trusted | easy |

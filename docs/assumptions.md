# Assumptions Register

Every assumption this project rests on, with its source and a confidence verdict.

**This is a living document.** Any assumption that changes during the build is updated in the same
commit as the change. The register's value is that it stays true, not that it was written once.

**Confidence vocabulary**

| Code | Meaning |
|---|---|
| **V** | Verified — a primary or authoritative source was retrieved and quoted, or the value was measured directly |
| **L** | Likely — consistent secondary sources, no primary retrieved |
| **U** | Uncertain — could not confirm; sources conflict, are paywalled, or are absent |
| **R** | Refuted — positive evidence the original claim was wrong; the corrected value is given |

**Normative reference.** Input drawings are assumed to follow the convention documented in the
*Kimray How to Read an Oil & Gas P&ID Reference Guide* (Rev. 01/2021, 13 pp), held at
`docs/reference/`. Where it is silent we fall back to the standards below. Where it and a drawing
disagree, the drawing is reported as non-conformant rather than reinterpreted.

---

## INPUT — measured directly from the supplied files

All **V** — measured, not inferred. These describe *one test case* and must never appear as constants
in code.

| ID | Assumption | Source |
|---|---|---|
| INPUT-01 | Born-digital CAD vector plot, 3 sheets, ANSI B page box, rotated 270 degrees | measured |
| INPUT-02 | No usable text layer (69 chars/page, a logo footer only) | measured |
| INPUT-03 | 1078 `AutoCAD SHX Text` annotations; `/Contents` key is **absent**; they cover 93.1 / 84.3 / 78.5 % of black glyph ink | measured |
| INPUT-04 | **No dash arrays** — all 18319 paths report `[] 0`; dashed lines are simulated with runs of short strokes | measured |
| INPUT-05 | Exactly one non-zero stroke width; process pipes are degenerate *filled* rectangles | measured |
| INPUT-06 | 43 instrument circles at a single diameter | measured |
| INPUT-07 | Dimensions decode as 0.2 m.u. (stroke) and 7.000 m.u. (bubble) against ISA Table 6.1 / 6.3 | measured + arithmetic |
| INPUT-08 | SOP design-limit rows all agree with the drawings (the legitimate full-agreement case) | measured |
| INPUT-09 | A company logo accounts for roughly 45 % of page-0 paths | measured |
| INPUT-10 | Kimray writes the differential modifier lower case (`PdI`, `PdS`, `PdSH`) — a third form matching neither ISA's `PDI` nor the industry's `DPI` | measured |

---

## STD — Standards text

| ID | Assumption | Source | C |
|---|---|---|---|
| STD-01 | `S` = *Safety* only when the first letter is `F`/`P`/`T` **and** the device is a self-actuated emergency-protective element — the set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Elsewhere `S` = *Switch*. `S` must **not** denote SIS; **`Z`** is the SIS variable modifier | ANSI/ISA-5.1-2009 Cl. 4.2 notes 14, 14(d), 30; Table 4.1 | **R** |
| STD-02 | **Kimray's letter table is the ISA-5.1-1984 table**, not 2009, despite the cover claim. Tells: 1984 header structure; `M` modifier = *Momentary* (deleted in 2009); `P` = *Pressure, Vacuum* (shortened in 2009); **no Safety Instrumented System entry** | guide p.4, verified directly | **V** |
| STD-03 | Current edition is **ANSI/ISA-5.1-2024**; Annexes A/B moved to ISA-TR5.1.02/03-2024 and are explicitly **nonmandatory guidance** | isa.org ISA-5 series; TR5.1.03-2024 Cl.1 | **V** |
| STD-04 | ISA-5.1-2009 Clause 6 defines dimensions in **measurement units (m.u.)**; 6.2.1 minimum 1/16 in (0.0625 in) or 1.50 mm; 6.2.2 size = shape m.u. times a selected equivalent dimension; Table 6.1 bubble = `7[8]` m.u. | ANSI/ISA-5.1-2009, read directly | **V** |
| STD-05 | 4.1.6 — all symbols **must preserve the size ratios** shown in the tables when reduced or enlarged | ANSI/ISA-5.1-2009 | **V** |
| STD-06 | 6.1.5 — traditional minimum device circle 10.5 mm (7/16 in), optionally 12 mm (1/2 in). Note 4.1.4 says "7/16 in or 11 mm" — the standard is internally inconsistent by ~5 % | ANSI/ISA-5.1-2009 | **V** |
| STD-07 | Differential `D` is a Column-2 variable modifier following the first letter, so the conformant form is `PDI`/`PDIT`; `DPI`/`DPIT` is a non-conformant industry variant | ANSI/ISA-5.1-2009 Table 4.1, note 11(a) | **V** |
| STD-08 | Exactly five failure-position codes: `FO`, `FC`, `FL`, `FL/DO`, `FL/DC`. **`FI` is not among them** | ANSI/ISA-5.1-2009 Table 5.4.4 | **V** |
| STD-09 | Diamond-in-square = "Alternate Choice **or** Safety Instrumented System" in 2009 (programmable logic control only pre-2009). **The shape cannot distinguish the two without the legend sheet** | ANSI/ISA-5.1-2009 Intro para 20; Table 5.1.1 headings | **V** |
| STD-10 | Clause 6 is **new in 2009** — every pre-2009 drawing is dimensionally unconstrained by ISA | ANSI/ISA-5.1-2009 Intro para 16 | **V** |
| STD-11 | Table 6.3: signal line 0.2 m.u., process/equipment line 0.4 m.u.; clearance around a symbol = half the symbol width | notes read directly; numeric values decoded from the table artwork | **L** |
| STD-12 | ISO 10628-1:2014 5.3.1 assigns line width **by object class** against M = 2.5 mm: 1.0 mm (0.4 M) main flow; 0.5 mm (0.2 M) equipment, unit frames, **subsidiary and utility lines**; 0.25 mm (0.1 M) valves, fittings, instrumentation, control/data lines. Below 0.25 mm shall not be used | ISO 10628-1:2014 | **V** |
| STD-13 | ISO 10628-1:2014 5.4.2 — lettering 5 mm for equipment designations, 2.5 mm for other lettering (a 2:1 ratio usable to separate equipment tags from annotation) | ISO 10628-1:2014 | **V** |
| STD-14 | ISO 10628-1:2014 5.4.1 — Type B vertical lettering recommended; legends and designations **shall be upper case** (chemical formulae excepted) | ISO 10628-1:2014 | **V** |
| STD-15 | ISO 10628-1:2014 5.1.1 — A1 should preferably be used | ISO 10628-1:2014 | **V** |
| STD-16 | ISO 81714-1:2010 6.5 grid 1 M, sub-grid 0.1 M **or** 0.125 M (only one per symbol family); 6.6 line-width-to-module = **1:10** | ISO 81714-1:2010 | **V** |
| STD-17 | ISO 128-2 line widths 0.13 / 0.18 / 0.25 / 0.35 / 0.5 / 0.7 / 1 / 1.4 / 2 mm on 1:sqrt(2); extra-wide : wide : narrow = **4:2:1** | ISO 128-2:**2022** (2020 superseded, text identical) | **V** |
| STD-18 | ISO 128-2 5.2 — widths may legally deviate from the series, bounded at +/-0.1 d, provided adjacent lines stay distinguishable | ISO 128-2 | **V** |
| STD-19 | ISO 3098 lettering sizes 1.8 / 2.5 / 3.5 / 5 / 7 / 10 / 14 / 20 mm, derived from ISO 216; stroke-to-height `d = h/10` (type B), `h/14` (type A) | ISO 3098-0 5.3, Tables 1-2 | **V** — but **3098-0:1997 is withdrawn**, superseded by 3098-1:2015 (values unchanged) |
| STD-20 | ISO 14617-1 6.4 module **M = 2.5 mm**; small symbols shown at 200 %; auxiliary grid 0.25 M. 8.2 — a resized symbol **keeps its original line width** | ISO 14617-1:**2005** | **V for 2005 / U for current** — ISO 14617-1:2025 restructures; clauses 6.4 and 8.2 no longer exist |
| STD-21 | ISO 5457 zone fields are 50 mm **measured from the centring marks**, with the remainder added to the corner fields; zone mapping must use the *drawing space*, not the trimmed sheet | ISO 5457:1999 Cl. 4.4, Table 1 | **V** |
| STD-22 | ASME Y14.1 sheet series: A 8.5x11, B 11x17, C 17x22, D 22x34, E 34x44 in | secondary sources only — paywalled | **L** |
| STD-23 | PIP PIC001 4.2.1.2 requires drawing size 22 x 34 in | only an unauthorised copy of a superseded revision was reachable | **L** |
| STD-24 | **No published bubble-diameter-to-text-height ratio exists.** ISA dimensions the bubble but not relative to text; PIP dimensions text but not the bubble | searched; none found | **U** — consequence realised in code: see STD-25 |

---

## DEXPI — information model

| ID | Assumption | Source | C |
|---|---|---|---|
| DEXPI-01 | `PipingNode` is composed by a **`PipingNodeOwner`** (piping component, nozzle), **not** by `PipingNetworkSegment`, which only *references* it via `SourceNode`/`TargetNode` | DEXPI 1.4 reference | **R** |
| DEXPI-02 | `SensingLocation` has **four** subtypes — `Mount`, `Nozzle`, `PipingComponent`, `PipingNetworkSegment` | DEXPI 1.4 reference | **R** |
| DEXPI-03 | `ComponentClassURI` uses **two** namespaces: `data.posccaesar.org/rdl/RDS...` (equipment, piping) and `sandbox.dexpi.org/rdl/...` (instrumentation). **DEXPI 1.4 does not normatively reference ISO 15926** — its References appendix lists only CSS Color 4, CSS Values 4, Proteus Schema, SVG 2 | DEXPI 1.4 spec + References | **R** |
| DEXPI-04 | DEXPI P&ID Specification **1.4** is the current model, free and browsable, serialised as Proteus Schema 4.2.0 | dexpi.org | **V** — but DEXPI 2.0 introduces "DEXPI XML" and **replaces Proteus**; keep serialisation behind an adapter |
| DEXPI-05 | `<Connection>` node indices are zero-based, **index 0 is the `PipingNodeOwner` itself** (real nodes start at 1), and all four attributes are optional | DEXPI 1.4 Proteus implementation | **V** |
| DEXPI-06 | There is **no class named `SignalLine`** — it is `SignalConveyingFunction`, with subclasses `SignalLineFunction` and `MeasuringLineFunction` | DEXPI 1.4 reference | **V** |
| DEXPI-07 | `TaggedPlantItem` defines exactly four fields: `TagName`, `TagNamePrefix`, `TagNameSequenceNumber`, `TagNameSuffix` | DEXPI 1.4 reference | **V** |
| DEXPI-08 | pyDEXPI is **AGPL-3.0** and implements DEXPI **1.3**, not 1.4 | repo LICENSE + README | **V** |

---

## PLAT — platform behaviour

| ID | Assumption | Source | C |
|---|---|---|---|
| PLAT-01 | Render free instance = **0.1 CPU / 512 MB**; **no free** Background Worker, Cron Job or Private Service; free Web Services spin down after 15 min idle (~1 min cold start); ephemeral filesystem, no attachable disk. **Consequence: asynchronous ingestion is impossible on the free tier** | Render compute-plans and free-tier docs | **V** |
| PLAT-02 | RLS is **not** off by default for Dashboard-created tables (it is for SQL/migration-created ones) — and **enabling RLS is insufficient**: default GRANTs to `anon`/`authenticated` persist independently of policies and must be `REVOKE`d | Supabase "Securing your API" | **R** |
| PLAT-03 | PostgREST's **1000-row cap applies to functions**, not only tables and views — a traversal RPC truncates silently | PostgREST / Supabase `max_rows` | **V** |
| PLAT-04 | Free workspace: **750 instance-hours and 500 pipeline (build) minutes** per month | Render Build Pipeline docs | **R** — the plan previously said 750 build minutes |
| PLAT-05 | Supabase direct Postgres is IPv6-only; the Supavisor pooler is the IPv4 path; the IPv4 add-on is **not dual-stack** (it swaps AAAA for A) | Supabase connection docs | **V** |
| PLAT-06 | `LISTEN`/`NOTIFY` through the pooler | no vendor doc found; PgBouncer marks `LISTEN` "Never" under transaction pooling; Supavisor issues open | **U** |
| PLAT-07 | PostgREST cannot execute recursive CTEs directly — wrap in a function and issue `NOTIFY pgrst, 'reload schema'` | reload command **V**; the prohibition is structural, not quotable | **L** |
| PLAT-08 | Render passes a service's env vars into the Docker build as build args **automatically** — a matching `ARG` bakes the secret into an image layer | Render docs | **V** |
| PLAT-09 | Debian trixie renames are **systemic**: `libglib2.0-0` is `libglib2.0-0t64`, `libgl1-mesa-glx` is removed. `python:3.13-slim` currently aliases trixie | packages.debian.org | **V** |
| PLAT-10 | `opencv-python-headless` removes the `libGL.so.1` dependency that `opencv-python` requires | package docs | **V** |
| PLAT-11 | Supabase free projects pause after ~7 days of inactivity | Supabase docs | **V** |
| PLAT-12 | The Supabase CLI cannot be installed via a global npm install | Supabase docs | **V** |
| PLAT-13 | `supabase start` applies `supabase/migrations/` during boot, and a failing migration aborts the boot with an opaque `LegacyDbSetupError` naming no statement. The project's own `migrate --apply` is the recovery path: it names the failing statement | observed on the local stack | **V** |
| PLAT-14 | The local stack's anon/service keys are the same well-known demo JWTs on every machine — they are configuration, not secrets, and may live in an untracked `.env.local` | Supabase CLI behaviour | **V** |

---

## DATA — datasets and licences

| ID | Assumption | Source | C |
|---|---|---|---|
| DATA-01 | PID2Graph: Zenodo DOI `10.5281/zenodo.14803338`, a single ~9.3 GB zip, **CC BY-SA 4.0** (share-alike may attach to derived artefacts), GraphML ground truth, OPEN100 subset = 12 annotated real P&IDs | Zenodo record | **V** |
| DATA-02 | Benchmark protocol and baselines — cite **arXiv:2411.13929 v3 / IEEE DSAA 2025**; the quoted figures are the OPEN100 *Stitched* rows of Table III | paper | **V** |
| DATA-03 | DEXPI TrainingTestCases (gitlab.com/dexpi/TrainingTestCases) is **CC BY 4.0** | GitLab repo | **V** |

---

## Refuted or corrected

The most important section. Each of these was believed, then found wrong.

| ID | Was believed | Correct value |
|---|---|---|
| STD-01 | "`S` in position 2 means Safety when the remaining letters are `V` or `E`" | The gate is on the **first letter** (`F`/`P`/`T`) *and* self-actuated emergency-protective function. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Coding the old rule emits `LSV`, `ASE`, `ZSV` as safety devices. Separately, `Z` — not `S` — is the SIS modifier, and the plan had no `Z` rule at all |
| STD-02 | Kimray's letter table follows ISA-5.1-2009, as its cover states | It is the **1984** table. Consequence: adopting it wholesale leaves the parser with **no concept of SIS tagging** |
| DEXPI-01 | `PipingNetworkSegment` owns its `PipingNode`s | Nodes are composed by a `PipingNodeOwner`; the segment only references them. A segment-owns-node schema will not round-trip |
| DEXPI-02 | `SensingLocation` covers segments and nozzles | It has four subtypes; restricting to two silently drops valid measurements |
| DEXPI-03 | `ComponentClassURI` points at POSC Caesar, anchoring DEXPI to ISO 15926 | Two namespaces are in use, and instrumentation uses `sandbox.dexpi.org`. A POSC-only validation rule rejects every instrument in a valid file. DEXPI 1.4 does not normatively cite ISO 15926 |
| PLAT-02 | "Supabase tables default to RLS off, so remember to enable it" | Wrong for Dashboard tables, and — more dangerously — **enabling RLS is not sufficient**. Default GRANTs persist; `REVOKE` is required |
| PLAT-04 | 750 build minutes per month on the free tier | 750 instance-hours **and 500** pipeline minutes |
| ENG-01 | "Cache only successful OCR reads" | **Refuted by profiling.** Unreadable crops are ~half of a stroke-font drawing, and uncached failures re-ran the engine on the same pixels every invocation — 267 subprocess calls and ~40 s per warm run, forever. Failures are now cached as empty entries: "this crop is unreadable to this engine" is an answer. Warm runs fell from 59 s to 15 s |
| ENG-02 | "Tolerating duplicate objects makes a migration re-runnable" | **Refuted twice in one file.** (a) A statement preceded by its explanatory comment begins with `--` and was silently discarded by a first-line comment test — most of a well-commented migration skipped while the runner reported success. (b) Rolling back the transaction on a duplicate policy discarded every statement already executed (the seed inserts). Correct form: keep comment-prefixed statements, and use a savepoint per statement |
| STD-27 | Grammar-constrained character substitution can repair optical-recognition errors | **Refuted for this project.** The idea works only when the grammar is tight enough to reject nonsense, and ours cannot be: line-number field schemas are company convention with variable arity, so the parser must stay permissive. Measured on the real cache, substitution "repaired" 7 reads and produced `4-14`→`A-14`, `S08`→`508`, `2-D5S`→`Z-05S` — each grammatically valid, each meaningless. **Disabled by default**; despacing (`MV-71 5-01`→`MV-715-01`) is unambiguous and retained |
| STD-26 | A per-glyph shape codebook can replace OCR on a stroke-font drawing | **Refuted, twice and independently.** Measured on the supplied sheets with rotation-sensitive normalisation: **7802 glyph marks produce 1744 distinct signatures, 1243 of them singletons**; the top 40 signatures cover only 61% of marks and the top 200 only 75%. A codebook needs a small closed vocabulary to be worth building, and this tail is real rather than a normalisation defect. Text recognition must therefore render crops and use a real recogniser |
| STD-25 | Text cap height is a module estimator at a ratio of 2 m.u. (ISA) | **Dropped during implementation.** Measured on the sample, the stroke and symbol estimators agreed exactly (module 2.4000 from both) while the text estimator was 60 % adrift. In a stroke font the individual marks include partial glyphs and several text sizes, so the observable is a *mixture*, not a cap height — and per STD-24 no published ratio exists to anchor it. Text height is now measured, reported, and used only as a sanity gate. Render resolution is derived from the **narrow stroke** instead, which is a single well-defined observable |

---

## Uncertain — proceed with a fallback

| ID | Uncertainty | Fallback |
|---|---|---|
| STD-20 | ISO 14617-1 8.2 ("line width is maintained on resize") is verified only against the **2005** edition; the 2025 edition restructured those clauses away | Cite the 2005 edition explicitly by year. The design does not depend on it alone — stroke width is already treated as a *secondary* scale estimator with a sanity gate, and as a *class* signal it is corroborated independently by ISO 10628-1 5.3.1 |
| STD-24 | No published bubble-to-text-height ratio exists | Calibrate the acceptance window empirically per corpus and report it as a measured parameter, never cite it as standard |
| STD-22, STD-23 | ASME Y14.1 and PIP PIC001 are paywalled; only secondary or unauthorised copies were reachable | Do not quote clause numbers in the deliverable. Sheet size is **detected** from geometry, not assumed, so nothing depends on these |
| PLAT-06 | `LISTEN`/`NOTIFY` behaviour through the pooler is undocumented | Do not use it. Use Supabase Realtime or polling for progress signalling |
| PLAT-07 | No quotable prohibition on recursive CTEs via PostgREST | Wrap traversals in functions regardless — required anyway by the row cap (PLAT-03) |
| — | Standards quotes come from a French-language rendering of ISA-5.1-2009 and university-hosted extracts, because ISA/ANSI return 403 to automated fetch | If the conformance claim must be defensible, purchase ANSI/ISA-5.1-2024 plus TR5.1.02/03 and re-verify the letter table, notes 14 and 30, and Table 5.4.4 against the English text. Also assess ISA-TR5.1.04-2026 "Content for PFDs and P&IDs", which is on-topic and unread |

---

## Design choices — not facts

These cannot be verified externally. They are decisions, and are labelled as such rather than dressed
up as findings.

| ID | Choice | Rationale |
|---|---|---|
| DESIGN-01 | Rules decide findings; models only structure prose and write explanations | A compliance-adjacent report must be auditable and reproducible without an API key |
| DESIGN-02 | Synthetic generation is the **primary** quantitative claim; real drawings validate | Only generated data gives exact truth at the topology level, and only it can be varied on purpose |
| DESIGN-03 | The pipeline runs locally; Render hosts the UI only | Forced by PLAT-01 — the free tier cannot run async ingestion |
| DESIGN-04 | A relational graph in Postgres rather than a graph database | One datastore; storage, auth and realtime come free; traversal cost is negligible at this scale |
| DESIGN-05 | No absolute dimensions anywhere — recover the module | Absolute point sizes are plot artifacts (INPUT-07 proves it); ratios are normative (STD-05) |
| DESIGN-06 | Under-claim: confidence propagates as the minimum; absence-based and connectivity-dependent findings are capped | Accusing a correct document of being wrong is the worst output this system can produce |
| DESIGN-07 | Report rejected approaches with their numbers | A negative result with data is stronger evidence of rigour than silence |
| DESIGN-08 | Take Kimray as the base vocabulary and overlay the ISA-2009 additions (notably `Z` to SIS) as a **labelled delta** | Keeps the guide as source of truth for the oil-and-gas abbreviations it uniquely provides, while safety semantics come from the current standard (see STD-02) |
| DESIGN-09 | Real drawings are for validation and threshold calibration, **not** fine-tuning | With a handful of drawings you cannot both fine-tune and validate; fine-tuning destroys the only independent measurement |
| DESIGN-10 | Nameplate design-limit blocks are **not** read from the drawings while OCR reads ~25 % of regions | Attributing a lone pressure value to the wrong vessel is worse than reporting the comparison unresolved — pages carry more than one equipment item, so proximity is not attribution. The report states this instead of hiding it |
| DESIGN-11 | A text region labels **at most one** node, and a labelled node's confidence is `min(geometry, read)` | One tag string annotating both members of a parallel train creates a silent duplicate identity; and a node is only as trustworthy as its weakest input |
| DESIGN-12 | The snapshot API derives sheet dimensions from node extents when serving from the database | The RPC returns nodes and edges only; the UI iterates the page list, and an absent array is a blank screen. Extent-derived dimensions are approximate and only used for the viewport |

---

## Adversarial review — outcome and accepted risks

The whole codebase was reviewed by an adversarial multi-agent pass (2026-08-25): independent
finders per subsystem, each finding then verified by a separate agent prompted to refute it.
**46 findings raised, 41 confirmed, 5 refuted.** Every confirmed correctness finding was fixed the
same day — the criticals were: absence of drawing data treated as a rules conflict (now
`needs_review`, capped severity); the SQL migration runner dropping comment-prefixed statements and
rolling back prior work on a duplicate (now savepoint-per-statement); the database-backed UI path
crashing for want of a derived page list; and port binding accepting near-misses by centre distance
(now an exact segment–bbox slab test — benchmark edge precision moved 45.7 % → 46.2 % with symbol
recall unchanged at 99.4 %, and the real graph shed spurious junction nodes, 584 → 425).

A few confirmed findings are **accepted risks** rather than fixes, recorded here so the acceptance
is a decision with an owner rather than an omission:

| ID | Finding | Why it stands |
|---|---|---|
| RISK-01 | `classify` assigns PIPE before FRAME/GLYPH, so a long stroke inside a table row is a "pipe" until frame exclusion removes it | The order is load-bearing the other way round too: frames are recognised by containing long strokes. Furniture removal happens before assembly, so the misnomer never reaches the graph; renaming mid-pipeline states would touch every stage for zero behavioural change |
| RISK-02 | Colour-cluster logo exclusion uses fixed count (≥50) and area (<8 %) thresholds rather than module units | The thresholds gate a *nomination*, not a deletion, and colour is already a non-normative signal (a drawing colouring lines by service keeps its content because the count gate fails). Module-scaling a mark count is not meaningful |
| RISK-03 | The abstract UI view draws edges centre-to-centre, which can cross unrelated symbols | It is a schematic overlay, not a routing claim; the drawing pane shows true geometry. Routing polylines are stored on edges and a future pane can render them |
| RISK-04 | Off-page connector matching is exact-string; a connector read with one bad character will not join sheets | The alternative — fuzzy joining — manufactures cross-sheet topology from misreads, which is the exact failure mode MAX_SUBSTITUTIONS=0 exists to prevent. An unjoined connector is a visible gap |
| RISK-05 | The synthetic generator draws with one renderer (pymupdf), so domain randomisation does not cover renderer-specific artifacts | Randomisation covers geometry, density, fonts, stroke weight, rotation and noise; a second renderer is future work and the real-drawing validation set covers the gap in practice |
| RISK-06 | `_colour_clusters` is O(n²) single-link clustering | n is the count of *coloured* marks, two orders of magnitude below total primitives on real sheets; measured cost is negligible next to rendering |

New assumptions introduced by the fix batch:

| ID | Assumption | Source / verification |
|---|---|---|
| ENG-03 | mupdf's pixmap ceiling is in **bytes with row padding**, so a pixel-count guard alone still hits `FzErrorLimit: Overly large image` | Observed on synthetic thin-stroke sheets whose derived DPI passed a 400 M-pixel guard and still failed; cap lowered to 120 M pixels (real case: ~67 M) with a fit-to-budget fallback |
| ENG-04 | Recognition is an enrichment: any render or engine failure degrades that page to unread labels and records the error, never aborts extraction | `pipeline.run_page` wraps the render/recognise step; the degraded state is identical to running without a recogniser, which the rest of the pipeline already treats as a gap |

# Assumptions register

Citations and measurements the pipeline stands on. Update in the same commit as the code.

| Prefix | What it covers |
|---|---|
| `INPUT-*` | The supplied test drawings and SOP. Must never become constants in code. |
| `STD-*` | What published standards actually say (ISA, ISO, ASME, PIP). |
| `DEXPI-*` | The DEXPI information model. |
| `PLAT-*` | Docker / Debian / optional Supabase behaviour. |
| `DATA-*` | External datasets and licences. |
| `ENG-*` | Engineering discoveries from profiling. |
| `OCR-*` / `UI-*` | Vector-recognition and interface decisions. |
| `DESIGN-*` | Choices, not facts. |
| `RISK-*` | Confirmed findings we accepted rather than fixed. |

**Confidence:** **V** verified, **L** likely, **U** uncertain, **R** refuted (corrected value given).

**Normative reference.** Input drawings are assumed to follow the convention in the Kimray *How to
Read an Oil & Gas P&ID* guide (not shipped; see [`reference/`](reference/README.md)). Where the
guide is silent we fall back to the standards below. Where the guide and a drawing disagree, the
drawing is reported as non-conformant.

---

## INPUT — measured directly from the supplied files

All **V**, because we measured them rather than inferring them. Everything here describes *one test
case* — the drawings and SOP that shipped with the repo. None of it may appear as a constant in
the code. If a new drawing disagrees with a row below, that is expected: change the drawing, not
the pipeline.

| ID | Assumption | Source |
|---|---|---|
| INPUT-01 | Born-digital CAD vector plot, 3 sheets, ANSI B page box, rotated 270 degrees | measured |
| INPUT-02 | No usable text layer (69 chars/page, a logo footer only) | measured |
| INPUT-03 | 1078 `AutoCAD SHX Text` annotations; the `/Contents` key is **absent**; they cover 93.1 / 84.3 / 78.5 % of black glyph ink | measured |
| INPUT-04 | **No dash arrays** — all 18319 paths report `[] 0`; dashed lines are simulated with runs of short strokes | measured |
| INPUT-05 | Exactly one non-zero stroke width; process pipes are degenerate *filled* rectangles | measured |
| INPUT-06 | 43 instrument circles, all at a single diameter | measured |
| INPUT-07 | Dimensions decode as 0.2 m.u. (stroke) and 7.000 m.u. (bubble) against ISA Table 6.1 / 6.3 | measured + arithmetic |
| INPUT-08 | Every SOP design-limit row agrees with the drawings — the legitimate full-agreement case | measured |
| INPUT-09 | A company logo accounts for roughly 45 % of page-0 paths | measured |
| INPUT-10 | Kimray writes the differential modifier in lower case (`PdI`, `PdS`, `PdSH`) — a third form, matching neither ISA's `PDI` nor the industry's `DPI` | measured |

---

## STD — what the standards actually say

| ID | Assumption | Source | C |
|---|---|---|---|
| STD-01 | `S` means *Safety* only when the first letter is `F`/`P`/`T` **and** the device is a self-actuated emergency-protective element — the set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Everywhere else `S` = *Switch*. `S` must **not** denote SIS; **`Z`** is the SIS variable modifier | ANSI/ISA-5.1-2009 Cl. 4.2 notes 14, 14(d), 30; Table 4.1 | **R** |
| STD-02 | **Kimray's letter table is the ISA-5.1-1984 table**, not 2009, despite what the cover says. The tells: 1984 header structure; `M` modifier = *Momentary*, deleted in 2009; `P` = *Pressure, Vacuum*, shortened in 2009; and **no Safety Instrumented System entry** anywhere | guide p.4, verified directly | **V** |
| STD-03 | The current edition is **ANSI/ISA-5.1-2024**; Annexes A/B moved to ISA-TR5.1.02/03-2024 and are explicitly **nonmandatory guidance** | isa.org ISA-5 series; TR5.1.03-2024 Cl.1 | **V** |
| STD-04 | ISA-5.1-2009 Clause 6 defines dimensions in **measurement units (m.u.)**; 6.2.1 sets a minimum of 1/16 in (0.0625 in) or 1.50 mm; 6.2.2 makes size = shape m.u. times a selected equivalent dimension; Table 6.1 puts the bubble at `7[8]` m.u. | ANSI/ISA-5.1-2009, read directly | **V** |
| STD-05 | 4.1.6 — symbols **must preserve the size ratios** shown in the tables when reduced or enlarged | ANSI/ISA-5.1-2009 | **V** |
| STD-06 | 6.1.5 — traditional minimum device circle is 10.5 mm (7/16 in), optionally 12 mm (1/2 in). Note 4.1.4 says "7/16 in or 11 mm", so the standard is internally inconsistent by roughly 5 % | ANSI/ISA-5.1-2009 | **V** |
| STD-07 | Differential `D` is a Column-2 variable modifier that follows the first letter, so the conformant form is `PDI`/`PDIT`; `DPI`/`DPIT` is a non-conformant industry variant | ANSI/ISA-5.1-2009 Table 4.1, note 11(a) | **V** |
| STD-08 | There are exactly five failure-position codes: `FO`, `FC`, `FL`, `FL/DO`, `FL/DC`. **`FI` is not one of them** | ANSI/ISA-5.1-2009 Table 5.4.4 | **V** |
| STD-09 | Diamond-in-square means "Alternate Choice **or** Safety Instrumented System" in 2009, and programmable logic control only on pre-2009 drawings. **The shape cannot distinguish the two without the legend sheet** | ANSI/ISA-5.1-2009 Intro para 20; Table 5.1.1 headings | **V** |
| STD-10 | Clause 6 is **new in 2009**, so every pre-2009 drawing is dimensionally unconstrained by ISA | ANSI/ISA-5.1-2009 Intro para 16 | **V** |
| STD-11 | Table 6.3: signal line 0.2 m.u., process/equipment line 0.4 m.u.; clearance around a symbol is half the symbol width | notes read directly; numeric values decoded from the table artwork | **L** |
| STD-12 | ISO 10628-1:2014 5.3.1 assigns line width **by object class** against M = 2.5 mm: 1.0 mm (0.4 M) main flow; 0.5 mm (0.2 M) equipment, unit frames, **subsidiary and utility lines**; 0.25 mm (0.1 M) valves, fittings, instrumentation, control/data lines. Anything below 0.25 mm shall not be used | ISO 10628-1:2014 | **V** |
| STD-13 | ISO 10628-1:2014 5.4.2 — lettering is 5 mm for equipment designations and 2.5 mm for other lettering, a 2:1 ratio you can use to separate equipment tags from annotation | ISO 10628-1:2014 | **V** |
| STD-14 | ISO 10628-1:2014 5.4.1 — Type B vertical lettering recommended; legends and designations **shall be upper case**, chemical formulae excepted | ISO 10628-1:2014 | **V** |
| STD-15 | ISO 10628-1:2014 5.1.1 — A1 should preferably be used | ISO 10628-1:2014 | **V** |
| STD-16 | ISO 81714-1:2010 6.5 — grid 1 M, sub-grid 0.1 M **or** 0.125 M (only one per symbol family); 6.6 puts line-width-to-module at **1:10** | ISO 81714-1:2010 | **V** |
| STD-17 | ISO 128-2 line widths run 0.13 / 0.18 / 0.25 / 0.35 / 0.5 / 0.7 / 1 / 1.4 / 2 mm on 1:sqrt(2); extra-wide : wide : narrow = **4:2:1** | ISO 128-2:**2022** (2020 superseded, text identical) | **V** |
| STD-18 | ISO 128-2 5.2 — widths may legally deviate from the series, bounded at +/-0.1 d, as long as adjacent lines stay distinguishable | ISO 128-2 | **V** |
| STD-19 | ISO 3098 lettering sizes are 1.8 / 2.5 / 3.5 / 5 / 7 / 10 / 14 / 20 mm, derived from ISO 216; stroke-to-height is `d = h/10` (type B) or `h/14` (type A) | ISO 3098-0 5.3, Tables 1-2 | **V** — but **3098-0:1997 is withdrawn**, superseded by 3098-1:2015 with values unchanged |
| STD-20 | ISO 14617-1 6.4 — module **M = 2.5 mm**; small symbols shown at 200 %; auxiliary grid 0.25 M. 8.2 — a resized symbol **keeps its original line width** | ISO 14617-1:**2005** | **V for 2005 / U for current** — ISO 14617-1:2025 restructures, and clauses 6.4 and 8.2 no longer exist |
| STD-21 | ISO 5457 zone fields are 50 mm **measured from the centring marks**, with the remainder added to the corner fields; zone mapping has to use the *drawing space*, not the trimmed sheet | ISO 5457:1999 Cl. 4.4, Table 1 | **V** |
| STD-22 | ASME Y14.1 sheet series: A 8.5x11, B 11x17, C 17x22, D 22x34, E 34x44 in | secondary sources only — paywalled | **L** |
| STD-23 | PIP PIC001 4.2.1.2 requires a drawing size of 22 x 34 in | only an unauthorised copy of a superseded revision was reachable | **L** |
| STD-24 | **There is no published bubble-diameter-to-text-height ratio.** ISA dimensions the bubble but not relative to text; PIP dimensions text but not the bubble | searched; found nothing | **U** — the consequence shows up in code: see STD-25 |

---

## DEXPI — the information model

| ID | Assumption | Source | C |
|---|---|---|---|
| DEXPI-01 | `PipingNode` is composed by a **`PipingNodeOwner`** (a piping component, a nozzle), **not** by `PipingNetworkSegment`, which only *references* it via `SourceNode`/`TargetNode` | DEXPI 1.4 reference | **R** |
| DEXPI-02 | `SensingLocation` has **four** subtypes — `Mount`, `Nozzle`, `PipingComponent`, `PipingNetworkSegment` | DEXPI 1.4 reference | **R** |
| DEXPI-03 | `ComponentClassURI` uses **two** namespaces: `data.posccaesar.org/rdl/RDS...` for equipment and piping, and `sandbox.dexpi.org/rdl/...` for instrumentation. **DEXPI 1.4 does not normatively reference ISO 15926** — its References appendix lists only CSS Color 4, CSS Values 4, Proteus Schema and SVG 2 | DEXPI 1.4 spec + References | **R** |
| DEXPI-04 | DEXPI P&ID Specification **1.4** is the current model: free, browsable, serialised as Proteus Schema 4.2.0 | dexpi.org | **V** — but DEXPI 2.0 introduces "DEXPI XML" and **replaces Proteus**, so keep serialisation behind an adapter |
| DEXPI-05 | `<Connection>` node indices are zero-based, **index 0 is the `PipingNodeOwner` itself** (real nodes start at 1), and all four attributes are optional | DEXPI 1.4 Proteus implementation | **V** |
| DEXPI-06 | There is **no class named `SignalLine`** — it is `SignalConveyingFunction`, with subclasses `SignalLineFunction` and `MeasuringLineFunction` | DEXPI 1.4 reference | **V** |
| DEXPI-07 | `TaggedPlantItem` defines exactly four fields: `TagName`, `TagNamePrefix`, `TagNameSequenceNumber`, `TagNameSuffix` | DEXPI 1.4 reference | **V** |
| DEXPI-08 | pyDEXPI is **AGPL-3.0** and implements DEXPI **1.3**, not 1.4 | repo LICENSE + README | **V** |

---

## PLAT — how the platforms actually behave

| ID | Assumption | Source | C |
|---|---|---|---|
| PLAT-02 | RLS is **not** off by default for Dashboard-created tables (it is for tables created by SQL or migrations) — and **enabling RLS is not sufficient on its own**: the default GRANTs to `anon`/`authenticated` persist independently of policies and have to be `REVOKE`d | Supabase "Securing your API" | **R** |
| PLAT-03 | PostgREST's **1000-row cap applies to functions**, not just tables and views — a traversal RPC truncates silently | PostgREST / Supabase `max_rows` | **V** |
| PLAT-05 | Supabase direct Postgres is IPv6-only; the Supavisor pooler is the IPv4 path; and the IPv4 add-on is **not dual-stack** — it swaps AAAA for A | Supabase connection docs | **V** |
| PLAT-06 | `LISTEN`/`NOTIFY` through the pooler | no vendor doc found; PgBouncer marks `LISTEN` "Never" under transaction pooling, and Supavisor has open issues | **U** |
| PLAT-07 | PostgREST cannot execute recursive CTEs directly — you wrap them in a function and issue `NOTIFY pgrst, 'reload schema'` | the reload command is **V**; the prohibition is structural rather than quotable | **L** |
| PLAT-09 | Debian trixie's package renames are **systemic**: `libglib2.0-0` is now `libglib2.0-0t64`, and `libgl1-mesa-glx` is gone. `python:3.13-slim` currently aliases trixie | packages.debian.org | **V** |
| PLAT-11 | Supabase free projects pause after roughly 7 days of inactivity | Supabase docs | **V** |
| PLAT-12 | The Supabase CLI cannot be installed via a global npm install | Supabase docs | **V** |
| PLAT-13 | `supabase start` applies `supabase/migrations/` during boot, and a failing migration aborts the boot with an opaque `LegacyDbSetupError` that names no statement. Our own `migrate --apply` is the recovery path, because it names the failing statement | observed on the local stack | **V** |
| PLAT-14 | The local stack's anon/service keys are the same well-known demo JWTs on every machine — they are configuration rather than secrets, and can live in an untracked `.env.local` | Supabase CLI behaviour | **V** |

---

## DATA — datasets and licences

| ID | Assumption | Source | C |
|---|---|---|---|
| DATA-01 | PID2Graph: Zenodo DOI `10.5281/zenodo.14803338`, a single ~9.3 GB zip, **CC BY-SA 4.0** (share-alike may attach to derived artefacts), GraphML ground truth, OPEN100 subset = 12 annotated real P&IDs | Zenodo record | **V** |
| DATA-02 | For benchmark protocol and baselines, cite **arXiv:2411.13929 v3 / IEEE DSAA 2025**; the figures we quote are the OPEN100 *Stitched* rows of Table III | paper | **V** |
| DATA-03 | DEXPI TrainingTestCases (gitlab.com/dexpi/TrainingTestCases) is **CC BY 4.0** | GitLab repo | **V** |

---

## Refuted or corrected

Read this section first. Each row was believed, then shown to be wrong. Several would have shipped
as defects.

| ID | What we believed | What is actually true |
|---|---|---|
| STD-01 | "`S` in position 2 means Safety when the remaining letters are `V` or `E`" | The gate is on the **first letter** (`F`/`P`/`T`) *and* on the device being a self-actuated emergency-protective element. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Coding the old rule would have emitted `LSV`, `ASE` and `ZSV` as safety devices. Separately, `Z` — not `S` — is the SIS modifier, and our plan had no `Z` rule at all |
| STD-02 | Kimray's letter table follows ISA-5.1-2009, as its cover states | It is the **1984** table. The consequence is serious: adopting it wholesale leaves the parser with **no concept of SIS tagging** |
| DEXPI-01 | `PipingNetworkSegment` owns its `PipingNode`s | Nodes are composed by a `PipingNodeOwner`, and the segment only references them. A segment-owns-node schema will not round-trip |
| DEXPI-02 | `SensingLocation` covers segments and nozzles | It has four subtypes. Restricting it to two silently drops valid measurements |
| DEXPI-03 | `ComponentClassURI` points at POSC Caesar, which anchors DEXPI to ISO 15926 | Two namespaces are in use, and instrumentation uses `sandbox.dexpi.org`. A POSC-only validation rule would reject every instrument in a perfectly valid file. And DEXPI 1.4 does not normatively cite ISO 15926 at all |
| PLAT-02 | "Supabase tables default to RLS off, so remember to enable it" | Wrong for Dashboard tables — and, more dangerously, **enabling RLS is not enough**. The default GRANTs persist, so you also need `REVOKE` |
| ENG-01 | "Cache only successful OCR reads" | **Refuted by profiling.** Unreadable crops are about half of a stroke-font drawing, and leaving failures uncached meant re-running the engine on the same pixels every single invocation — 267 subprocess calls and roughly 40 s per warm run, forever. Failures are now cached as empty entries, because "this crop is unreadable to this engine" is itself an answer. Warm runs went from 59 s to 15 s |
| ENG-02 | "Tolerating duplicate objects makes a migration re-runnable" | **Refuted twice in the same file.** (a) A statement preceded by its explanatory comment starts with `--`, and a first-line comment test silently discarded it — so most of a well-commented migration was skipped while the runner reported success. (b) Rolling back the transaction on a duplicate policy threw away every statement already executed, including the seed inserts. The correct form: keep comment-prefixed statements, and use a savepoint per statement |
| STD-27 | Grammar-constrained character substitution can repair optical-recognition errors | **Refuted for this project.** The idea only works when the grammar is tight enough to reject nonsense, and ours cannot be — line-number field schemas are company convention with variable arity, so the parser has to stay permissive. Measured on the real cache, substitution "repaired" 7 reads and produced `4-14`→`A-14`, `S08`→`508`, `2-D5S`→`Z-05S`: each one grammatically valid, each one meaningless. **Disabled by default.** Despacing (`MV-71 5-01`→`MV-715-01`) is unambiguous, so we kept it |
| STD-26 | A per-glyph shape codebook can replace OCR on a stroke-font drawing | **Refuted twice, independently.** Measured on the supplied sheets with rotation-sensitive normalisation: **7802 glyph marks produce 1744 distinct signatures, 1243 of them singletons**; the top 40 signatures cover only 61 % of marks and the top 200 only 75 %. A codebook is only worth building against a small closed vocabulary, and this tail is real rather than a normalisation defect. So text recognition has to render crops and use a real recogniser |
| STD-25 | Text cap height is a module estimator at a ratio of 2 m.u. (ISA) | **Dropped during implementation.** Measured on the sample, the stroke and symbol estimators agreed exactly — module 2.4000 from both — while the text estimator was 60 % adrift. In a stroke font the individual marks include partial glyphs and several text sizes, so what you are observing is a *mixture*, not a cap height; and per STD-24 there is no published ratio to anchor it against anyway. Text height is now measured, reported, and used only as a sanity gate. Render resolution comes from the **narrow stroke** instead, which is one well-defined observable |

---

## Uncertain — what we do instead

| ID | The uncertainty | What we do about it |
|---|---|---|
| STD-20 | ISO 14617-1 8.2 ("line width is maintained on resize") is verified only against the **2005** edition, and the 2025 edition restructured those clauses away | Cite the 2005 edition explicitly, by year. The design does not hang on it alone: stroke width is already only a *secondary* scale estimator behind a sanity gate, and as a *class* signal it is corroborated independently by ISO 10628-1 5.3.1 |
| STD-24 | No published bubble-to-text-height ratio exists | Calibrate the acceptance window empirically per corpus and report it as a measured parameter. Never cite it as if it were standard |
| STD-22, STD-23 | ASME Y14.1 and PIP PIC001 are paywalled; we could only reach secondary or unauthorised copies | Do not quote clause numbers in the deliverable. Sheet size is **detected** from geometry rather than assumed, so nothing actually depends on these |
| PLAT-06 | `LISTEN`/`NOTIFY` behaviour through the pooler is undocumented | Do not use it. Use Supabase Realtime or polling for progress signalling |
| PLAT-07 | We found no quotable prohibition on recursive CTEs via PostgREST | Wrap traversals in functions anyway — the row cap (PLAT-03) requires it regardless |
| — | Our standards quotes come from a French-language rendering of ISA-5.1-2009 and from university-hosted extracts, because ISA and ANSI return 403 to automated fetch | If the conformance claim ever needs to be defensible, buy ANSI/ISA-5.1-2024 plus TR5.1.02/03 and re-verify the letter table, notes 14 and 30, and Table 5.4.4 against the English text. Also worth assessing ISA-TR5.1.04-2026 "Content for PFDs and P&IDs", which is on-topic and which nobody here has read |

---

## Design choices — decisions, not facts

None of these can be verified against an external source. They are judgement calls, labelled as
such so they are not presented as findings.

| ID | The choice | Why |
|---|---|---|
| DESIGN-01 | Rules decide findings; models only structure prose and write explanations | A report that touches compliance has to be auditable and reproducible by someone who has no API key |
| DESIGN-02 | Synthetic generation is the **primary** quantitative claim; real drawings validate | Only generated data gives exact truth at the topology level, and only generated data can be varied on purpose |
| DESIGN-03 | The pipeline and the UI both run locally | CLI plus files; there is no hosted deploy |
| DESIGN-04 | A relational graph in Postgres rather than a graph database | One datastore, with storage, auth and realtime coming free; traversal cost is negligible at this scale |
| DESIGN-05 | No absolute dimensions anywhere — recover the module instead | Absolute point sizes are plot artifacts (INPUT-07 demonstrates it) while ratios are normative (STD-05) |
| DESIGN-06 | Under-claim: confidence propagates as the minimum, and absence-based and connectivity-dependent findings are capped | Accusing a correct document of being wrong is the worst output this system can produce |
| DESIGN-07 | Report rejected approaches together with their numbers | A negative result with data is stronger evidence of rigour than silence is |
| DESIGN-08 | Take Kimray as the base vocabulary and overlay the ISA-2009 additions (notably `Z` for SIS) as a **labelled delta** | Keeps the guide as our source of truth for the oil-and-gas abbreviations it uniquely provides, while safety semantics come from the current standard (see STD-02) |
| DESIGN-09 | Real drawings are for validation and threshold calibration, **not** fine-tuning | With a handful of drawings you cannot both fine-tune and validate, and fine-tuning destroys the only independent measurement you have |
| DESIGN-10 | Nameplate design-limit blocks are **not** read from the drawings while OCR reads only ~25 % of regions | Attributing a lone pressure value to the wrong vessel is worse than reporting the comparison as unresolved — pages carry more than one equipment item, so proximity is not attribution. The report says so rather than hiding it |
| DESIGN-11 | A text region labels **at most one** node, and a labelled node's confidence is `min(geometry, read)` | One tag string annotating both members of a parallel train creates a silent duplicate identity. And a node is only as trustworthy as its weakest input |
| DESIGN-12 | The snapshot API derives sheet dimensions from node extents when serving from the database | The RPC returns nodes and edges only, while the UI iterates the page list — and an absent array means a blank screen. Extent-derived dimensions are approximate and used only for the viewport |

---

## Accepted risks

Confirmed findings we chose not to fix. Historical port-binding change (edge P 45.7%→46.2%, real graph 584→425 nodes) is past tense — current scores: [`../benchmarks/results.md`](../benchmarks/results.md).

| ID | The finding | Why it stands |
|---|---|---|
| RISK-01 | `classify` assigns PIPE before FRAME/GLYPH, so a long stroke inside a table row counts as a "pipe" until frame exclusion removes it | Frames are recognised by containing long strokes. Furniture removal happens before assembly, so the misnomer never reaches the graph |
| RISK-02 | Colour-cluster logo exclusion uses fixed count (≥50) and area (<8 %) thresholds instead of module units | Nomination gate, not deletion. Colour is non-normative; a drawing that colours lines by service keeps content because the count gate fails |
| RISK-04 | Off-page connector matching is exact-string, so a connector read with one bad character will not join sheets | Fuzzy joining manufactures cross-sheet topology. `MAX_SUBSTITUTIONS=0`. An unjoined connector is a visible gap |
| RISK-05 | The synthetic generator draws with one renderer (pymupdf) | Randomisation covers geometry, density, fonts, stroke, rotation, noise. A second renderer is future work |
| RISK-06 | `_colour_clusters` is O(n²) single-link clustering | `n` is coloured marks, two orders of magnitude below total primitives. Negligible vs rendering |

## ENG

| ID | Assumption | Source / verification |
|---|---|---|
| ENG-03 | mupdf's pixmap ceiling is **bytes with row padding**; a pixel-count guard still hits `FzErrorLimit` | Cap is 120 M pixels (real case ~67 M) with a fit-to-budget fallback |
| ENG-04 | Recognition is an enrichment: render/engine failure degrades to unread labels and never aborts extraction | `pipeline.run_page`. Same state as running with no recogniser |

---

## OCR

Current held-out figures (seeds 500–529, 30/30 scored): [`../benchmarks/results.md`](../benchmarks/results.md). Raster-parameter sweeps plateaued at ~72%; the remaining errors were character confusions on hairline stroke fonts. Vector matching reads the strokes already in hand.

| ID | Assumption / decision | Source and verification |
|---|---|---|
| OCR-01 | Generator renders the recogniser's own stroke alphabet (`recognise/glyphs.py`; `benchmark/strokefont.py` imports it). Density has its own RNG stream (not coupled to module). Truth bboxes use authored tracking; metric gate is 3 modules | Benchmark measures segmentation and matching under size, weight, tracking, shear (±0.08), jitter (0.02 h) — **not** transfer to a foreign font. Transfer is the real drawing only |
| OCR-02 | Confusable families {0 O D Q C G 6}, {1 I}, {8 B}, {5 S}, {2 Z}, {4 A} are not separable by shape at single-stroke weight | Chamfer 0.022 vs 0.023 for a drawn 0 against 0 and D. Grammar + digit prior only inside a ±0.010 tie band |
| OCR-03 | Train and suffix letters exclude I, O and Q | `standards/tags.py` `_TRAIN`. Lets the grammar resolve a trailing O into a 0 |
| OCR-04 | Stroke count is shape evidence: B three strokes, 8 two; 0 one, D two | 0.025 penalty per stroke-count difference |
| OCR-05 | Printed text is periodic and chains like dashes. Dissolving a chain re-emits absorbed real line pieces | Pure glyph-derived chains need ≥15 modules and duty ≥0.35 |
| OCR-06 | Text rows: interval single-link banding, orientation per row. Losing rows re-enter as unclaimed remainder | Fixed-width buckets orphaned by phase; page-level orientation votes fragmented the lone vertical label |
| OCR-07 | A letter-sized multi-stroke SYMBOL near lettering is hypothetically a letter; reading is the test | Unread promotion reverts. Without that, the real drawing lost 157 symbol nodes; with it: 384 nodes / 570 edges |
| OCR-08 | Real-graph delta vs pre-vector baseline (384 vs 425 nodes) is partly de-phantoming | Current classifier: symbol precision **99.8%** [99.1–100] n=623 ([`../benchmarks/results.md`](../benchmarks/results.md)). Real delta has no ground truth |
| OCR-10 | Slant estimate is a hypothesis: read upright and desheared; lower mean character distance wins | A, AA, W, WW, 7, 77, 747, 7A7, V, AV, VA and full tags, upright and 0.08 shear, both orientations |

## UI

| ID | Decision | Why |
|---|---|---|
| UI-01 | Direct manipulation: wheel-zoom, drag-pan, click-inspect, search-jump, findings fly to evidence | One dismissable hint line |
| UI-02 | Supabase path: findings come from the same `graph_snapshot` RPC as the graph. File path: graph from `outputs/<sha256>/graph.nodelink.json`, findings from **root** `outputs/findings.jsonl` (written by `check`, not UI `extract`) | File mode can show findings from a different run |

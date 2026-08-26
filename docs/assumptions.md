# Assumptions register

This file is the citations and measurements the pipeline stands on. When an assumption changes, update it in the same commit as the code. A stale register is worse than none.

A piping and instrumentation diagram is a scaled diagram in a published language. The rows below pin that language down by citation and measurement rather than by treating one plot as a rule.

Three editions of ANSI/ISA-5.1 are in play at once. The Kimray *How to Read an Oil and Gas P&ID* guide is the vocabulary for these oil-and-gas abbreviations — `MV` for a manual valve, equipment class letters, the lower-case differential `PdI` — but its letter table is the 1984 table, not the 2009 edition its cover claims. It still has `M` for Momentary, gives `P` as *Pressure, Vacuum*, and has no Safety Instrumented System entry. The current edition is 2024; annexes A and B moved to technical reports that are explicitly nonmandatory. Kimray is the base table; `Z` (SIS) is overlaid from 2009; annex guidance is not reported as a violation. The guide is not shipped; see [`reference/`](reference/README.md). Where the guide is silent, the standards below apply. Where the guide and a drawing disagree, the drawing is reported as non-conformant.

The module is the other half of the language. ISA-5.1 clause 6 sizes symbols in measurement units and fixes only a minimum (1/16 inch or 1.50 mm). Clause 4.1.6 requires the ratios in the tables to survive scaling. Table 6.1 puts the instrument bubble at 7 (optionally 8) units; Table 6.3 puts a signal line at 0.2 and a process line at 0.4. ISO 81714-1 calls the same quantity M and ties line width to M/10. ISO 10628-1 assigns widths by object class against M = 2.5 mm. On the sample sheets those ratios decode as a module of 2.4 points — a fact about one plot, which is why it must not appear in the code. Text height is not an estimator: there is no published bubble-to-text ratio (PIP dimensions text, ISA dimensions the bubble, neither relative to the other), and on a stroke font the marks are a mixture.

Two letter-table traps are load-bearing. `S` means Safety only for a closed set of self-actuated emergency-protective devices (`FSV`, `PSV`, `TSV`, `PSE`, `TSE`); everywhere else it means Switch. Coding the obvious rule would have emitted `LSV` as a safety device. `Z`, not `S`, is the Safety Instrumented System modifier — and without the 2009 overlay the parser would have had no concept of SIS tagging at all. Industry writes the differential backwards (`DPI`); the standard wants `PDI`; Kimray writes `PdI`. Those forms are normalised and reported.

Classes, where known, are DEXPI 1.4 names (Proteus Schema 4.2.0). DEXPI 2.0 replaces Proteus, so serialisation stays behind an adapter. Several early DEXPI beliefs were wrong: a `PipingNetworkSegment` does not own its nodes, `SensingLocation` has four subtypes not two, and instrumentation class URIs live under `sandbox.dexpi.org`, not POSC Caesar. Those refutations are in the table below because a POSC-only validator would reject every instrument in a valid file.

Read **Refuted or corrected** before proposing a change. Several of those rows would have shipped as defects. The `INPUT-*` rows are measurements on the files in `data/`. If a new drawing disagrees with one, that is expected: change the drawing, not the pipeline.

| Prefix | What it covers |
|---|---|
| `INPUT-*` | Facts measured on the supplied test drawings and procedure. None of these may become constants in the code. |
| `STD-*` | What published standards actually say (ISA, ISO, ASME, PIP). |
| `DEXPI-*` | The DEXPI information model. |
| `PLAT-*` | How Docker, Debian, and optional Supabase actually behave. |
| `DATA-*` | External datasets and licences. |
| `ENG-*` | Engineering discoveries from profiling. |
| `OCR-*` / `UI-*` | Vector-recognition and interface decisions. |
| `DESIGN-*` | Choices, not facts. |
| `RISK-*` | Confirmed findings accepted rather than fixed. |

Confidence is written out: **verified**, **likely**, **uncertain**, or **refuted** (with the corrected value given).

---

## INPUT — measured directly from the supplied files

Every row here is verified by direct measurement rather than inference. Everything describes one test case: the drawings and procedure that shipped with the repository. None of it may appear as a constant in the code. If a new drawing disagrees with a row below, that is expected. Change the drawing, not the pipeline.

| ID | Assumption | Source |
|---|---|---|
| INPUT-01 | The plot is a born-digital CAD vector drawing on three sheets, with an ANSI B page box, rotated 270 degrees. | measured |
| INPUT-02 | There is no usable text layer: about 69 characters per page, a logo footer only. | measured |
| INPUT-03 | There are 1078 `AutoCAD SHX Text` annotations. The `/Contents` key is absent. They cover 93.1, 84.3, and 78.5 percent of black glyph ink on the three sheets. | measured |
| INPUT-04 | There are no dash arrays. All 18319 paths report `[] 0`. Dashed lines are simulated with runs of short strokes. | measured |
| INPUT-05 | Exactly one non-zero stroke width is used. Process pipes are degenerate filled rectangles. | measured |
| INPUT-06 | There are 43 instrument circles, all at a single diameter. | measured |
| INPUT-07 | Against ISA Tables 6.1 and 6.3, those dimensions decode as 0.2 measurement units for the stroke and 7.000 measurement units for the bubble. | measured + arithmetic |
| INPUT-08 | Every design-limit row in the procedure agrees with the drawings. That is the legitimate full-agreement case. | measured |
| INPUT-09 | A company logo accounts for roughly 45 percent of the paths on page 0. | measured |
| INPUT-10 | Kimray writes the differential modifier in lower case (`PdI`, `PdS`, `PdSH`). That is a third form, matching neither ISA’s `PDI` nor the industry’s `DPI`. | measured |

---

## STD — what the standards actually say

ISA dimensions below are in measurement units: a relative size, not millimetres, until a plot scale is chosen.

| ID | Assumption | Source | Confidence |
|---|---|---|---|
| STD-01 | `S` means Safety only when the first letter is `F`, `P`, or `T` and the device is a self-actuated emergency-protective element. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Everywhere else `S` means Switch. `S` must not denote a Safety Instrumented System; `Z` is that variable modifier. | ANSI/ISA-5.1-2009 Cl. 4.2 notes 14, 14(d), 30; Table 4.1 | refuted |
| STD-02 | Kimray’s letter table is the ISA-5.1-1984 table, not 2009, despite what the cover says. The tells are the 1984 header structure, `M` as Momentary (deleted in 2009), `P` as Pressure, Vacuum (shortened in 2009), and no Safety Instrumented System entry anywhere. | guide p.4, verified directly | verified |
| STD-03 | The current edition is ANSI/ISA-5.1-2024. Annexes A and B moved to ISA-TR5.1.02/03-2024 and are explicitly nonmandatory guidance. | isa.org ISA-5 series; TR5.1.03-2024 Cl.1 | verified |
| STD-04 | ISA-5.1-2009 Clause 6 defines dimensions in measurement units. Clause 6.2.1 sets a minimum of 1/16 inch (0.0625 in) or 1.50 mm. Clause 6.2.2 makes size equal to shape measurement units times a selected equivalent dimension. Table 6.1 puts the bubble at 7[8] measurement units. | ANSI/ISA-5.1-2009, read directly | verified |
| STD-05 | Clause 4.1.6: symbols must preserve the size ratios shown in the tables when reduced or enlarged. | ANSI/ISA-5.1-2009 | verified |
| STD-06 | Clause 6.1.5: the traditional minimum device circle is 10.5 mm (7/16 in), optionally 12 mm (1/2 in). Note 4.1.4 says “7/16 in or 11 mm”, so the standard is internally inconsistent by roughly 5 percent. | ANSI/ISA-5.1-2009 | verified |
| STD-07 | Differential `D` is a Column-2 variable modifier that follows the first letter, so the conformant form is `PDI` / `PDIT`. `DPI` / `DPIT` is a non-conformant industry variant. | ANSI/ISA-5.1-2009 Table 4.1, note 11(a) | verified |
| STD-08 | There are exactly five failure-position codes: `FO`, `FC`, `FL`, `FL/DO`, `FL/DC`. `FI` is not one of them. | ANSI/ISA-5.1-2009 Table 5.4.4 | verified |
| STD-09 | Diamond-in-square means “Alternate Choice or Safety Instrumented System” in 2009, and programmable logic control only on pre-2009 drawings. The shape cannot distinguish the two without the legend sheet. | ANSI/ISA-5.1-2009 Intro para 20; Table 5.1.1 headings | verified |
| STD-10 | Clause 6 is new in 2009, so every pre-2009 drawing is dimensionally unconstrained by ISA. | ANSI/ISA-5.1-2009 Intro para 16 | verified |
| STD-11 | Table 6.3: a signal line is 0.2 measurement units, a process or equipment line is 0.4, and clearance around a symbol is half the symbol width. | notes read directly; numeric values decoded from the table artwork | likely |
| STD-12 | ISO 10628-1:2014 5.3.1 assigns line width by object class against M = 2.5 mm: 1.0 mm (0.4 M) main flow; 0.5 mm (0.2 M) equipment, unit frames, subsidiary and utility lines; 0.25 mm (0.1 M) valves, fittings, instrumentation, control and data lines. Anything below 0.25 mm shall not be used. | ISO 10628-1:2014 | verified |
| STD-13 | ISO 10628-1:2014 5.4.2: lettering is 5 mm for equipment designations and 2.5 mm for other lettering, a 2:1 ratio that can separate equipment tags from annotation. | ISO 10628-1:2014 | verified |
| STD-14 | ISO 10628-1:2014 5.4.1 recommends Type B vertical lettering. Legends and designations shall be upper case, chemical formulae excepted. | ISO 10628-1:2014 | verified |
| STD-15 | ISO 10628-1:2014 5.1.1: A1 should preferably be used. | ISO 10628-1:2014 | verified |
| STD-16 | ISO 81714-1:2010 6.5: grid 1 M, sub-grid 0.1 M or 0.125 M (only one per symbol family). Clause 6.6 puts line-width-to-module at 1:10. | ISO 81714-1:2010 | verified |
| STD-17 | ISO 128-2 line widths run 0.13 / 0.18 / 0.25 / 0.35 / 0.5 / 0.7 / 1 / 1.4 / 2 mm on a 1:sqrt(2) series. Extra-wide : wide : narrow is 4:2:1. The 2022 text is the current one; 2020 is superseded with identical wording. | ISO 128-2:2022 | verified |
| STD-18 | ISO 128-2 5.2: widths may legally deviate from the series, bounded at plus or minus 0.1 d, as long as adjacent lines stay distinguishable. | ISO 128-2 | verified |
| STD-19 | ISO 3098 lettering sizes are 1.8 / 2.5 / 3.5 / 5 / 7 / 10 / 14 / 20 mm, derived from ISO 216. Stroke-to-height is d = h/10 (type B) or h/14 (type A). ISO 3098-0:1997 is withdrawn; 3098-1:2015 supersedes it with the values unchanged. | ISO 3098-0 5.3, Tables 1-2 | verified |
| STD-20 | ISO 14617-1:2005 6.4 sets the module M = 2.5 mm, shows small symbols at 200 percent, and uses an auxiliary grid of 0.25 M. Clause 8.2 says a resized symbol keeps its original line width. The 2025 edition restructures those clauses away, so this is verified for 2005 and uncertain for the current edition. | ISO 14617-1:2005 | verified for 2005 / uncertain for current |
| STD-21 | ISO 5457 zone fields are 50 mm measured from the centring marks, with the remainder added to the corner fields. Zone mapping has to use the drawing space, not the trimmed sheet. | ISO 5457:1999 Cl. 4.4, Table 1 | verified |
| STD-22 | ASME Y14.1 sheet series: A 8.5 by 11, B 11 by 17, C 17 by 22, D 22 by 34, E 34 by 44 inches. Only secondary sources were reachable; the standard is paywalled. | secondary sources | likely |
| STD-23 | PIP PIC001 4.2.1.2 requires a drawing size of 22 by 34 inches. Only an unauthorised copy of a superseded revision was reachable. | unauthorised copy of a superseded revision | likely |
| STD-24 | There is no published bubble-diameter-to-text-height ratio. ISA dimensions the bubble but not relative to text; PIP dimensions text but not the bubble. The consequence in code is STD-25. | searched; found nothing | uncertain |

---

## DEXPI — the information model

| ID | Assumption | Source | Confidence |
|---|---|---|---|
| DEXPI-01 | A `PipingNode` is composed by a `PipingNodeOwner` (a piping component, a nozzle), not by `PipingNetworkSegment`. The segment only references it via `SourceNode` / `TargetNode`. | DEXPI 1.4 reference | refuted |
| DEXPI-02 | `SensingLocation` has four subtypes: `Mount`, `Nozzle`, `PipingComponent`, `PipingNetworkSegment`. | DEXPI 1.4 reference | refuted |
| DEXPI-03 | `ComponentClassURI` uses two namespaces: `data.posccaesar.org/rdl/RDS...` for equipment and piping, and `sandbox.dexpi.org/rdl/...` for instrumentation. DEXPI 1.4 does not normatively reference ISO 15926. Its References appendix lists only CSS Color 4, CSS Values 4, Proteus Schema, and SVG 2. | DEXPI 1.4 spec + References | refuted |
| DEXPI-04 | DEXPI P&ID Specification 1.4 is the model implemented against: free, browsable, serialised as Proteus Schema 4.2.0. DEXPI 2.0 introduces “DEXPI XML” and replaces Proteus, so serialisation stays behind an adapter. | dexpi.org | verified |
| DEXPI-05 | `<Connection>` node indices are zero-based. Index 0 is the `PipingNodeOwner` itself (real nodes start at 1), and all four attributes are optional. | DEXPI 1.4 Proteus implementation | verified |
| DEXPI-06 | There is no class named `SignalLine`. The class is `SignalConveyingFunction`, with subclasses `SignalLineFunction` and `MeasuringLineFunction`. | DEXPI 1.4 reference | verified |
| DEXPI-07 | `TaggedPlantItem` defines exactly four fields: `TagName`, `TagNamePrefix`, `TagNameSequenceNumber`, `TagNameSuffix`. | DEXPI 1.4 reference | verified |
| DEXPI-08 | pyDEXPI is AGPL-3.0 and implements DEXPI 1.3, not 1.4. | repo LICENSE + README | verified |

---

## PLAT — how the platforms actually behave

| ID | Assumption | Source | Confidence |
|---|---|---|---|
| PLAT-02 | Row Level Security is not off by default for Dashboard-created tables (it is for tables created by SQL or migrations). Enabling it is not sufficient on its own: the default GRANTs to `anon` / `authenticated` persist independently of policies and have to be REVOKEd. | Supabase “Securing your API” | refuted |
| PLAT-03 | PostgREST’s 1000-row cap applies to functions, not just tables and views. A traversal RPC truncates silently. | PostgREST / Supabase `max_rows` | verified |
| PLAT-05 | Supabase direct Postgres is IPv6-only. The Supavisor pooler is the IPv4 path. The IPv4 add-on is not dual-stack: it swaps AAAA for A. | Supabase connection docs | verified |
| PLAT-06 | `LISTEN` / `NOTIFY` through the pooler is undocumented. PgBouncer marks `LISTEN` “Never” under transaction pooling, and Supavisor has open issues. | no vendor doc found | uncertain |
| PLAT-07 | PostgREST cannot execute recursive CTEs directly. They are wrapped in a function and issued with `NOTIFY pgrst, 'reload schema'`. The reload command is verified; the prohibition is structural rather than quotable. | structural | likely |
| PLAT-09 | Debian trixie’s package renames are systemic: `libglib2.0-0` is now `libglib2.0-0t64`, and `libgl1-mesa-glx` is gone. `python:3.13-slim` currently aliases trixie. | packages.debian.org | verified |
| PLAT-11 | Supabase free projects pause after roughly seven days of inactivity. | Supabase docs | verified |
| PLAT-12 | The Supabase CLI cannot be installed via a global npm install. | Supabase docs | verified |
| PLAT-13 | `supabase start` applies `supabase/migrations/` during boot. A failing migration aborts the boot with an opaque `LegacyDbSetupError` that names no statement. `migrate --apply` is the recovery path, because it names the failing statement. | observed on the local stack | verified |
| PLAT-14 | The local stack’s anon and service keys are the same well-known demo JWTs on every machine. They are configuration rather than secrets, and can live in an untracked `.env.local`. | Supabase CLI behaviour | verified |

---

## DATA — datasets and licences

| ID | Assumption | Source | Confidence |
|---|---|---|---|
| DATA-01 | PID2Graph is Zenodo DOI `10.5281/zenodo.14803338`, a single roughly 9.3 GB zip, CC BY-SA 4.0 (share-alike may attach to derived artefacts), GraphML ground truth. The OPEN100 subset is 12 annotated real piping and instrumentation diagrams. | Zenodo record | verified |
| DATA-02 | For benchmark protocol and baselines, cite arXiv:2411.13929 v3 / IEEE DSAA 2025. The figures quoted are the OPEN100 Stitched rows of Table III. | paper | verified |
| DATA-03 | DEXPI TrainingTestCases (gitlab.com/dexpi/TrainingTestCases) is CC BY 4.0. | GitLab repo | verified |

---

## Refuted or corrected

Read this section first. Each row was believed, then shown to be wrong. Several would have shipped as defects.

| ID | Prior belief | What is actually true |
|---|---|---|
| STD-01 | “`S` in position 2 means Safety when the remaining letters are `V` or `E`.” | The gate is on the first letter (`F` / `P` / `T`) and on the device being a self-actuated emergency-protective element. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Coding the old rule would have emitted `LSV`, `ASE` and `ZSV` as safety devices. Separately, `Z` — not `S` — is the Safety Instrumented System modifier, and the original design had no `Z` rule at all. |
| STD-02 | Kimray’s letter table follows ISA-5.1-2009, as its cover states. | It is the 1984 table. Adopting it wholesale leaves the parser with no concept of Safety Instrumented System tagging. |
| DEXPI-01 | `PipingNetworkSegment` owns its `PipingNode`s. | Nodes are composed by a `PipingNodeOwner`, and the segment only references them. A segment-owns-node schema will not round-trip. |
| DEXPI-02 | `SensingLocation` covers segments and nozzles. | It has four subtypes. Restricting it to two silently drops valid measurements. |
| DEXPI-03 | `ComponentClassURI` points at POSC Caesar, which anchors DEXPI to ISO 15926. | Two namespaces are in use, and instrumentation uses `sandbox.dexpi.org`. A POSC-only validation rule would reject every instrument in a perfectly valid file. DEXPI 1.4 does not normatively cite ISO 15926 at all. |
| PLAT-02 | “Supabase tables default to Row Level Security off, so remember to enable it.” | Wrong for Dashboard tables. More dangerously, enabling Row Level Security is not enough. The default GRANTs persist, so REVOKE is also required. |
| ENG-01 | Cache only successful OCR reads. | Refuted by profiling. Unreadable crops are about half of a stroke-font drawing, and leaving failures uncached meant re-running the engine on the same pixels every invocation: 267 subprocess calls and roughly 40 seconds per warm run, forever. Failures are now cached as empty entries, because “this crop is unreadable to this engine” is itself an answer. Warm runs went from 59 seconds to 15 seconds. |
| ENG-02 | Tolerating duplicate objects makes a migration re-runnable. | Refuted twice in the same file. A statement preceded by its explanatory comment starts with `--`, and a first-line comment test silently discarded it, so most of a well-commented migration was skipped while the runner reported success. Rolling back the transaction on a duplicate policy threw away every statement already executed, including the seed inserts. The correct form: keep comment-prefixed statements, and use a savepoint per statement. |
| STD-27 | Grammar-constrained character substitution can repair optical-recognition errors. | Refuted for this project. The idea only works when the grammar is tight enough to reject nonsense, and the ISA tag grammar cannot be: line-number field schemas are company convention with variable arity, so the parser has to stay permissive. Measured on the real cache, substitution “repaired” 7 reads and produced `4-14`→`A-14`, `S08`→`508`, `2-D5S`→`Z-05S`: each one grammatically valid, each one meaningless. Substitution is disabled by default. Despacing (`MV-71 5-01`→`MV-715-01`) is unambiguous and remains. |
| STD-26 | A per-glyph shape codebook can replace OCR on a stroke-font drawing. | Refuted twice, independently. Measured on the supplied sheets with rotation-sensitive normalisation: 7802 glyph marks produce 1744 distinct signatures, 1243 of them singletons. The top 40 signatures cover only 61 percent of marks and the top 200 only 75 percent. A codebook is only worth building against a small closed vocabulary, and this tail is real rather than a normalisation defect. Text recognition has to render crops and use a real recogniser. |
| STD-25 | Text cap height is a module estimator at a ratio of 2 measurement units (ISA). | Dropped during implementation. Measured on the sample, the stroke and symbol estimators agreed exactly — module 2.4000 from both — while the text estimator was 60 percent adrift. In a stroke font the individual marks include partial glyphs and several text sizes, so the observable is a mixture, not a cap height. Per STD-24 there is no published ratio to anchor it against anyway. Text height is now measured, reported, and used only as a sanity gate. Render resolution comes from the narrow stroke instead, which is one well-defined observable. |

---

## Uncertain — residual practice

| ID | The uncertainty | Treatment |
|---|---|---|
| STD-20 | ISO 14617-1 8.2 (“line width is maintained on resize”) is verified only against the 2005 edition, and the 2025 edition restructured those clauses away. | Cite the 2005 edition explicitly, by year. The design does not hang on it alone: stroke width is already only a secondary scale estimator behind a sanity gate, and as a class signal it is corroborated independently by ISO 10628-1 5.3.1. |
| STD-24 | No published bubble-to-text-height ratio exists. | Calibrate the acceptance window empirically per corpus and report it as a measured parameter. Never cite it as if it were standard. |
| STD-22, STD-23 | ASME Y14.1 and PIP PIC001 are paywalled. Only secondary or unauthorised copies were reachable. | Do not quote clause numbers in the deliverable. Sheet size is detected from geometry rather than assumed, so nothing actually depends on these. |
| PLAT-06 | `LISTEN` / `NOTIFY` behaviour through the pooler is undocumented. | Do not use it. Use Supabase Realtime or polling for progress signalling. |
| PLAT-07 | No quotable prohibition on recursive CTEs via PostgREST was found. | Wrap traversals in functions anyway. The row cap (PLAT-03) requires it regardless. |
| — | Standards quotes come from a French-language rendering of ISA-5.1-2009 and from university-hosted extracts, because ISA and ANSI return 403 to automated fetch. | If the conformance claim ever needs to be defensible, buy ANSI/ISA-5.1-2024 plus TR5.1.02/03 and re-verify the letter table, notes 14 and 30, and Table 5.4.4 against the English text. ISA-TR5.1.04-2026 “Content for PFDs and P&IDs” is on-topic and has not been consulted. |

---

## Design choices — decisions, not facts

None of these can be verified against an external source. They are judgement calls, labelled as such so they are not presented as findings.

| ID | The choice | Why |
|---|---|---|
| DESIGN-01 | Rules decide findings. Models only structure prose and write explanations. | A report that touches compliance has to be auditable and reproducible by someone who has no API key. |
| DESIGN-02 | Synthetic generation is the primary quantitative claim. Real drawings validate. | Only generated data gives exact truth at the topology level, and only generated data can be varied on purpose. |
| DESIGN-03 | The pipeline and the UI both run locally. | The work is a command line plus files. There is no hosted deploy. |
| DESIGN-04 | A relational graph in Postgres rather than a graph database. | One datastore, with storage, auth and realtime coming free. Traversal cost is negligible at this scale. |
| DESIGN-05 | No absolute dimensions anywhere. Recover the module instead. | Absolute point sizes are plot artifacts (INPUT-07 demonstrates it) while ratios are normative (STD-05). |
| DESIGN-06 | Under-claim: confidence propagates as the minimum, and absence-based and connectivity-dependent findings are capped. | Accusing a correct document of being wrong is the worst output this system can produce. |
| DESIGN-07 | Report rejected approaches together with their numbers. | A negative result with data is stronger evidence of rigour than silence is. |
| DESIGN-08 | Take Kimray as the base vocabulary and overlay the ISA-2009 additions (notably `Z` for Safety Instrumented System) as a labelled delta. | Keeps the guide as the source of truth for the oil-and-gas abbreviations it uniquely provides, while safety semantics come from the current standard (see STD-02). |
| DESIGN-09 | Real drawings are for validation and threshold calibration, not fine-tuning. | With a handful of drawings, fine-tuning and validation cannot both be done, and fine-tuning destroys the only independent measurement available. |
| DESIGN-10 | Nameplate design-limit blocks are not read from the drawings while OCR reads only about a quarter of regions. | Attributing a lone pressure value to the wrong vessel is worse than reporting the comparison as unresolved. Pages carry more than one equipment item, so proximity is not attribution. The report says so rather than hiding it. |
| DESIGN-11 | A text region labels at most one node, and a labelled node’s confidence is the minimum of geometry and read. | One tag string annotating both members of a parallel train creates a silent duplicate identity. A node is only as trustworthy as its weakest input. |
| DESIGN-12 | The snapshot API derives sheet dimensions from node extents when serving from the database. | The RPC returns nodes and edges only, while the UI iterates the page list, and an absent array means a blank screen. Extent-derived dimensions are approximate and used only for the viewport. |

---

## Accepted risks

These are confirmed findings left unfixed. A historical port-binding change moved edge precision from 45.7 percent to 46.2 percent and the real graph from 584 nodes to 425. That is past tense. Current scores are in [`../benchmarks/results.md`](../benchmarks/results.md).

| ID | The finding | Why it stands |
|---|---|---|
| RISK-01 | `classify` assigns PIPE before FRAME/GLYPH, so a long stroke inside a table row counts as a “pipe” until frame exclusion removes it. | Frames are recognised by containing long strokes. Furniture removal happens before assembly, so the misnomer never reaches the graph. |
| RISK-02 | Colour-cluster logo exclusion uses fixed count (50 or more) and area (under 8 percent) thresholds instead of module units. | Those thresholds gate a nomination, not a deletion. Colour is already a non-normative signal. A drawing that colours lines by service keeps its content because the count gate fails. |
| RISK-04 | Off-page connector matching is exact-string, so a connector read with one bad character will not join sheets. | Fuzzy joining manufactures cross-sheet topology out of misreads, which is the failure mode `MAX_SUBSTITUTIONS=0` exists to prevent. An unjoined connector is a visible gap. |
| RISK-05 | The synthetic generator draws with one renderer (PyMuPDF), so domain randomisation does not cover renderer-specific artifacts. | Randomisation already covers geometry, density, fonts, stroke, rotation, and noise. A second renderer is future work. |
| RISK-06 | `_colour_clusters` is quadratic single-link clustering. | The count here is coloured marks, two orders of magnitude below total primitives on real sheets. Measured cost is negligible next to rendering. |

## Engineering notes

| ID | Assumption | Source / verification |
|---|---|---|
| ENG-03 | MuPDF’s pixmap ceiling is expressed in bytes with row padding, so a pixel-count guard on its own still hits `FzErrorLimit`. | The cap is 120 million pixels (the real case is around 67 million) with a fit-to-budget fallback. |
| ENG-04 | Recognition is an enrichment. Any render or engine failure degrades that page to unread labels, records the error, and never aborts extraction. | `pipeline.run_page` wraps the step. The degraded state is the same as running with no recogniser at all. |

---

## Lettering

Current held-out figures (seeds 500–529, all 30 scored) live in [`../benchmarks/results.md`](../benchmarks/results.md). Raster-parameter sweeps plateaued at about 72 percent. The remaining errors were character confusions on hairline stroke fonts. Vector matching reads the strokes already in hand.

| ID | Assumption / decision | Source and verification |
|---|---|---|
| OCR-01 | The generator renders the recogniser’s own stroke alphabet (`recognise/glyphs.py`; `benchmark/strokefont.py` imports it). Density has its own random stream, not coupled to the module. Truth boxes use authored tracking. The metric gate is 3 modules. | The benchmark measures segmentation and matching under size, weight, tracking, shear of plus or minus 0.08, and jitter of 0.02 of height. It is not transfer to a foreign font. Transfer is measured only on the real drawing. |
| OCR-02 | The confusable families {0 O D Q C G 6}, {1 I}, {8 B}, {5 S}, {2 Z}, {4 A} are not separable by shape at single-stroke weight. | Chamfer distance 0.022 versus 0.023 for a drawn 0 against the 0 and D templates. Grammar plus a digit prior apply only inside a plus-or-minus 0.010 tie band. |
| OCR-03 | Train and suffix letters exclude I, O, and Q. | Encoded in `standards/tags.py` (`_TRAIN`). That is also what lets the grammar resolve a trailing O into a 0. |
| OCR-04 | Stroke count is shape evidence: B is three strokes and 8 is two; 0 is one and D is two. | A 0.025 penalty per stroke-count difference separates what point distance cannot. |
| OCR-05 | Printed text is periodic and chains like dashes. Dissolving a chain re-emits absorbed real line pieces. | Pure glyph-derived chains need at least 15 modules and duty of at least 0.35. |
| OCR-06 | Text rows are found by interval single-link banding, with orientation chosen per row. Losing rows re-enter as their unclaimed remainder. | Fixed-width buckets orphaned marks by phase. Page-level orientation votes fragmented the lone vertical label on a horizontal page. |
| OCR-07 | A letter-sized multi-stroke SYMBOL near lettering is hypothetically a letter, and reading it is the test. | Unread promotion is reverted. Without that, the real drawing lost 157 symbol nodes. With it, the real graph is 384 nodes and 570 edges. |
| OCR-08 | The remaining real-graph delta against the pre-vector baseline (384 versus 425 nodes) is partly de-phantoming. | The current classifier’s symbol precision is 99.8 percent [99.1–100] on 623 instances ([`../benchmarks/results.md`](../benchmarks/results.md)). The real delta has no ground truth. |
| OCR-10 | The slant estimate is a hypothesis: read upright and desheared, and the lower mean character distance wins. | A, AA, W, WW, 7, 77, 747, 7A7, V, AV, VA and full tags, upright and at 0.08 shear, both orientations. |

## Interface

| ID | Decision | Why |
|---|---|---|
| UI-01 | Direct manipulation: wheel-zoom, drag-pan, click-inspect, search-jump, and findings that fly to their evidence. | The only instructional text is a single dismissable hint line. |
| UI-02 | On the Supabase path, findings come from the same `graph_snapshot` call as the graph. On the file path, the graph comes from `outputs/<sha256>/graph.nodelink.json` and findings from the root `outputs/findings.jsonl`, which is written by `check`, not by the UI extract. | File mode can show findings from a different run than the drawing on screen. |

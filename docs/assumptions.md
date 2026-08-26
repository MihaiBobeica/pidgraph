# Assumptions register

This file is what extraction, tag parsing, findings, and the held-out claim stand on. A row belongs here only if, were it false, one of those would change. When an assumption changes, update it in the same commit as the code. A stale register is worse than none.

The Kimray *How to Read an Oil and Gas P&ID* guide is the vocabulary for these oil-and-gas abbreviations. It is not shipped; see [`reference/`](reference/README.md). Kimray’s letter table is the 1984 ISA table, not the 2009 edition its cover claims (STD-02). The current edition is 2024; annexes are nonmandatory (STD-03). `Z` (Safety Instrumented System) is overlaid from 2009 (DESIGN-08). Where the guide is silent, the standards below apply. Where the guide and a drawing disagree, the drawing is reported as non-conformant.

Rejected alternatives live in [`tradeoffs.md`](tradeoffs.md). Docker, Debian, and optional Postgres live in [`architecture.md`](architecture.md). How the scores were produced lives in [`../benchmarks/results.md`](../benchmarks/results.md).

Confidence is **verified**, **likely**, or **uncertain**. Corrected prior beliefs are in **Corrections**, not marked refuted in the table of current rules.

---

## Standards the parser and calibrator use

ISA dimensions are in measurement units: a relative size, not millimetres, until a plot scale is chosen. Absolute point sizes are plot artifacts; ratios are normative (STD-05). The module is recovered rather than hardcoded.

| ID | Assumption | Source | Confidence |
|---|---|---|---|
| STD-01 | `S` means Safety only when the first letter is `F`, `P`, or `T` and the device is a self-actuated emergency-protective element. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. Everywhere else `S` means Switch. `S` must not denote a Safety Instrumented System; `Z` is that variable modifier. | ANSI/ISA-5.1-2009 Cl. 4.2 notes 14, 14(d), 30; Table 4.1 | verified |
| STD-02 | Kimray’s letter table is the ISA-5.1-1984 table, not 2009, despite what the cover says. The tells are the 1984 header structure, `M` as Momentary (deleted in 2009), `P` as Pressure, Vacuum (shortened in 2009), and no Safety Instrumented System entry anywhere. | guide p.4, verified directly | verified |
| STD-03 | The current edition is ANSI/ISA-5.1-2024. Annexes A and B moved to ISA-TR5.1.02/03-2024 and are explicitly nonmandatory guidance. | isa.org ISA-5 series; TR5.1.03-2024 Cl.1 | verified |
| STD-04 | ISA-5.1-2009 Clause 6 defines dimensions in measurement units. Clause 6.2.1 sets a minimum of 1/16 inch (0.0625 in) or 1.50 mm. Clause 6.2.2 makes size equal to shape measurement units times a selected equivalent dimension. Table 6.1 puts the bubble at 7[8] measurement units. | ANSI/ISA-5.1-2009, read directly | verified |
| STD-05 | Clause 4.1.6: symbols must preserve the size ratios shown in the tables when reduced or enlarged. | ANSI/ISA-5.1-2009 | verified |
| STD-07 | Differential `D` is a Column-2 variable modifier that follows the first letter, so the conformant form is `PDI` / `PDIT`. `DPI` / `DPIT` is a non-conformant industry variant. | ANSI/ISA-5.1-2009 Table 4.1, note 11(a) | verified |
| STD-08 | There are exactly five failure-position codes: `FO`, `FC`, `FL`, `FL/DO`, `FL/DC`. `FI` is not one of them. | ANSI/ISA-5.1-2009 Table 5.4.4 | verified |
| STD-09 | Diamond-in-square means “Alternate Choice or Safety Instrumented System” in 2009, and programmable logic control only on pre-2009 drawings. The shape cannot distinguish the two without the legend sheet. | ANSI/ISA-5.1-2009 Intro para 20; Table 5.1.1 headings | verified |
| STD-10 | Clause 6 is new in 2009, so every pre-2009 drawing is dimensionally unconstrained by ISA. | ANSI/ISA-5.1-2009 Intro para 16 | verified |
| STD-11 | Table 6.3: a signal line is 0.2 measurement units, a process or equipment line is 0.4, and clearance around a symbol is half the symbol width. | notes read directly; numeric values decoded from the table artwork | likely |
| STD-12 | ISO 10628-1:2014 5.3.1 assigns line width by object class against M = 2.5 mm: 1.0 mm (0.4 M) main flow; 0.5 mm (0.2 M) equipment, unit frames, subsidiary and utility lines; 0.25 mm (0.1 M) valves, fittings, instrumentation, control and data lines. Anything below 0.25 mm shall not be used. | ISO 10628-1:2014 | verified |
| STD-16 | ISO 81714-1:2010 6.5: grid 1 M, sub-grid 0.1 M or 0.125 M (only one per symbol family). Clause 6.6 puts line-width-to-module at 1:10. | ISO 81714-1:2010 | verified |
| STD-17 | ISO 128-2 line widths run 0.13 / 0.18 / 0.25 / 0.35 / 0.5 / 0.7 / 1 / 1.4 / 2 mm on a 1:sqrt(2) series. Extra-wide : wide : narrow is 4:2:1. The 2022 text is the current one; 2020 is superseded with identical wording. | ISO 128-2:2022 | verified |
| STD-20 | ISO 14617-1:2005 6.4 sets the module M = 2.5 mm, shows small symbols at 200 percent, and uses an auxiliary grid of 0.25 M. Clause 8.2 says a resized symbol keeps its original line width. Verified against the 2005 edition; the 2025 edition restructured those clauses away. Stroke width is only a secondary estimator, corroborated independently by STD-12. | ISO 14617-1:2005 | verified for 2005 / uncertain for current |
| STD-24 | There is no published bubble-diameter-to-text-height ratio. ISA dimensions the bubble but not relative to text; PIP dimensions text but not the bubble. Text height is a sanity gate only. | searched; found nothing | uncertain |
| DEXPI-04 | DEXPI P&ID Specification 1.4 is the model implemented against: free, browsable, serialised as Proteus Schema 4.2.0. DEXPI 2.0 introduces “DEXPI XML” and replaces Proteus, so serialisation stays behind an adapter. | dexpi.org | verified |
| DEXPI-06 | There is no class named `SignalLine`. The class is `SignalConveyingFunction`, with subclasses `SignalLineFunction` and `MeasuringLineFunction`. | DEXPI 1.4 reference | verified |

The graph uses DEXPI 1.4 class names. Proteus XML is not emitted. If serialisation is added later, three composition traps apply: a `PipingNetworkSegment` does not own its `PipingNode`s (`PipingNodeOwner` does); `SensingLocation` has four subtypes, not two; instrumentation class URIs live under `sandbox.dexpi.org`, not POSC Caesar. DEXPI 1.4 does not normatively cite ISO 15926.

Quotes of ISA-5.1-2009 come from a French-language rendering and from university-hosted extracts (ISA and ANSI return 403 to automated fetch). A defensible conformance claim would re-verify the letter table, notes 14 and 30, and Table 5.4.4 against the English text of ANSI/ISA-5.1-2024 plus TR5.1.02/03. ISA-TR5.1.04-2026 has not been consulted.

---

## Corrections

The subject of each row is a prior belief. The code implements the right-hand column.

| ID | Prior belief | What the code does |
|---|---|---|
| STD-01 | “`S` in position 2 means Safety when the remaining letters are `V` or `E`.” | The gate is on the first letter (`F` / `P` / `T`) and on the device being a self-actuated emergency-protective element. The set is exactly `{FSV, PSV, TSV, PSE, TSE}`. The old rule would have emitted `LSV`, `ASE` and `ZSV` as safety devices. `Z`, not `S`, is the SIS modifier. |
| STD-02 | Kimray’s letter table follows ISA-5.1-2009, as its cover states. | It is the 1984 table. Adopting it wholesale leaves the parser with no concept of SIS tagging. |
| STD-25 | Text cap height is a module estimator at a ratio of 2 measurement units (ISA). | Dropped. On the sample, stroke and symbol estimators agreed at module 2.4000; the text estimator was 60 percent adrift. In a stroke font the marks are a mixture of partial glyphs and several sizes, not a cap height. Per STD-24 there is no published ratio. Render resolution comes from the narrow stroke. |
| STD-26 | A per-glyph shape codebook can replace OCR on a stroke-font drawing. | Refuted twice. On the supplied sheets, 7802 glyph marks produce 1744 distinct signatures, 1243 of them singletons. The top 40 cover 61 percent of marks; the top 200 cover 75 percent. Text recognition has to render crops and use a real recogniser. |
| STD-27 | Grammar-constrained character substitution can repair optical-recognition errors. | The ISA tag grammar cannot reject nonsense: line-number field schemas are company convention with variable arity. Substitution “repaired” 7 reads and produced `4-14`→`A-14`, `S08`→`508`, `2-D5S`→`Z-05S`. Substitution is disabled. Despacing (`MV-71 5-01`→`MV-715-01`) is unambiguous and remains. |
| ENG-01 | Cache only successful OCR reads. | Unreadable crops are about half of a stroke-font drawing. Leaving failures uncached meant 267 subprocess calls and roughly 40 seconds per warm run. Failures are cached as empty entries. Warm runs went from 59 seconds to 15 seconds. |

---

## The sample sheets

The files under `data/` are one test case. Nothing measured off them may become a constant. [`tests/test_derisk.py`](../tests/test_derisk.py) is the live check; if a new drawing disagrees, that is expected.

The plot is a born-digital CAD vector drawing on three sheets, ANSI B, rotated 270 degrees. There is no usable text layer (about 69 characters per page, logo footer only). Lettering is AutoCAD SHX: 1078 annotations, no `/Contents` key, covering most of the black glyph ink. There are no dash arrays (all 18 319 paths report `[] 0`); dashes are runs of short strokes. Exactly one non-zero stroke width is used; process pipes are degenerate filled rectangles. Forty-three instrument circles share one diameter. Against ISA Tables 6.1 and 6.3 those dimensions decode as 0.2 measurement units for the stroke and 7.000 for the bubble — a module of 2.4 points, a fact about this plot. The company logo is roughly 45 percent of the paths on page 0. The procedure agrees with the drawings on every design-limit row (the legitimate full-agreement case). Kimray writes the differential modifier in lower case (`PdI`), a third form next to ISA’s `PDI` and industry’s `DPI`.

---

## Lettering

Held-out figures live in [`../benchmarks/results.md`](../benchmarks/results.md). Raster-parameter sweeps plateaued at about 72 percent on hairline stroke fonts. Vector matching reads the strokes already in the file.

| ID | Assumption | Source and verification |
|---|---|---|
| OCR-01 | The generator renders the recogniser’s own stroke alphabet (`recognise/glyphs.py`; `benchmark/strokefont.py` imports it). Density has its own random stream, not coupled to the module. Truth boxes use authored tracking. The metric gate is 3 modules. | Segmentation and matching under size, weight, tracking, shear of plus or minus 0.08, and jitter of 0.02 of height. Not transfer to a foreign font. |
| OCR-02 | The confusable families {0 O D Q C G 6}, {1 I}, {8 B}, {5 S}, {2 Z}, {4 A} are not separable by shape at single-stroke weight. | Chamfer distance 0.022 versus 0.023 for a drawn 0 against the 0 and D templates. Grammar plus a digit prior apply only inside a plus-or-minus 0.010 tie band. |
| OCR-03 | Train and suffix letters exclude I, O, and Q. | Encoded in `standards/tags.py` (`_TRAIN`). That is also what lets the grammar resolve a trailing O into a 0. |
| OCR-04 | Stroke count is shape evidence: B is three strokes and 8 is two; 0 is one and D is two. | A 0.025 penalty per stroke-count difference separates what point distance cannot. |
| OCR-05 | Printed text is periodic and chains like dashes. Dissolving a chain re-emits absorbed real line pieces. | Pure glyph-derived chains need at least 15 modules and duty of at least 0.35. |
| OCR-06 | Text rows are found by interval single-link banding, with orientation chosen per row. Losing rows re-enter as their unclaimed remainder. | Fixed-width buckets orphaned marks by phase. Page-level orientation votes fragmented the lone vertical label on a horizontal page. |
| OCR-07 | A letter-sized multi-stroke SYMBOL near lettering is hypothetically a letter, and reading it is the test. | Unread promotion is reverted. Without that, the real drawing lost 157 symbol nodes. With it, the real graph is 384 nodes and 570 edges. |
| OCR-10 | The slant estimate is a hypothesis: read upright and desheared, and the lower mean character distance wins. | A, AA, W, WW, 7, 77, 747, 7A7, V, AV, VA and full tags, upright and at 0.08 shear, both orientations. |

---

## Judgement

These cannot be verified against an external source. They are labelled so they are not presented as findings. DESIGN-01, DESIGN-02, and DESIGN-11 are already in [`tradeoffs.md`](tradeoffs.md).

| ID | The choice | Why |
|---|---|---|
| DESIGN-06 | Under-claim: confidence propagates as the minimum, and absence-based and connectivity-dependent findings are capped. | Accusing a correct document of being wrong is the worst output this system can produce. |
| DESIGN-08 | Take Kimray as the base vocabulary and overlay the ISA-2009 additions (notably `Z` for Safety Instrumented System) as a labelled delta. | Keeps the guide as the source of truth for the oil-and-gas abbreviations it uniquely provides, while safety semantics come from the current standard (STD-02). |
| DESIGN-10 | Nameplate design-limit blocks are not read from the drawings while OCR reads only about a quarter of regions. | Attributing a lone pressure value to the wrong vessel is worse than reporting the comparison as unresolved. Pages carry more than one equipment item, so proximity is not attribution. |

| ID | Accepted risk | Why it stands |
|---|---|---|
| RISK-02 | Colour-cluster logo exclusion uses fixed count (50 or more) and area (under 8 percent) thresholds instead of module units. | Those thresholds gate a nomination, not a deletion. Colour is already a non-normative signal. A drawing that colours lines by service keeps its content because the count gate fails. |
| RISK-04 | Off-page connector matching is exact-string, so a connector read with one bad character will not join sheets. | Fuzzy joining manufactures cross-sheet topology out of misreads, which is the failure mode `MAX_SUBSTITUTIONS=0` exists to prevent. An unjoined connector is a visible gap. |

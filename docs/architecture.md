# Architecture

A system that reads any P&ID conforming to published conventions and produces a standards-conformant
plant graph, persisted in Supabase, cross-referenced against an SOP, browsable in a web UI, with
defensible precision and recall.

**Design principle.** The supplied documents are one test case, not the specification. No code branches
on facts about them; their measurements live in `assumptions.md` under `INPUT-*` and appear here only as
worked validation.

See also: [`assumptions.md`](assumptions.md) for every assumption with its source and confidence, and
[`tradeoffs.md`](tradeoffs.md) for the options considered and rejected.

---

## 1. Overview

```
INPUT     vector PDF · raster PDF · image · DEXPI XML
              └──────────┬──────────┘
                    ADAPTERS  →  primitive stream + measured capability descriptor
                         ↓
                   CALIBRATION  →  scale basis; every threshold becomes relative
                         ↓
                   RECOGNITION  →  symbols · text · lines   (strategy per capability)
                         ↓
    ╔══════════════════════════════════════════════════╗
    ║  SEMANTICS   ISA-5.1 tag grammar · DEXPI classes ║  ← knows only standards
    ╚══════════════════════════════════════════════════╝
                         ↓
                    GRAPH  →  DEXPI ConceptualModel + structural invariants
                         ↓
       ┌──────────┬──────────┬──────────┬──────────────┐
     STORE      CROSS-REF     UI      EVALUATION
    Supabase    rules       Next.js   4-tier P/R
```

The semantic layer is the stable core. A new input format is an adapter; a new drawing style is a
recognition strategy; neither touches semantics. That boundary is what makes the system generic, and it
is also what makes the failure modes in §2 tractable — each one is localised to a tier.

---

## 2. Failure model

You are right that this can deeply fail. These are the ways, ranked by how hard they are to detect, with
the architectural defence for each. **The ranking is by silence, not by frequency** — a loud failure is
cheap, a silent one is what sinks the project.

### F1 — Fabricated or missing connectivity *(most dangerous)*

The graph looks plausible, queries return answers, and edges are wrong. Nothing downstream can detect it:
a fabricated edge is structurally identical to a real one. Every cross-reference finding, every path
query and every UI claim inherits the error.

**Defences, layered:**
- **Never infer edges from crossings.** Two lines crossing are usually *not* connected. Connectivity
  comes only from endpoint proximity and symbol-port binding.
- **Typed evidence on every edge** — `port_binding`, `collinear_merge`, `bridged_gap`, `offpage_pair` —
  with a confidence, so the graph's weakest claims are queryable rather than uniform.
- **Structural invariants from the standard** (§5.3). These are the real defence: DEXPI constrains
  degree and type in ways a fabricated edge usually violates.
- **Report the edge-confidence distribution**, not just a graph. A graph whose edges are 60 % low
  confidence is a different artifact from one at 95 %, and the UI must show which it is.

### F2 — Metrics that measure the wrong thing *(most damaging to credibility)*

Precision and recall computed against ground truth your own system proposed. The numbers look strong and
certify nothing. This is worse than a technical failure because it *hides* technical failure — and it is
the single most common flaw in digitisation write-ups.

**Defence: the four-tier evaluation architecture in §7.** Tier 1 is synthetic data with exact,
independently-known ground truth. No tier is allowed to score a component against output that component
produced.

### F3 — Correct label, wrong object

Text is read perfectly and bound to the neighbouring symbol. The tag is valid, the grammar checks out,
every validator passes, and two nodes are silently mislabelled at once. Dense regions — valve manifolds,
parallel equipment trains — are where this concentrates.

**Defences:** global assignment (Hungarian) rather than greedy nearest-neighbour; an association margin
(best vs second-best) recorded as confidence; type compatibility as an assignment cost so an instrument
tag resists binding to a pipe fitting; and a dedicated association metric in the evaluation harness so
this is measured, not assumed.

### F4 — Template overfit

Everything works on the calibration drawing and collapses on the next one, because thresholds, symbol
sizes or tag patterns were learned from one source.

**Defences:** no absolute dimensions anywhere (§4); the symbol codebook is built per drawing rather than
shipped; project-specific vocabulary is data, not code; an explicit `unknown` class that routes to review
instead of being forced into the nearest known class; and synthetic evaluation across varied templates
and scales.

### F5 — Silent empty or partial results

A wrong coordinate frame, a mis-routed input, or a mis-derived scale yields a clean, confident, empty or
near-empty result with no exception raised.

**Defences:** postcondition assertions at every stage; a calibration self-check that must pass before
extraction runs; run-level atomicity so a partial run is never visible as complete; and the rule that no
stage may return an empty result without raising.

### F6 — Cascading calibration error

The scale basis is derived wrongly, so every relative threshold is wrong, and the whole pipeline produces
confident garbage.

**Defences:** calibration asserts multiple independent signals agree (grid quantum, stroke mode, text
mode, sheet size against the standard series); disagreement lowers confidence and triggers a fallback to
conservative absolute bounds with a loud warning rather than proceeding silently.

### F7 — Over-claiming in the cross-reference layer

Reporting "equipment missing from the P&ID" when extraction simply missed it. This accuses a correct
document of being wrong — the worst output a compliance-adjacent tool can produce.

**Defence:** findings that depend on *absence* are capped in severity and carry an extraction-completeness
flag; connectivity-dependent findings carry a confidence ceiling; confidence propagates as the minimum
over inputs. The system is designed to under-claim.

---

## 3. Adapters

```python
class Source(Protocol):
    def pages(self) -> Iterable[Page]: ...
    def capabilities(self, page: Page) -> Capabilities: ...
    def primitives(self, page: Page) -> Iterable[Primitive]: ...
```

`Capabilities` is a **measured descriptor, not a format label**: vector geometry present, text layer
extent, text-region hints, dash-array support, paint-type distinction, line-width variation, embedded
raster fraction, implied resolution.

⚠ **Route on measured magnitude, never on presence or file type.** Vector drawings routinely carry an
embedded logo bitmap and a vestigial text layer; scans carry stray vector annotations. Rules of the form
*"has an image ⇒ scanned"* or *"has text ⇒ use it"* misroute real files in both directions.

Implementations: `VectorPdfSource`, `RasterSource` (raster PDF, PNG/JPG/TIFF including multipage),
`DexpiSource` (Proteus XML — bypasses recognition entirely and exercises the semantic core directly).
Detect and refuse formats needing external binaries, with the conversion instruction.

---

## 4. Calibration — recover the drawing's *measurement unit*

**No absolute dimension is hardcoded.** But calibration is not arbitrary self-derivation either: **the
standards define symbol geometry in a per-drawing dimensionless module, and that module is what we
recover.**

### The dimensional system is normative

- **ANSI/ISA-5.1-2009 Clause 6** ("Graphic symbol dimension tables", new in 2009) makes symbol dimensions
  **mandatory** when the standard is invoked without exception, expressed in **measurement units (m.u.)**.
  §6.2.1 sets a *minimum* m.u. of **1/16 in (1.50 mm)**; §6.2.2 makes the actual m.u. a **free parameter
  chosen per drawing**, bounded below only. §6.1.3 explicitly permits scaling it up or down for legibility.
- **Table 6.1:** the instrument bubble is **7 m.u.** (with an 8 m.u. option).
- **Table 6.3:** signal line **0.2 m.u.**, process/equipment line **0.4 m.u.**; clearance around a symbol
  is half the symbol width.
- **ISO equivalent:** ISO 14617-1**:2005** §6.4 uses module **M = 2.5 mm**; ISO 81714-1:2010 §6.6 fixes
  line width to **M/10**; ISO 10628-1:2014 §5.3.1 gives the 0.4 M / 0.2 M / 0.1 M line classes and §5.4.2
  pins ordinary lettering to **1 M** (2 M for equipment designations).
  ⚠ **Cite editions by year.** ISO 14617-1**:2025** supersedes the 2005 edition, is technically revised
  and **restructured — clauses 6.4 and 8.2 no longer exist** (the contents show 4.3 "Dimensions and lines"
  and 4.4 "Modification of proportions"). Our §8.2 line-width claim is verified against **2005**; whether
  it survives into 2025 is unconfirmed. Likewise ISO 3098-0:1997 is **withdrawn** (superseded by
  ISO 3098-1:2015, values unchanged) and ISO 128-2:2020 by :2022. Citing withdrawn editions in a
  conformance deliverable is a credibility risk — cite the current ones and note where verification came
  from the older text.

So the quantity to recover is `U`, the drawing's module. Everything else is a published ratio.

```python
class Scale(BaseModel):
    unit_system: str  # 'ISA' | 'ISO'  — from sheet-size series
    U: float  # the module (ISA m.u. or ISO M), in drawing units
    cap_height: float  # modal ink cap height  (≈ 2·U ISA, 1·U ISO)
    stroke_narrow: float  # narrowest populated stroke cluster (≈ 0.2·U ISA, 0.1·U ISO)
    bubble: float | None  # measured circle-radius mode (expect ≈ 7·U, or 8·U)
    confidence: float
```

### Recipe

1. **Snap the page box** to the ANSI A–F / ARCH / ISO A0–A4 series → *unit-system prior only*.
   ⚠ It cannot recover plot scale: "B-size drawn small" and "D-size plotted at half" are
   indistinguishable from the page box alone.
   ⚠ **Detect the sheet standard, never assume it.** ISO 10628-1 §5.1.1 recommends A1 (594 × 841 mm)
   while PIP practice uses 22 × 34 in (558.8 × 863.6 mm) — ~6 % and ~3 % apart, close enough to pass a
   naive check and far enough to shift stroke measurements across bin boundaries.
2. **`cap_height`** = modal ink bbox height of uppercase/digit runs **inside the drawing frame**
   (exclude title block, notes and revision blocks — different text populations). **This is the primary
   anchor:** text is geometry, so it always scales with the plot, and ISO 10628-1 pins it to 1 M.
   ⚠ Measure ink extent, never a font-size operand — stroke fonts and outline fonts differ ~30 %.
3. **`stroke_narrow`** = narrowest well-populated, path-length-weighted stroke cluster; verify neighbours
   near 2× and 4× (ISO 128-2:2022 §5.1's 4:2:1 hierarchy).
   ⚠ **Secondary as a *scale* proxy.** Fixed CAD plot styles assign absolute output widths independent of
   plot scale, and ISO 14617-1:2005 §8.2 says a resized symbol *keeps* its original line width — so stroke
   does not track symbol size. **Diagnostic:** if `stroke_narrow` lands exactly on an ISO 128 value
   (0.13/0.18/0.25/0.35/0.5/0.7 mm), suspect a fixed lineweight and **discard it as a scale proxy**.
   ✅ **But precisely because it is scale-invariant, stroke width is a strong *class* signal — use it.**
   ISO 10628-1:2014 §5.3.1 assigns width **by object class** on a 4:2:1 lattice: 1.0 mm (0.4 M) main flow
   lines · 0.5 mm (0.2 M) equipment, unit frames, subsidiary and utility lines · 0.25 mm (0.1 M) valves,
   fittings, instrumentation and control/data lines. Feed the stroke class into recognition as a
   node/edge-type prior. ⚠ **The 0.5 mm band is not uniquely equipment** — it also covers subsidiary and
   energy-carrier lines, so a "0.5 ⇒ equipment" rule inflates equipment false positives. ⚠ And ISO 128-2
   §5.2 permits ±10 % deviation and off-series widths, so **bin by ratios between widths observed on the
   same sheet, never by absolute millimetre equality.**
4. **Sanity gate:** `cap_height / stroke_narrow` should sit ≈ 5 (ISA) to 14 (ISO type A). Outside
   **[3, 20]**, drop the stroke estimate and proceed on text alone.
5. **`U` = median of the surviving estimators** (`cap_height/2` or `/1`; `5×stroke` or `10×stroke`;
   zone-grid pitch ÷ module count where an ISO 5457 50 mm grid is detected).
6. **Find the bubble empirically** by mode-seeking the circle-radius histogram — *not* by predicting it
   from `U`. Accept the cluster where `D/U ∈ [5, 10]` (nominal 7 or 8, per ISA Table 6.1).
   A real P&ID has tens to hundreds of instrument circles at one or two radii; that mode is the strongest
   single signal in the document and needs no external anchor.
   ⚠ **There is no published bubble-diameter-to-text-height ratio** — the audit searched for one and found
   none, and PIP practice dimensions text but not the bubble. Any such window must therefore be
   **calibrated empirically per corpus and reported as such**, never cited as if it were standard.
   ⚠ **ISA Clause 6 is new in 2009**, so every pre-2009 drawing is dimensionally unconstrained by ISA.
   Dimensional conformance cannot be used as a validity gate for legacy drawings — which are the majority
   in circulation. Use it to *calibrate*, never to *reject*.
7. **Express every threshold in `U`.** Render resolution is derived:
   `dpi = target_cap_px × 72 / cap_height`, `target_cap_px ≈ 28`.
8. **Log `U`, `cap_height`, `stroke_narrow`, `D` per document.** If `D/U` drifts off 7–8 across a corpus,
   that is a non-ISA template — a finding, not a bug.

### Two invariants safe to hardcode

The **1:2:4 line-width hierarchy** (ISO 128-2 §5.1, mirrored by ISA's 0.2/0.4 m.u.) and
**stroke-to-lettering-height = 1/10 or 1/14** (ISO 3098 Tables 1–2). Nothing else absolute is.

✓ **Acceptance: rescale any drawing 2× and 0.5×, re-render, assert the graph is isomorphic with identical
tags — and assert `D/U` is unchanged.** That second assertion is what proves we recovered a module rather
than fitting a constant.

---

## 5. Semantics — the standards core

### 5.1 ISA-5.1 — instrument identification

Function letters decompose positionally: `first_letter [+ variable_modifier] + succeeding_letters
[+ function_modifier]`. The standard's annex tables **enumerate every permitted combination**, so parsing
is primarily a lookup against a seeded table, with a grammar as fallback for combinations real drawings
contain but the standard does not list.

⚠ **One disambiguation rule the audit refuted, with safety consequences.** An earlier draft said "`S` in
second position means *Safety* only when the remaining letters are exactly `V` or `E`." **That gate is
wrong.** ISA-5.1-2009 notes (14) and (30) give a much tighter rule: `S` is *Safety* only when the first
letter is `F`, `P` or `T` **and** the device is a self-actuated emergency-protective element — i.e. the
set is exactly **`{FSV, PSV, TSV, PSE, TSE}`**. Everywhere else `S` = *Switch*. The draft rule would have
emitted `LSV`, `ASE` and `ZSV` as safety devices. And note 14(d) states `S` shall **not** denote a Safety
Instrumented System; note (30) assigns **`Z`** that role.

⚠ **The diamond-in-square is genuinely ambiguous and must be modelled as such.** ISA-5.1-2009 Table 5.1.1
heads its columns *"A — Primary Choice or Basic Process Control System"* and *"B — Alternate Choice or
**Safety Instrumented System**"*. The shape alone therefore cannot distinguish an alternate-choice device
from an SIS device — that depends on the drawing's legend sheet — and on a pre-2009 drawing the same
shape means programmable logic control. **Assigning a single hard `device_type` to this shape will be
wrong on a large fraction of real drawings.** Emit the ambiguity: record the shape, the candidate
classes, and a `requires_legend` flag, and let the cross-reference layer treat it as unresolved rather
than guessing.

⚠ **Annex material is guidance, not conformance.** ISA-TR5.1.03-2024 describes the content moved out of
Annexes A and B as *"nonmandatory guidance on the use of the standard"*. Encoding it as conformance rules
would report violations that are not violations. **Keep a `guidance` tier separate from `normative`
checks**, and label findings accordingly.

**Bubble geometry maps to system class and location through a table, not code.** The guide enumerates
**five location classes**, each defined by three independent predicates — where it sits, whether it is
visible, and whether an operator can reach it:

| Line through bubble | Location | Visible | Operator-accessible |
|---|---|---|---|
| none | field, not panel/cabinet/console mounted | at field | yes |
| single solid | front of central/main panel or console | yes | yes |
| single dashed | rear of central/main panel, or cabinet behind panel | no | no |
| double solid | front of secondary/local panel or console | yes | yes |
| double dashed | rear of secondary/local panel, or field cabinet | no | no |

Storing all three predicates rather than a single enum matters: cross-reference rules about operator
action during a procedure depend on *accessibility*, not on the drafting symbol.

⚠ **Dashed detection must be geometric, not a dash-array read.** Many CAD exports simulate dashes with
runs of short solid strokes, so the discriminator is run-length/gap statistics on collinear segments —
the same routine used for signal-line typing.

**Valve symbols are composite, and the guide states the composition rules normatively:** element symbols
1–14 with actuator symbols 1–16 form process control valves; element 2 with actuators 20–21 forms a
pressure safety valve; elements 15–19 with actuators 13–15 form on-off solenoid valves; element 21 with
actuators 1–16 forms a variable-speed control unit. **Recognition must therefore operate on the composite
`(element ∪ actuator ∪ tag bubble ∪ leader)`, not on the connected component** — a rule derived from the
convention, and the reason naive per-mark clustering produces a long tail of singletons.

The guide also fixes **twelve line types** (major process, minor process connection, undefined signal,
pneumatic, electric, hydraulic, capillary, guided and unguided electromagnetic/sonic, two software/data
link forms, mechanical link) and a **fail-safe position** notation. Both become seeded tables.

Every parse emits a **conformance verdict**: listed in the reference, grammar-valid but unlisted,
non-conformant-but-normalised, or unparsed. Industry variants are normalised **and reported** — never
silently rewritten, never rejected.

### ⚠ Three editions are in play — the schema must name which one it claims

**Verified in the guide's own text: its letter table is the ISA-5.1-*1984* table, not 2009** — despite the
cover stating "Based on information from ANSI/ISA-5.1-2009". The tells: the header reads *"Measured or
Initiating Variable | Modifier | Readout or Passive Function | Output Function | Modifier"* (1984
structure, not 2009's "Column 1…Column 5"); `M` modifier = **Momentary**, which 2009 deleted; `P` =
**"Pressure, Vacuum"**, which 2009 shortened to "Pressure"; and **there is no Safety Instrumented System
entry** anywhere in the table, which 2009 added.

So: the **current** standard is ANSI/ISA-5.1-**2024**; our **verified rule set** is **2009**; our
**normative reference** is effectively **1984**. A "standards-conformant graph" that does not name its
edition is an unfalsifiable claim. **Record the target edition as a column on every seeded letter row**,
and state it in the README and the report.

⚠ **The most consequential gap: with the 1984 table, the parser has no concept of SIS tagging.** In
ISA-5.1-2009, note (30) makes **`Z` the Safety Instrumented System variable modifier**, and note 14(d)
says **`S` shall *not* be used for SIS**. Adopting Kimray wholesale silently classifies safety-instrumented
loops as ordinary position/dimension loops. **Recommendation: take Kimray as the base vocabulary but
overlay the 2009 additions (`Z`→SIS, the revised `P`, the deleted `M` modifier) as an explicit, labelled
delta**, so the guide stays the source of truth for the oil-&-gas abbreviations it uniquely provides
while safety semantics come from the current standard.

**Also inherited from the guide, and requiring curation before seeding:**

- **A shipped typo:** `FO  Fial Open` [sic, Rev 01/2021].
- **A real collision:** `FC` is defined twice on consecutive lines — *Flow Controller* and *Fail Close*.
- **A false friend:** `FI` = *Flow Indicator*, not any failure code.
- ⚠ **Case is load-bearing.** Kimray writes the differential modifier lower case (`PdI`, `PdS`) while
  ISA-2009 note 11(a) writes it upper case (`PD`). Naive upper-casing collapses `PdI`→`PDI` harmlessly,
  **but also merges Kimray's `PD` = *Pulsation Dampener* (a mechanical item) with ISA's `PD` = pressure
  differential** — two different node types become one. The grammar needs an explicit case policy plus
  equipment-vs-instrument disambiguation.

Every curation decision above must be recorded in `docs/assumptions.md`, or the precision/recall numbers
are not reproducible.

**Two parsing rules taken directly from the reference guide (verified in its text):**

- **The canonical differential form is `Pd…`, not `DP…`.** The guide lists `PdA`, `PdAH`, `PdAL`, `PdI`,
  `PdIC`, `PdS`, `PdSH`, `PdSL` — variable first, differential modifier second in lower case, exactly
  ISA's column-2 rule. A drawing writing `DPI`/`DPIT` is therefore using a **non-conformant industry
  variant**, which the parser normalises to `PdI`/`PdIT` while retaining the observed form and emitting
  a conformance finding. Canonicalising to the guide's own casing keeps us consistent with our stated
  source of truth.
- ⚠ **Abbreviations are ambiguous and must be disambiguated by context.** The guide lists `FC` twice — as
  *Flow Controller* **and** as *Fail Close*. The parser must resolve by position: inside an instrument
  bubble it is a loop function; adjacent to a final control element it is a failure position. Any
  abbreviation table built from this list needs a `context` column, not a single meaning per code.

### 5.2 DEXPI — the information model

A free, published, browsable model with an XML serialization. It supplies the vocabulary: `Equipment`
owning `Nozzle`s; `PipingNetworkSystem` containing `PipingNetworkSegment`s;
`ProcessInstrumentationFunction` with `SignalConveyingFunction`; and `SensingLocation` as the sanctioned
"this instrument measures that thing" relation. Tag decomposition uses DEXPI's own prefix / sequence /
suffix fields.

The graph schema is this model in relational form, with a seeded class-vocabulary table enforcing it by
foreign key. Adopting a published model rather than inventing enums is what makes the output
interoperable and the conformance claim checkable.

**Four corrections from the assumption audit — each would have produced a non-round-trippable schema:**

- ⚠ **`PipingNode` is *not* owned by `PipingNetworkSegment`.** The segment *references* nodes
  (`SourceNode`/`TargetNode`, 0..1 each); the node is *composed by* a `PipingNodeOwner` — a
  `PipingComponent`, `Nozzle`, etc. A schema nesting nodes under segments will not round-trip.
- ⚠ **`SensingLocation` has four subtypes** — `Mount`, `Nozzle`, `PipingComponent`,
  `PipingNetworkSegment` — not two. Restricting instrument attachment to segments and nozzles silently
  drops valid measurements.
- ⚠ **`ComponentClassURI` uses two namespaces**, not one: equipment and piping mostly resolve to
  `data.posccaesar.org/rdl/RDS…`, but **instrumentation classes resolve to `sandbox.dexpi.org/rdl/…`**.
  A validation rule anchored on the POSC Caesar prefix would reject every instrumentation object in a
  valid file. Store `ComponentClass` (the name) as the stable key and the URI as metadata — `sandbox` is
  explicitly provisional.
- ⚠ **DEXPI 1.4 does not normatively reference ISO 15926.** Its References appendix lists only CSS Color 4,
  CSS Values 4, the Proteus Schema and SVG 2. The ISO 15926 link is *indirect*, via POSC Caesar's RDL.
  Any claim of ISO 15926 conformance must be softened accordingly.

⚠ **The wire format is moving.** DEXPI 2.0 (Oct 2025) introduces "DEXPI XML" and replaces the Proteus
Schema. The *information model* is stable; the *serialization* is not. Keep serialization behind an
adapter and treat Proteus 4.2.0 as today's target, not a permanent one. If a Proteus reader is built:
`<Connection>` may carry only `FromID`/`FromNode`, so **treat all four attributes as optional**, and note
that node index **0 is the `PipingNodeOwner` itself — real nodes start at 1**.

### 5.3 Structural invariants — the main defence against F1

The standards constrain graph shape, which gives us cheap, generic validators that fabricated edges tend
to violate:

- a piping segment has exactly one source and one target endpoint;
- a nozzle belongs to exactly one equipment item and participates in at most one segment;
- an inline component (valve, fitting, orifice) lies on exactly one segment and has exactly two piping
  nodes;
- an instrumentation function has at least one sensing location or actuating link;
- signal-conveying functions connect instrumentation, never process items directly;
- a relief device's inlet traces to a pressure-containing item;
- degree bounds per class come from the class definition, not from guesswork.

Violations are surfaced as findings against the *extraction*, distinct from findings against the
*documents*. That distinction matters: it prevents F7.

### 5.4 What is explicitly *not* standardised

Line-number field schemas, equipment class letters, user's-choice ISA letters, and off-page connector
formats are **company convention**. They live in project vocabulary tables, seeded per project, with
unrecognised fields preserved rather than dropped. Hardcoding one contractor's line-number grammar is the
most likely way to build something that only works on one client's drawings.

---

## 6. Recognition

Three problems, each with strategies ranked by the capability descriptor:

| Problem | Preferred | Fallback | Last resort |
|---|---|---|---|
| Text regions | structural hints from the source | geometric clustering of glyph marks | connected components + text/graphics separation |
| Text content | vector glyph matching on the strokes themselves | embedded text layer | crop + raster OCR at the derived DPI |
| Line type | dash arrays | collinear gap statistics | stroke thickness |
| Symbols | normalised shape matching | raster template match | learned detector |
| Connectivity | endpoints + port binding | endpoints + port binding | morphology + line-segment detection |

Strategies degrade **independently**. A page may take the best option for geometry and the worst for
text; that must not force a whole-pipeline fork.

Symbol matching is **scale- and rotation-normalised before comparison**, so it is generic by
construction. The codebook maps normalised shapes to standard classes and is built by clustering each
drawing's own symbols and labelling cluster exemplars — which works for any template, not one.

An explicit `unknown` class is mandatory. Forcing an unrecognised symbol into the nearest known class is
how F4 becomes invisible.

**Two free priors worth exploiting, both conditional on the detected unit system:**

- **Stroke width as a class prior** (§4 step 3) — scale-invariant, standards-assigned, and available
  before any shape matching.
- **Upper-case-only text** — ISO 10628-1 §5.4.1 requires legends and designations in flow diagrams to be
  written in upper case (chemical formulae excepted), letting OCR reject lower-case hypotheses outright.
  ⚠ Apply only when the drawing is ISO-convention: our reference guide's own canonical differential form
  is `PdI`, with a deliberate lower-case modifier, so an unconditional upper-case rule would corrupt ISA
  tags.

⚠ **Stroke width cannot separate small annotation text from instrument symbology.** Type B lettering at
ISO 10628-1's 2.5 mm "other lettering" height gives `d = h/10 = 0.25 mm` — exactly the width mandated for
valve, fitting and instrumentation symbols. That separation must come from geometry and connectivity.

---

## 6b. Graph, storage, cross-reference, UI, deployment

**Graph.** The DEXPI ConceptualModel as a property graph. Junctions are retained internally for fidelity
and filtered from the default view. Off-page connectors stitch sheets into one plant graph; connectors
pointing outside the supplied set resolve to `external_unresolvable` — a normal state, not a failure.

**Storage.** Supabase Postgres. Nodes, edges and attributes as relational tables with a seeded
`dexpi_class` vocabulary table enforcing the standard by foreign key. Extraction runs are versioned so
re-running never destroys prior results; review state keys to a content-addressed stable id so it
survives re-runs. Writes go through a direct Postgres connection in one transaction; the UI reads through
PostgREST. Original files and page renders live in Storage, never on local disk.

⚠ **Three platform corrections from the assumption audit:**

- **Enabling RLS is not sufficient.** A new table in an exposed schema starts with *every privilege
  already granted* to `anon` and `authenticated`, and **adding policies does not take those grants back**.
  The security step is `ENABLE ROW LEVEL SECURITY` **and `REVOKE`**. (The common claim "RLS is off by
  default" holds only for tables created via SQL/migrations — Dashboard-created tables get it
  automatically. We create via migrations, so it applies to us.)
- **PostgREST's 1 000-row cap applies to functions too**, not only tables and views. A graph-traversal
  RPC truncates at 1 000 rows **with no error** — which corrupts evaluation numbers, not merely the UI.
  **Have traversal functions return a single aggregated `jsonb` document**, or paginate explicitly and
  assert the returned count.
- **Do not rely on `LISTEN`/`NOTIFY` through the pooler.** No vendor doc settles it; PgBouncer's own
  matrix marks `LISTEN` "Never" under transaction pooling and Supavisor has open issues. Use Supabase
  Realtime or polling for progress signalling.

**Cross-reference.** A rules engine over the graph, in three layers: intra-drawing consistency (needs no
SOP — relief set-point versus design pressure, unprotected vessels, orphaned instruments, connector
reciprocity, duplicate tags, conformance to the drawing's own notes); SOP agreement (equipment coverage
both ways, design-limit comparison with unit and range handling, tag-reference validity); and procedure
feasibility. Findings carry severity, status, confidence and quoted evidence from both documents.
Verdicts are always deterministic; a model may structure prose and write explanations, never decide.
Because a conforming SOP and drawing may legitimately agree everywhere, **verified matches are reported
as first-class results**, and correctness is demonstrated by fault injection.

### Supabase — using it as a platform, not just a table store

| Feature | Used for |
|---|---|
| **Postgres + RPC** | The graph itself. Traversals (`trace_downstream`, `valves_on_line`, `unpaired_connectors`) are recursive CTEs wrapped as `SECURITY INVOKER` functions returning aggregated `jsonb` (see the 1 000-row trap above) |
| **Storage** | Original documents, the render pyramid, symbol-crop thumbnails. Private buckets, signed URLs |
| **Realtime** | Live extraction progress and findings streaming into the UI as the local pipeline writes them |
| **Auth + RLS** | Single-user magic link; `ENABLE ROW LEVEL SECURITY` **plus `REVOKE`** on `anon` |
| **Versioned runs** | Every extraction is a row; nothing is overwritten, so run-to-run diffing is a query, not a feature to build |
| **pgvector** *(optional)* | Fallback tier of entity resolution only — never the primary match path |

### UI — the design brief

Next.js reading Supabase directly. **The goal is that it looks like an engineering instrument, not a
CRUD app.** Dark, high-contrast, monospaced tags, the drawing itself as the hero surface. Five ideas
carry it:

**1. The dual pane.** Rendered drawing on the left with interactive hotspots at true coordinates,
abstract graph on the right, selection synchronised both ways. Because we hold exact bboxes in drawing
space, hotspots sit *precisely* on the real symbols — the document stays the interface rather than being
replaced by a node-link cartoon.

**2. Flow tracing — the feature engineers actually want.** Click a vessel, choose *trace downstream*, and
the process path animates outward through valves and instruments, **continuing across sheets** via
off-page connectors into one plant graph. This is the single most visually striking thing the data
supports, and it is only possible because connectivity and cross-sheet stitching were done properly. It
also doubles as the most convincing demonstration that the graph is real.

**3. A confidence layer.** A toggle that shades edges and nodes by extraction confidence — low-confidence
bridges in amber, `unknown` symbols outlined, `requires_legend` items flagged. **This is simultaneously
the coolest and the most honest thing in the UI:** most demos show a clean graph and hide the
uncertainty; showing it is what makes the numbers believable, and it looks like an instrument readout.

**4. Findings anchored on the drawing.** Severity badges at the offending geometry; clicking one opens
the SOP quote beside the P&ID crop, with accept/dismiss. Verified matches render as green checks, so the
screen is never a blank "no discrepancies found".

**5. Live generate → extract → diff.** A demo route that generates a synthetic drawing from the grammar,
runs extraction, and shows the recovered graph against the authored truth with the differences
highlighted. It makes the whole evaluation argument visible in about ten seconds, and no other submission
will have it.

Supporting: a command palette (type a tag, jump to it), loop collapsing (`TI`/`TW`/`TIT` of one loop as a
single expandable entity), filters by class, line number and sheet, and a run-diff view.

⚠ **Build order within the UI matters.** Dual pane → findings → flow tracing → confidence layer → demo
route. The first two are not cuttable; the last three are, in reverse order. A polished shell over a weak
pipeline is the classic failure of this kind of project, so the UI gets its time only after extraction
and cross-reference are real.

### Deployment — the free tier cannot run the pipeline

⚠ **Architectural constraint, not a configuration detail.** Render's free tier combines: **no free
Background Worker, Cron Job or Private Service**; Web Services that spin down after 15 minutes idle with
a ~1 minute cold start; an ephemeral filesystem with no attachable disk; and **0.1 CPU / 512 MB RAM**. A
Python image carrying OpenCV, a PDF rasteriser and OCR will plausibly OOM on a full-size sheet at 512 MB,
and **there is no way to run asynchronous ingestion inside those limits**.

**Therefore: the extraction pipeline runs locally via Docker Compose against the shared Supabase, and
Render hosts the UI only.** This fits the free tier honestly and removes the need for a jobs table or an
API service. `render.yaml` carries a commented `type: worker` block so the paid path is one plan change
away. Ingestion is a batch operation, so nothing is lost.

Budget: the free workspace gets **750 instance-hours and 500 pipeline (build) minutes per month** — *not*
750 build minutes. An OpenCV image build takes 4–8 minutes, so that is ~60–100 builds; use `buildFilter`
so a docs edit does not rebuild everything. ⚠ Prefer **`python:3.13-slim-bookworm`**: Debian 13 "trixie"
renamed many packages to a `t64` suffix (`libglib2.0-0t64`) and dropped others (`libgl1-mesa-glx` → use
`libgl1`), so pinning bookworm removes a whole class of build breakage. Use secret *files* rather than
build args — Render translates service env vars into build args automatically and silently.

---

## 7. Evaluation — how precision and recall are justified

This is the part that decides whether anyone should believe the system. **The governing rule: no
component is ever scored against output it produced.**

### Tier 1 — Synthetic generation, treating the convention as a formal grammar *(the primary claim)*

**Generate the graph first, then draw it.** A generator samples a *valid process graph* from a grammar
over the standard vocabulary, lays it out, renders it, and degrades it. Because we authored the graph
before it became pixels, ground truth is exact at **four levels simultaneously** — and that is what makes
this tier carry the weight:

| Level | Truth available |
|---|---|
| Symbols | class, bbox, rotation, composition (element + actuator) |
| Text | string, bbox, orientation, and **what it labels** |
| Connectivity | every edge, its type, its endpoints and ports |
| Graph semantics | loops, equipment/nozzle ownership, sensing and actuating relations |

Nothing else in the evaluation gives level 3 and 4 truth. Hand-labelling gives boxes; only generation
gives topology.

**The grammar's constraints are the structural invariants of §5.3, run in reverse.** A segment has one
source and one target; a nozzle belongs to one equipment item; an inline component sits on one segment;
a signal function connects instrumentation, never process. Used as generator productions these guarantee
validity by construction; used as validators they detect fabricated edges. **Same rules, both directions** —
which means a generator bug and an extractor bug cannot cancel out silently.

Sketch of the productions:

```
Plant     → Unit+
Unit      → Equipment · Nozzle{2..n} · Loop*
Loop      → Sensor · Transmitter? · Controller? · FinalElement?      # ISA loop grammar
Segment   → (Nozzle|Component).port → InlineComponent* → (Nozzle|Component).port
Tag       → firstLetter · modifier? · succeeding+ · loopNumber · suffix?
```

**Randomisation must cover structure, not only appearance.** This is the part I would push on: the
axes you listed are almost all *appearance*, and appearance variation fixes a different failure than
structure variation does. Degradation multiplies how a symbol *looks*; it cannot invent a layout the
model has never seen.

| Appearance axes *(vary how it looks)* | Structural axes *(vary what it is)* |
|---|---|
| font family and weight; stroke-class assignment | topology: series/parallel trains, recycles, headers, bypasses |
| module size and symbol scale | **line crossings without hops** — targets F1 directly |
| rotation and mirroring | dense parallel runs with near-identical tag sets — targets F3 |
| scan quality: blur, noise, compression, skew | manifolds and instrument clusters — targets F3 |
| broken lines, faded symbols, ink bleed | label density and deliberate text/graphics overlap |
| sheet size, plot scale, unit system (ISA/ISO) | symbol-library variants and non-conformant tags — targets F4 |
| line thickness within ISO 128 tolerance | off-page connectors, unresolvable references, sheet notes |

⚠ **Map each axis to the failure it defends against, and refuse to ship an axis that defends nothing.**
Heavy blur augmentation with no dense-manifold generation leaves F3 completely undefended while the
metrics look thorough.

**The generator also produces the SOP.** Since the graph is known, emit a matching procedure document
and inject catalogued discrepancies — wrong design limit, renamed equipment, infeasible step, missing
relief path. That gives **exact P/R for the cross-reference engine**, not just for vision, and it is
free.

**Report a breaking point, not a number.** Sweep degradation severity and structural density and report
where accuracy crosses a threshold. "F1 ≥ 0.9 up to moderate scan degradation and 1.5× typical label
density, falling to 0.6 beyond" is a far more useful and more honest claim than a single figure.

### The two risks that decide whether Tier 1 is worth anything

**R1 — The generator becomes the specification.** If the model only ever sees graphs the grammar can
produce, it learns *the grammar*, not P&IDs. Real drawings contain drafting errors, legacy conventions,
vendor packages, hand annotations, revision clouds and non-conformant tags that no clean grammar emits.
Synthetic scores then look excellent and certify very little.
**Mitigations:** deliberately include *malformed* productions (violated invariants, duplicate tags,
dangling connectors, mixed editions); hold a fraction of the grammar out of training and test on it; and
always report the synthetic-to-real gap rather than the synthetic number alone.

**R2 — Layout realism is harder than symbol realism, and matters more.** Real P&IDs have strong layout
convention: left-to-right process flow, equipment on a baseline, instruments above and below, orthogonal
routing, utilities at the margins. Randomly placed symbols produce drawings that are either trivially
easy or so unlike reality that nothing transfers. **Budget more effort on the layout engine than on the
degradation stack** — it is the single biggest determinant of whether Tier 1 transfers.

### ⚠ Correction to the "fine-tune on real" step

With only a handful of real drawings you **cannot both fine-tune and validate on them** — any split is
too small to mean anything, and fine-tuning on three drawings overfits immediately while destroying the
only independent measurement you have.

**So: real drawings are for validation and threshold calibration, not fine-tuning.** Concretely, the real
set is used to (a) measure the sim-to-real gap, (b) calibrate decision thresholds and confidence
mapping, and (c) surface failure classes the grammar does not generate — which then become **new
generator productions**, closing the loop. Fine-tuning becomes appropriate only once enough real,
independently-labelled drawings exist to hold out a genuine test set. Until then, synthetic trains,
real judges, and the gap between them is itself a headline result.

### Tier 2 — Public annotated datasets *(external validity)*

Score against a published dataset with third-party labels, using its **published protocol and reported
baselines**. This is the only tier where our numbers are comparable to other people's work, which is what
converts "we measured ourselves" into "we placed on a known scale."

Its limitation: public P&ID label sets are coarse (a handful of node classes), so our fine-grained
classification cannot be scored here. Report Tier 2 at their granularity and keep the fine-grained table
separate — never silently coarsen our own metrics to make a number look better.

### Tier 3 — Real held-out drawings *(realism)*

The supplied documents and any others, with a **stratified human audit** rather than exhaustive labelling.
Report the audit's sample size and agreement rate next to every figure.

Its limitation, stated in the README: in a compressed build this set is model-proposed and
human-spot-checked, not independently labelled. It is evidence of realism, **not** the primary
quantitative claim — that is what Tier 1 is for. This is the honest answer to F2.

### Tier 4 — Property-based checks *(continuous, cheap, no labels)*

These need no ground truth at all and run on every commit:

- **Invariance:** rescale, rotate, re-render, change DPI → the graph must be isomorphic with identical
  tags. Catches F4 and F6.
- **Round-trip:** ingest a standards-conformant XML file, build the graph, export it, re-ingest → assert
  isomorphism. Exercises the semantic core with exact expectations and no vision at all.
- **Structural invariants (§5.3):** violated invariants are a measurable defect rate against F1.
- **Fault injection:** perturb inputs with known, catalogued changes and assert each is caught. For the
  cross-reference layer, ground truth here is exact by construction — this is a genuine P/R measurement,
  not a smoke test.
- **Determinism:** two runs, byte-identical output.

### Metric definitions

| Task | Primary metric | Matching |
|---|---|---|
| Symbol detection | P/R/F1 per class + mAP | IoU, **swept** not fixed — a single threshold is arbitrary and small symbols are penalised disproportionately |
| Text region | P/R | IoU with a height-normalised rule |
| Text content | **exact-string accuracy** | on matched regions only, reporting the matched-subset size |
| Connectivity | edge P/R/F1 on matched nodes **and** edge recall with gold nodes injected | the second isolates snapping failure from detection failure |
| Association | P/R of label→object binding | direct — this is F3 made measurable |
| End-to-end | graph edit distance on subgraphs + correctness of canonical path queries | task-level truth |
| Cross-reference | P/R of findings | exact by construction (fault injection) |

**Character error rate is a diagnostic, never a headline.** A single-character error in a tag is a >95 %
character match and a completely different component — CER hides exactly the errors that change topology.

**Scoring happens in drawing coordinates**, never pixels, so results do not move when render resolution
changes.

### Statistical honesty

Sample sizes in this domain are small enough that point estimates mislead. Therefore: every figure
carries its denominator and a confidence interval; no rate is printed for a class below a minimum
instance count, and excluded classes are listed rather than quietly dropped; method comparisons use a
paired test on the same instances, not a comparison of independent point estimates; and rejected
approaches are reported **with their numbers**, because a negative result with data is stronger evidence
of rigour than silence.

---

## 8. Test case — the supplied documents

⚠ **Evidence about one drawing set. None of it may appear in the code.** It validates the architecture
and seeds project vocabulary.

**Drawings** — 3 sheets, born-digital CAD vector plot, ANSI B sheet, rotated. No usable text layer.

**Calibration decodes cleanly against ISA Clause 6, which is the strongest validation the architecture
has received.** The narrowest stroke is exactly **0.2 m.u.** (ISA Table 6.3's signal-line weight), giving
`U = 5 × stroke`; the instrument circle then measures **7.000 m.u.** — exactly ISA Table 6.1 — and text
heights land on 0.8 / 1.0 / 1.2 / 1.4 m.u. The drafter chose m.u. = 1/15 in, legally above ISA's 1/16 in
minimum. Cross-checking against ISO gives M = 3.39 mm rather than 2.5 mm, so this is an ISA/imperial
drawing, not an ISO one — which the unit-system prior from the page box predicts correctly.
The apparent "device grid" that 96–99.7 % of dimensions land on is simply the CAD template snapping to
0.2 m.u. **There is nothing standard about the absolute values; there is everything standard about 7 and
0.2.** A parser keyed to the ratios reproduces this drawing and generalises; one keyed to the points does
neither. Capabilities: vector geometry ✓, text layer ✗,
text-region hints ✓ (covering ~79–93 % of glyph ink), dash arrays ✗ (dashes simulated with short
strokes), line-width signal ✗ (one non-zero width), paint-type signal ✓, embedded raster < 1 %.
Content is filter separators, a stabiliser column with pump, an after-cooler and a heat exchanger, with
ISA-tagged instrumentation including a common industry variant of the conformant differential-pressure
form — a useful conformance-reporting case. Quirks worth regression tests: a logo accounting for a large
share of page paths, sheet notes that redefine tag numbering, and connectors referencing sheets outside
the supplied set.

**SOP** — an operating-limits excerpt with a small design-limit table whose rows all agree with the
drawings, plus a placeholder marking removed content. Properties reveal the original is a purge procedure
for the same facility. Useful because it tests the **legitimate full-agreement** path, which is where a
naive comparator reports nothing and looks broken.

---

## 11. Cross-cutting rules

- **Fail loudly.** No stage returns an empty result without raising. No run is visible as complete unless
  it is.
- **One coordinate transform, in one place**, applied at the adapter boundary. A wrong frame raises no
  exception — it just produces confidently wrong output.
- **Determinism.** Fixed seeds, sorted iteration, quantised values before hashing, model calls cached to
  committed artifacts.
- **Provenance everywhere.** Every node, edge and finding traces to a page, region, method and
  confidence, so a disputed value is one click from its evidence.
- **Configuration over branching.** If you are writing `if drawing_is_from_contractor_X`, it belongs in a
  table.
- **Under-claim.** Confidence propagates as the minimum over inputs. Absence-based and
  connectivity-dependent findings are capped.

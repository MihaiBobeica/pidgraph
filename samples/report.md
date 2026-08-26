# P&ID / SOP Cross-Reference Report

- **Drawings:** `data/pid/diagram.pdf`
- **Procedure:** `data/sop/sop.docx` — *Majorsville – Initial Purge of Condensate Skid*
- **Estimated extraction recall:** 12%

## Summary

**0 checks verified** · **7 findings**

| Severity | Count |
|---|---|
| info | 1 |
| low | 6 |

## Findings

### • F-715A carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** F-715 A and B Particulate Filters | 275 | 100
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • F-715B carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** F-715 A and B Particulate Filters | 275 | 100
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • V-745 carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** V-745 Stabilizer Tower | 300 | 375
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • E-742 carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** E-742 Exchanger (Shell) | 300 | 375
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • E-742 carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** E-742 Exchanger (Tube) | 300 | 250
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • AC-746 carries SOP limits but no drawing data was matched

- **Check:** `equipment_not_found_in_drawing`
- **Severity:** low · **Status:** needs_review
- **Confidence:** 12%
- **Procedure evidence:** AC-746 After Cooler | 350 | -20 to 400
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

The procedure sets limits for this item, but nothing on the drawing was matched for comparison. That may be an extraction gap rather than a problem with the document — an estimated 12% of it was read — so this is capped in severity and reported as unresolved, not as a conflict.

### • 341 symbols carry no resolved class

- **Check:** `symbol_requires_legend`
- **Severity:** info · **Status:** needs_review
- **Confidence:** 100%
- ⓘ This finding rests on something *not* being found. That could mean the document has a defect, or it could just mean extraction missed it — which cannot be distinguished, so the severity is capped.

Some symbols really are ambiguous without the drawing's legend sheet — the standard itself gives one shape two different meanings. They are listed rather than guessed, so a reader with the legend can settle them.

## Extraction

| Metric | Value |
|---|---|
| pages | 3 |
| nodes | 384 |
| edges | 570 |
| instrument symbols | 43 |
| text regions | 617 |
| elapsed | 14.4s |

## Notes

- Nameplate design-limit blocks are not read from the drawings. Local OCR manages about a quarter of the regions on this stroke font, and a page usually holds more than one piece of equipment — so pinning a stray pressure value to the wrong vessel is a worse outcome than saying the comparison is unresolved. Tags on the drawing ARE read, and they drive the drawing-side checks.
- An estimated 12% of the drawing was read. That number matters for any finding above that rests on something being absent — those are capped in severity and marked as possibly incomplete.
- Every verdict here comes from a deterministic rule. No model decides whether something is a finding, so this report reproduces exactly.
- On editions: safety semantics follow ANSI/ISA-5.1-2009. The base vocabulary comes from the reference guide, whose letter table is really ANSI/ISA-5.1-1984, so the SIS modifier is overlaid on top of it.

---

*Generated by `pidgraph check` on the shipped `data/` inputs. Absolute paths in a live run are replaced here with repo-relative ones.*

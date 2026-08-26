# Idea: a person links a drawing to an SOP

Not every P&ID belongs with every procedure. A drawing should only be checked against an SOP that someone has said is about the same plant.

**Sketch.** A map of library paths, one SOP per drawing:

```json
{ "p&id/diagram.pdf": ["sop/sop.docx"] }
```

In the data pane: select a drawing, then Link on an SOP row. Unlink the same way. This file is an idea, not a spec. Nothing implements it yet.
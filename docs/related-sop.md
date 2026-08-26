# Idea: a person links a drawing to a procedure

Not every piping and instrumentation diagram belongs with every standard operating procedure. A compressor-station drawing and a condensate-skid purge procedure may share a tag style and even a few loop numbers; they remain different plants. A drawing should only be checked against a procedure that has been declared to concern the same unit.

That pairing must not be inferred from tags, titles, or filenames. `V-745` on two sheets is not evidence that they should be cross-referenced. A tag is still what a check compares after two files are paired. It is not how pairing is decided.

The sketch is a map of library paths, one procedure per drawing:

```json
{ "pid/diagram.pdf": ["sop/sop.docx"] }
```

On the command line, `--pid` plus `--sop` is the same idea, said once per invocation. In the data pane, the intended interaction was: select a drawing, then Link on a procedure row, and unlink the same way.

This file is an idea, not a spec. Nothing implements it yet. Today, discovery in `data/` will check the first drawing it finds against the first procedure it finds.

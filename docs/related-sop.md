# Idea: a person links a drawing to a procedure

Not every piping and instrumentation diagram belongs with every standard operating procedure. A drawing should only be checked against a procedure that someone has said is about the same plant.

Do not infer that pairing from tags, titles, or filenames. A tag is still what a check compares after two files are paired. It is not how pairing is decided.

The sketch is a map of library paths, one procedure per drawing:

```json
{ "p&id/diagram.pdf": ["sop/sop.docx"] }
```

On the command line, `--pid` plus `--sop` is the same idea. In the data pane, the thought was: select a drawing, then Link on a procedure row, and unlink the same way.

This file is an idea, not a spec. Nothing implements it yet.

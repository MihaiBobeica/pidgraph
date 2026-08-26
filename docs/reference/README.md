# Reference material

The vocabulary for these oil-and-gas abbreviations comes from Kimray’s *How to Read an Oil and Gas P&ID* guide. It is not shipped in this repository.

That guide is why `MV` is a manual valve, why equipment class letters look the way they do on the sample sheets, and why the differential modifier shows up in lower case (`PdI`). It is also why three editions of ISA-5.1 have to live in the parser at once: the guide’s letter table is the 1984 table, not the 2009 edition its cover claims. It still lists `M` as Momentary (deleted in 2009), gives `P` as *Pressure, Vacuum*, and has no Safety Instrumented System entry. Taking it wholesale would classify every SIS loop as an ordinary position loop.

The ISA letter tables and DEXPI class names the parser actually uses live in `pidgraph/standards/`. The 2009 `Z` (Safety Instrumented System) is overlaid there as a labelled delta, and the 1984 `M` is retained because drawings in this corpus still use it. The citations behind those tables — including the `S`-means-Safety trap, the industry `DPI`/`PDI` split, and the DEXPI class names — are in [`assumptions.md`](../assumptions.md).

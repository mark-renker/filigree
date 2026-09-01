# Third-party material

The MIT licence in `LICENSE` covers the source, documentation and examples in
this repository. Two categories of third-party material are called out here.

## MAESTRO v3.0.0 — statistics only, corpus not redistributed

Filigree's `feel` engine (humanised timing, velocity and gate) is calibrated
against **MAESTRO v3.0.0**, Google Magenta's dataset of real piano performances
captured on Yamaha Disklaviers. The dataset is licensed **CC BY-NC-SA 4.0**.

The 12 MIDI excerpts that calibration was measured from are **deliberately not
included** in this repository: a non-commercial, share-alike corpus does not
belong inside an MIT-licensed source tree. What is included is the derived
statistics (`refs/midi/stats.json`, `refs/midi/feel_measured.json`) and the full
provenance record (`refs/midi/SOURCES.md`) — the archive URL, its checksum, and
the exact path of every file inside it, so the corpus can be re-created locally
in a couple of minutes.

Those derived statistics are a work based on a CC BY-NC-SA 4.0 dataset. Treat
them as carrying the same attribution, non-commercial and share-alike terms,
not the MIT licence.

> Hawthorne et al., "Enabling Factorized Piano Music Modeling and Generation
> with the MAESTRO Dataset", ICLR 2019.
> <https://magenta.tensorflow.org/datasets/maestro>

To restore the corpus and run the measurement tooling yourself, follow
`refs/midi/SOURCES.md`, then:

```bash
python tools/perf_stats.py refs/midi -o refs/midi/stats.json
```

## Reference screenshots — not redistributed

The playground UI was built against a named visual bar (see `refs/BAR.md`):
**strudel.cc**'s live-coding editor and **signal**, an open-source web piano
roll. Screenshots of those two products were captured for the internal blind
comparison and are **not included** in this repository. `refs/BAR.md` cites both
by name and URL, and the critic verdicts in `refs/verdicts/` describe the
compared regions in text, so the build record remains readable without them.

Every screenshot that *is* present — in `docs/screenshots/` and `refs/ui/` — is
of Filigree itself.

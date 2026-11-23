# Miqra al pi ha-Masorah importer

Imports [*Miqra according to the Masorah*](https://he.wikisource.org/wiki/%D7%9E%D7%A7%D7%A8%D7%90_%D7%A2%D7%9C_%D7%A4%D7%99_%D7%94%D7%9E%D7%A1%D7%95%D7%A8%D7%94) (MAM) into the JLPTEI project `tanakh-miqra_al_pi_hamasorah-he`. The text comes from the JSON files of [MAM-parsed plus](https://bdenckla.github.io/MAM-basics/MAM-parsed/plus/html/mpplus.html) in [MAM-basics](https://github.com/bdenckla/MAM-basics), which are parsed from MAM's text at Hebrew Wikisource. The humash importer reads its aliyah divisions from the same files (`humash/aliyot.py`).

## License

MAM was prepared by Seth (Avi) Kadish from materials that he originally developed at Hebrew Wikisource, and is available under **CC BY-SA 4.0**. The attribution it asks for differs between Hebrew and other languages; see the downloaded `LICENSE.md`, MAM-parsed's own, for its wording. The project's `index.xml` quotes both attributions and names the commit its text was taken from.

## Download

Writes into the `sourcetexts` submodule (`sourcetexts/sources`) by default; pass
`--sourcetexts-root` to use an external clone instead.

```bash
uv run python -m opensiddur.importer.miqra_al_pi_hamasorah.download
```

MAM-basics publishes no releases of the files, so a download is pinned to a commit: `COMMIT` in `download.py`, or `--commit`, which also takes a branch or tag (resolved to its commit through GitHub's API). Use `--dry-run` to print paths without downloading. A run whose commit and files match the manifest downloads nothing and writes nothing.

Output layout:

```
<sourcetexts-root>/miqra_al_pi_hamasorah/
  manifest.json      the repository, the commit, each file's URL, size and SHA-256, the download time
  LICENSE.md         MAM-parsed/LICENSE.md
  plus/
    A1-Genesis.json
    …
    FC-Chronicles.json
```

Each file is checked against the Git blob SHA GitHub lists for it at the commit. A file under `plus/` that the previous manifest recorded and the commit no longer has is deleted; nothing else is touched.

## Convert

```bash
uv run python -m opensiddur.importer.miqra_al_pi_hamasorah.convert [--only-book genesis]
```

Each plus file holds one or more books of the 39, each a set of chapters of verses; a verse is `[C, D, E]`: the separator from the previous verse, the verse label and the verse proper, as strings and templates. `miqra_plus.py` walks them with a closed dispatch: every template has a handler naming the role of each of its parameters (rendered text, note, apparatus, alternative), and an unknown template or parameter raises. It writes the intermediate XML that `miqra_to_tei.xslt` turns into TEI; `canonical_verses.py` first moves MAM's verses onto the canonical verse division. Chapter and verse numbers come from the JSON keys.

Where MAM offers alternatives the importer keeps: both ketiv and qere (`tei:choice`); both cantillations of a span with two (`j:option`); the form without the stress helper (מ:דחי, מ:צינור); the grammatical qamats (מ:קמץ's `ד`). MAM's documentation notes and scroll-difference notes go to the `tei:standOff`, anchored where they stand. The good endings (`good_ending_plus`) are not imported.

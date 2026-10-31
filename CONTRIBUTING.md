# Contributing

## Add a synthetic case

1. Add a `CaseSpec` in `crtest/gen.py::build_specs()`. Set the gold fields (use `_common`, `_set_term`, `_set_modification`), the rendering style (`date`, `money`, `kv`) and the hazard tags.
2. If the layout needs a new rendering trick, add it to `crtest/render.py` and a builder branch in `gen.py`. New hazard tags need a one-line description in `HAZARD_DESCRIPTIONS`.
3. `make cases naive site` and check the page images under `cases/<id>/pages/`.
4. Open a PR with the new case folder, the regenerated `manifest.json` and the updated `results/naive_text*.json`.

Rules for cases: fictional authority and supplier (use `crtest/corpus.py`), the "synthetic test document" footer stays on every page, every gold value must be derivable from the document (if it is not printed, it is `null`).

## Add an extractor result

Write predictions in the `results/` format (see README), run the scorer, commit both `results/<name>.json` and `results/<name>.scored.json`. Say which model/endpoint and mode (text, OCR, vision) in `description`. Never commit API keys.

## Add a real, hand-labelled document

Fetch with `python -m crtest.collect`, pick a release with an attached award notice or contract, label the fields in a `gold.json` using the schema, keep the `_provenance` block (source URL, fetch time, licence) and record the document's own licence. Put it under `cases/REAL-NNN/`. If the document's licence is unclear, link to it rather than copying it in.

## Rules

`crtest/pa2023.py` is a reference implementation of the checks, not a legal opinion. Changes need the section of the Act or the statutory instrument in the PR description.

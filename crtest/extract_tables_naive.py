"""The "wrong extraction" for the tables track: what a quick text-dump pipeline does.

pdftotext -layout, find the table's header line, then treat every following text line as one row (until the totals
line), split it on runs of two or more spaces and map the pieces left to right onto the printed columns. No
de-duplication, no merging of wrapped lines, no carrying values down. Deliberately not clever: it shows exactly where
each hazard bites. Writes tables/<case>/wrong.csv, a predictions JSON for the scorer, and appends the damage report to
each case's notes.md.

Run:  python -m crtest.extract_tables_naive --tables tables --out results_tables/naive_text.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess

from .score_tables import load_spec, score


def naive_rows(text: str, spec: dict) -> list[dict]:
    printed = [c for c in spec["columns"] if not c["printed_header"].endswith("(group heading)")]
    words = [c["printed_header"].split()[0].lower() for c in printed]
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if sum(w in ln.lower() for w in words) >= max(2, len(words) - 1)), None)
    if start is None:
        return []
    stop = re.compile(spec["naive_stop"])
    rows = []
    for ln in lines[start + 1:]:
        if stop.search(ln):
            break
        if not ln.strip():
            continue
        cells = re.split(r"\s{2,}", ln.strip())
        if len(cells) > len(printed):
            cells = cells[: len(printed) - 1] + [" ".join(cells[len(printed) - 1:])]
        row = {c["name"]: "" for c in spec["columns"]}
        for c, v in zip(printed, cells):
            row[c["name"]] = v
        rows.append(row)
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="tables")
    ap.add_argument("--out", default="results_tables/naive_text.json")
    args = ap.parse_args(argv)
    with open(os.path.join(args.tables, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    pred = {"extractor": "naive_text_tables", "version": "0.1.0", "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "description": "pdftotext -layout, one line = one row, cells split on 2+ spaces. Deliberately simple baseline.", "cases": {}}
    for c in manifest["cases"]:
        cid = c["case_id"]
        spec = load_spec(args.tables, cid)
        text = subprocess.run(["pdftotext", "-layout", os.path.join(args.tables, cid, "document.pdf"), "-"],
                              check=True, capture_output=True, text=True).stdout
        rows = naive_rows(text, spec)
        pred["cases"][cid] = {"rows": rows}
        with open(os.path.join(args.tables, cid, "wrong.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[col["name"] for col in spec["columns"]])
            w.writeheader()
            w.writerows(rows)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(pred, fh, indent=2, ensure_ascii=False)
    r = score(args.tables, args.out)
    with open(args.out.replace(".json", "") + ".scored.json", "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False)
    for cid, pc in r["per_case"].items():
        path = os.path.join(args.tables, cid, "notes.md")
        with open(path, encoding="utf-8") as fh:
            notes = fh.read().split("\n## What the wrong extraction gets wrong")[0].rstrip()
        extra_kinds = sorted({" ".join(str(v) for v in e["values"].values())[:60] for e in pc["extra_rows"]})[:8]
        lines = [f"\n\n## What the wrong extraction gets wrong\n",
                 f"`wrong.csv` is the naive text-dump extraction (pdftotext -layout, one line = one row, cells split on 2+ spaces). "
                 f"Scored against `expected.csv`: **{pc['cell_accuracy']:.0%} cell accuracy** (an extra row counts as a row of wrong cells; "
                 f"{pc['cell_recall']:.0%} of the expected cells are right), **{pc['rows_exact']}/{pc['rows_expected']} rows exactly right**, "
                 f"{pc['rows_extra']} extra rows, {pc['rows_missing']} missing rows.\n"]
        if extra_kinds:
            lines.append("\nExtra rows it invents (first text of each):\n\n" + "".join(f"- `{k}`\n" for k in extra_kinds))
        bad_cols = [c for c, a in pc["per_column"].items() if a is not None and a < 1]
        if bad_cols:
            lines.append("\nColumn accuracy: " + ", ".join(f"`{c}` {pc['per_column'][c]:.0%}" for c in bad_cols) + ".\n")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(notes + "".join(lines))
    from .score_tables import print_summary
    print_summary(r)


if __name__ == "__main__":
    main()

"""Mainstream table extractors as baselines for the tables track, each run with its documented defaults.

  pdfplumber_lines   pdfplumber page.extract_tables() with default settings (cells from ruling lines)
  pdfplumber_text    pdfplumber with vertical_strategy="text", horizontal_strategy="text" (cells from text alignment)
  pymupdf            PyMuPDF page.find_tables() with default settings
  pymupdf_plainbbox  diagnostic, not a default: PyMuPDF page.find_tables() with TEXT_ACCURATE_BBOXES taken out of
                     pymupdf.table's text flags. PyMuPDF 2.0 builds table text from glyph-tight character boxes, which
                     drops the spaces between words and moves ',' and '.' off the numbers onto a line of their own
                     ("12,480.00" -> "1248000\n, ."); with ordinary boxes its cell text is clean

The post-processing is the minimum needed to score a tool, and the same for every tool: the tables a tool finds are
concatenated in page order; header rows (a row whose text is made only of printed header words) are dropped;
each cell goes to the printed column it overlaps most horizontally (every table is centred in the text frame, so
gen_tables.COLUMN_WIDTHS_MM fixes where the printed columns are) and cells that land in the same printed column of one
row are joined; blank rows are dropped. Nothing is repaired: wrapped lines stay separate rows, blank cells are not filled
down, subtotal and total lines stay in, text outside the table stays in, and a column the document never prints in a cell
of its own (TB-004's week_ending) stays blank.

Writes <out>/<tool>/<case>.csv, scores each tool with crtest.score_tables (<out>/<tool>.scored.json) and writes
<out>/summary.json with the scores and a breakdown of each tool's extra rows. With --cleanup it also scores
<tool>_cleanup: the same output after generic_cleanup(), three case-agnostic rules any table pipeline might apply, which
shows how far each tool is from exact once the textbook clean-up is done.

Run:  python -m crtest.extract_tables_tools --tables tables --out results_tables/tools [--tools pymupdf] [--tag 1.26] [--cleanup]
Needs pdfplumber and/or pymupdf (pip install pdfplumber pymupdf); the rest of the test set does not.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

from .gen_tables import COLUMN_WIDTHS_MM
from .render import MARGIN, PAGE_W
from .score_tables import load_spec, score

MM = 72 / 25.4
TOOLS = ("pdfplumber_lines", "pdfplumber_text", "pymupdf")
DIAGNOSTIC_TOOLS = ("pymupdf_plainbbox",)
TEXT_STRATEGY = {"vertical_strategy": "text", "horizontal_strategy": "text"}
TOTAL_LINE = re.compile(r"^\s*(totals?\b|week total|quarter total|total for|carried forward|brought forward)", re.I)


def _key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _flat(s) -> str:
    return " ".join(str(s or "").split())


def printed_columns(spec: dict) -> list[dict]:
    """The columns printed in cells of their own (TB-004's week_ending is only a group heading)."""
    return [c for c in spec["columns"] if not c["printed_header"].endswith("(group heading)")]


def column_bounds(case_id: str, spec: dict) -> list[tuple[float, float]]:
    """(x0, x1) in PDF points from the left page edge for each printed column."""
    widths = [w * MM for w in COLUMN_WIDTHS_MM[case_id]]
    if len(widths) != len(printed_columns(spec)):
        raise ValueError(f"{case_id}: {len(widths)} column widths for {len(printed_columns(spec))} printed columns")
    x = MARGIN + (PAGE_W - 2 * MARGIN - sum(widths)) / 2
    out = []
    for w in widths:
        out.append((x, x + w))
        x += w
    return out


def header_words(spec: dict) -> frozenset[str]:
    return frozenset(_key(w) for c in printed_columns(spec) for w in c["printed_header"].split() if _key(w))


def is_header_row(texts: list, words: frozenset[str]) -> bool:
    """A header row, or the wrapped second line of one: the row's text, read left to right with spaces and punctuation
    removed, splits into whole printed-header words. Tools often cut header words across cells ('Director' | 'ate'),
    so the row is judged as a whole."""
    key = _key("".join(str(t or "") for t in texts))
    if len(key) < 2:
        return False
    ok = [True] + [False] * len(key)
    for i in range(len(key)):
        if ok[i]:
            for w in words:
                if key.startswith(w, i):
                    ok[i + len(w)] = True
    return ok[-1]


def column_for(x0: float, x1: float, bounds: list[tuple[float, float]]) -> int:
    overlap = [max(0.0, min(x1, b1) - max(x0, b0)) for b0, b1 in bounds]
    if max(overlap) > 0:
        return overlap.index(max(overlap))
    mid = (x0 + x1) / 2
    return min(range(len(bounds)), key=lambda i: abs(mid - (bounds[i][0] + bounds[i][1]) / 2))


def map_cells(cells: list, bounds: list[tuple[float, float]], join) -> list[str]:
    """cells: [(bbox, text)] of one tool row -> one string per printed column."""
    buckets: list[list] = [[] for _ in bounds]
    for bbox, text in cells:
        if _flat(text):
            buckets[column_for(bbox[0], bbox[2], bounds)].append((bbox, text))
    return [_flat(join(b)) if len(b) > 1 else (_flat(b[0][1]) if b else "") for b in buckets]


def _union(cells: list) -> tuple[float, float, float, float]:
    return (min(b[0] for b, _ in cells), min(b[1] for b, _ in cells), max(b[2] for b, _ in cells), max(b[3] for b, _ in cells))


def run_pdfplumber(path: str, bounds, hwords: frozenset[str], settings: dict | None) -> tuple[list[list[str]], dict]:
    import pdfplumber
    from pdfplumber.utils import extract_text

    rows: list[list[str]] = []
    info: dict = {"tool_version": pdfplumber.__version__, "tables": [], "header_rows_dropped": 0}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            def join(cells, page=page):
                # several tool cells in one printed column: re-read the chars of their union the way Table.extract does
                x0, top, x1, bottom = _union(cells)
                chars = [c for c in page.chars if x0 <= (c["x0"] + c["x1"]) / 2 < x1 and top <= (c["top"] + c["bottom"]) / 2 < bottom]
                return extract_text(chars, x_tolerance=3, y_tolerance=3)

            for t in sorted(page.find_tables(settings or {}), key=lambda t: (t.bbox[1], t.bbox[0])):
                info["tables"].append({"page": page.page_number, "rows": len(t.rows), "columns": max(len(r.cells) for r in t.rows)})
                for row, texts in zip(t.rows, t.extract()):
                    cells = [(b, x or "") for b, x in zip(row.cells, texts) if b is not None]
                    if is_header_row([x for _, x in cells], hwords):
                        info["header_rows_dropped"] += 1
                        continue
                    mapped = map_cells(cells, bounds, join)
                    if any(mapped):
                        rows.append(mapped)
    return rows, info


def run_pymupdf(path: str, bounds, hwords: frozenset[str], plain_bboxes: bool = False) -> tuple[list[list[str]], dict]:
    import pymupdf
    import pymupdf.table as mtable

    def join(cells):
        return " ".join(_flat(x) for _, x in sorted(cells, key=lambda c: c[0][0]))

    rows: list[list[str]] = []
    info: dict = {"tool_version": pymupdf.__version__, "tables": [], "header_rows_dropped": 0}
    saved = {k: getattr(mtable, k) for k in ("FLAGS", "TABLE_DETECTOR_FLAGS") if hasattr(mtable, k)}
    if plain_bboxes:
        for k, v in saved.items():
            setattr(mtable, k, v & ~pymupdf.TEXT_ACCURATE_BBOXES)
    doc = pymupdf.open(path)
    try:
        for page in doc:
            for t in sorted(page.find_tables().tables, key=lambda t: (t.bbox[1], t.bbox[0])):
                data = t.extract()
                info["tables"].append({"page": page.number + 1, "rows": len(data), "columns": t.col_count})
                for row, texts in zip(t.rows, data):
                    cells = [(tuple(b), x or "") for b, x in zip(row.cells, texts) if b is not None]
                    if is_header_row([x for _, x in cells], hwords):
                        info["header_rows_dropped"] += 1
                        continue
                    mapped = map_cells(cells, bounds, join)
                    if any(mapped):
                        rows.append(mapped)
    finally:
        doc.close()
        for k, v in saved.items():
            setattr(mtable, k, v)
    return rows, info


def extract_case(tool: str, tables_dir: str, case_id: str) -> tuple[list[dict], dict]:
    spec = load_spec(tables_dir, case_id)
    bounds, hwords = column_bounds(case_id, spec), header_words(spec)
    path = os.path.join(tables_dir, case_id, "document.pdf")
    if tool == "pdfplumber_lines":
        raw, info = run_pdfplumber(path, bounds, hwords, None)
    elif tool == "pdfplumber_text":
        raw, info = run_pdfplumber(path, bounds, hwords, TEXT_STRATEGY)
    elif tool in ("pymupdf", "pymupdf_plainbbox"):
        raw, info = run_pymupdf(path, bounds, hwords, plain_bboxes=tool == "pymupdf_plainbbox")
    else:
        raise ValueError(tool)
    names = [c["name"] for c in printed_columns(spec)]
    rows = []
    for r in raw:
        row = {c["name"]: "" for c in spec["columns"]}
        row.update(dict(zip(names, r)))
        rows.append(row)
    return rows, info


def generic_cleanup(rows: list[dict], spec: dict) -> list[dict]:
    """Three case-agnostic rules (not used for the plain baselines): (1) drop total, subtotal and carried/brought-forward
    lines; (2) a row with no date, id or money value continues the row above, so its text cells are appended there (with
    no row above it is dropped); (3) a blank date or text cell takes the value from the row above (suppressed repeats)."""
    types = {c["name"]: c["type"] for c in spec["columns"]}
    keys = [c for c, t in types.items() if t in ("date", "id", "money")]
    out: list[dict] = []
    for r in rows:
        if any(TOTAL_LINE.match(str(v or "")) for v in r.values()):
            continue
        if not any(str(r.get(c) or "").strip() for c in keys):
            if out:
                for c, t in types.items():
                    if t == "text" and str(r.get(c) or "").strip():
                        out[-1][c] = f"{out[-1][c]} {r[c]}".strip()
            continue
        out.append(dict(r))
    for prev, r in zip(out, out[1:]):
        for c, t in types.items():
            if t in ("date", "text") and not str(r.get(c) or "").strip():
                r[c] = prev[c]
    return out


def classify_extra(values: dict, gold_text_key: str) -> str:
    """Rough kind of an unmatched predicted row, for the report."""
    text = " ".join(str(v) for v in values.values()).lower()
    flat = re.sub(r"\s+", "", text)
    if re.search(r"\btotals?\b|carried\s*forward", text) or ("broughtforward" in flat and "balance" not in flat):
        return "total, subtotal or carried/brought forward line"
    if "weekending" in flat:
        return "group heading line"
    if values and all(_key(v) and _key(v) in gold_text_key for v in values.values()):
        return "wrapped continuation line"
    return "other (text outside the table, or a mangled row)"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="tables")
    ap.add_argument("--out", default="results_tables/tools")
    ap.add_argument("--tools", default=",".join(TOOLS), help=f"comma-separated, from {', '.join(TOOLS + DIAGNOSTIC_TOOLS)}")
    ap.add_argument("--tag", default="", help="suffix for the output directory names, e.g. a tool version")
    ap.add_argument("--cleanup", action="store_true", help="also score each tool after generic_cleanup()")
    args = ap.parse_args(argv)
    with open(os.path.join(args.tables, "manifest.json"), encoding="utf-8") as fh:
        case_ids = [c["case_id"] for c in json.load(fh)["cases"]]
    summary_path = os.path.join(args.out, "summary.json")
    summary = {}
    if os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as fh:
            summary = json.load(fh)
    runs = []
    for tool in args.tools.split(","):
        name = tool + (f"_{args.tag}" if args.tag else "")
        extracted = {cid: extract_case(tool, args.tables, cid) for cid in case_ids}
        runs.append((name, extracted))
        if args.cleanup:
            runs.append((name + "_cleanup", {cid: (generic_cleanup(rows, load_spec(args.tables, cid)), info)
                                             for cid, (rows, info) in extracted.items()}))
    for name, extracted in runs:
        tool_dir = os.path.join(args.out, name)
        os.makedirs(tool_dir, exist_ok=True)
        infos = {}
        for cid, (rows, info) in extracted.items():
            infos[cid] = info
            spec = load_spec(args.tables, cid)
            with open(os.path.join(tool_dir, f"{cid}.csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=[c["name"] for c in spec["columns"]])
                w.writeheader()
                w.writerows(rows)
        r = score(args.tables, tool_dir)
        with open(tool_dir + ".scored.json", "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, ensure_ascii=False)
        entry = {"summary": r["summary"], "cases": {}}
        for cid, pc in r["per_case"].items():
            spec = load_spec(args.tables, cid)
            with open(os.path.join(args.tables, cid, "expected.csv"), encoding="utf-8") as fh:
                gold = list(csv.DictReader(fh))
            gkey = "|".join(_key(row[c["name"]]) for row in gold for c in spec["columns"] if c["type"] == "text")
            kinds: dict[str, int] = {}
            for e in pc["extra_rows"]:
                k = classify_extra(e["values"], gkey)
                kinds[k] = kinds.get(k, 0) + 1
            entry["cases"][cid] = {k: pc[k] for k in ("cell_accuracy", "rows_exact", "rows_expected", "rows_extra", "rows_missing", "table_exact")}
            entry["cases"][cid].update({"per_column": pc["per_column"], "missing_rows": pc["missing_rows"], "extra_kinds": kinds,
                                        "tool": infos[cid]})
        summary[name] = entry
        s = r["summary"]
        print(f"\n{name}: cells {s['cell_accuracy']:.1%}, rows exact {s['rows_exact']}/{s['rows_expected']}, extra {s['rows_extra']}, "
              f"missing {s['rows_missing']}, tables exact {s['tables_exact']}/{s['cases']}")
        for cid, c in entry["cases"].items():
            print(f"  {cid}: cells {c['cell_accuracy']:.0%}  rows exact {c['rows_exact']}/{c['rows_expected']}  extra {c['rows_extra']}  "
                  f"missing {c['rows_missing']}  exact={'yes' if c['table_exact'] else 'no'}  tables found {len(c['tool']['tables'])}")
    os.makedirs(args.out, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print("wrote", summary_path)


if __name__ == "__main__":
    main()

"""Score table extractions for the tables track against tables/<case>/expected.csv.

Predictions are either a directory of CSV files named <case_id>.csv, or one JSON file
  {"extractor": "name", "description": "...", "cases": {"TB-001": {"rows": [{column: value, ...}, ...]}}}
(a case may give "csv": "<csv text>" instead of "rows", or be a bare list of rows or a bare CSV string; a row may be a
list of values in column order). Columns are matched one by one, by the column names in spec.json and then by the
printed headers (case, spaces and punctuation ignored); a CSV whose header is not found is read by position. Blank
lines, an Excel "sep=," line and title lines above the header are skipped; rows with every column blank are dropped.
Files may be UTF-8 (with or without a BOM), UTF-16 with a BOM, or Windows-1252.

Predicted rows are aligned to the expected rows in document order (dynamic programming over the number of matching
non-blank expected cells, ties broken by the number of matching cells including blanks), so a missing or an extra row
costs only itself and a junk row cannot pair with a gold row on shared blanks alone. Per case:
  cell_accuracy  right cells / ((expected rows + extra rows) x columns): a blank expected cell must stay blank, and an
                 extra predicted row is a row of wrong cells, so duplicated or padded rows lower it and two versions
                 of each row score no better than the two versions would on average alone. The headline number.
  cell_recall    right cells / expected cells, extra rows ignored (per_column is the same, column by column);
  rows exactly right, extra rows, missing rows, whether the whole table is exact, and empty_columns: columns blank in
  every predicted row (usually a header or key that did not match).

Cells: dates in any common format, numeric dates day first as in the UK (01/02/2026 is 1 February; 2-digit years as
Python's %y); money must be one amount (£ and GBP ignored; negative in brackets, with a leading or trailing minus or
dash, or with a CR suffix; "nil" is 0; a blank cell must be empty, so "0", "-" and "n/a" are not blank); ids ignore
case, spaces, dash variants, and leading zeros when all digits; text ignores case, spacing, punctuation, hyphenation,
&/and and Limited/Ltd and allows a small spelling slip in a word, but a dropped, added or changed word or number is
wrong (a wrapped line that went missing, "Ltd" cut off, the next cell's text merged in, Ward 3 for Ward 4).

Run:  python -m crtest.score_tables --pred results_tables/my_extractor.json [--tables tables] [--out ...]
"""
from __future__ import annotations

import argparse
import codecs
import csv
import io
import json
import math
import os
import re
import sys
from difflib import SequenceMatcher

from .normalise import norm_text, parse_date

TEXT_SIMILARITY = 0.92  # character similarity (of normalised text) a text cell needs at least
WORD_SLIP = 0.8         # ...and each changed word must still be this similar to count as a spelling slip
HEADER_SCAN = 10        # how many rows above a CSV header (title lines) may be skipped

BOM = chr(0xFEFF)
_INVISIBLE = (0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060, 0x00AD)   # BOM, zero-width space/non-joiner/joiner, word joiner, soft hyphen
_DASHES = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212, 0xFE63, 0xFF0D)   # hyphens, figure/en/em dash, minus signs
_SPACES = (0x00A0, 0x2007, 0x2009, 0x202F)   # no-break, figure, thin and narrow no-break spaces
_CLEAN = {**dict.fromkeys(_INVISIBLE, None), **dict.fromkeys(_DASHES, "-"), **dict.fromkeys(_SPACES, " ")}


def clean(v) -> str:
    """str(v) without BOMs, zero-width characters or soft hyphens, with dash variants as '-' and odd spaces as ' '."""
    return str(v).translate(_CLEAN)


def blank(v) -> bool:
    return v is None or not clean(v).strip()


def load_spec(tables_dir: str, case_id: str) -> dict:
    with open(os.path.join(tables_dir, case_id, "spec.json"), encoding="utf-8") as fh:
        return json.load(fh)


def decode(data: bytes) -> str:
    """Text of a prediction file: UTF-16 if it starts with a UTF-16 BOM (PowerShell's Out-File), else UTF-8 with or
    without a BOM, else Windows-1252 (Excel's plain "CSV" on Windows writes £ as byte 0xA3)."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_csv_text(text: str) -> list[list[str]]:
    try:
        return list(csv.reader(io.StringIO(text.lstrip(BOM))))
    except csv.Error as e:
        raise ValueError(f"CSV error: {e}") from None


def _key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(s).lower())


def _lookups(spec: dict) -> tuple[dict, dict]:
    return ({_key(c["name"]): c["name"] for c in spec["columns"]},
            {_key(c["printed_header"]): c["name"] for c in spec["columns"]})


def _header(cells: list[str], spec: dict) -> tuple[list, set]:
    """Map each header cell to a column, by column name first, then by printed header; a repeated column is ignored."""
    by_name, by_printed = _lookups(spec)
    mapping, kinds = [], set()
    for h in cells:
        k = _key(h)
        name, kind = (by_name[k], "names") if k in by_name else (by_printed[k], "printed headers") if k in by_printed else (None, None)
        if name in mapping:
            name = None
        if name:
            kinds.add(kind)
        mapping.append(name)
    return mapping, kinds


def _skippable(row: list[str]) -> bool:
    """A blank line, or Excel's 'sep=,' delimiter hint."""
    cells = [str(x).strip() for x in row]
    return not any(cells) or (cells[0].lower().startswith("sep=") and not any(cells[1:]))


def _fill_by_position(mapping: list, cols: list[str]) -> bool:
    """A header in column order with a title spelled differently: when every matched cell sits at its own column's
    position, an unmatched cell takes the column at its position. Returns whether any cell was filled."""
    if any(name and (x >= len(cols) or cols[x] != name) for x, name in enumerate(mapping)):
        return False
    filled = False
    for x, name in enumerate(mapping):
        if name is None and x < len(cols) and cols[x] not in mapping:
            mapping[x], filled = cols[x], True
    return filled


def _looks_like_header(row: list[str], spec: dict) -> bool:
    """A first line read by position that is column titles nobody matched: most cells filled, and every filled date or
    money cell is text that does not parse."""
    cells = list(zip(spec["columns"], row))
    typed = [(c["type"], v) for c, v in cells if c["type"] in ("date", "money") and not blank(v)]
    filled = sum(1 for _c, v in cells if not blank(v))
    return (filled >= max(2, len(spec["columns"]) // 2) and bool(typed)
            and all(str(norm_cell(t, v)).startswith("?") for t, v in typed))


def rows_from_csv(table: list[list[str]], spec: dict) -> tuple[list[dict], str]:
    cols = [c["name"] for c in spec["columns"]]
    start = 0
    while start < len(table) and _skippable(table[start]):
        start += 1
    mapping, how, first = list(cols), "position", start   # no header found: the first line is data
    for i in range(start, min(len(table), start + HEADER_SCAN)):
        m, kinds = _header(table[i], spec)
        if sum(1 for x in m if x) >= max(1, len(cols) // 2):
            mapping, how, first = m, " and ".join(sorted(kinds)), i + 1
            if _fill_by_position(mapping, cols):
                how += " and position"
            break
        if sum(1 for x in table[i] if str(x).strip()) > 1:
            break   # a data line before any header: there is no header (only one-cell title lines are skipped)
    if how == "position" and first < len(table) and _looks_like_header(table[first], spec):
        how, first = "position (first line read as a header)", first + 1
    out = []
    for r in table[first:]:
        row = {c: "" for c in cols}
        for name, v in zip(mapping, r):
            if name:
                row[name] = v
        if not all(blank(v) for v in row.values()):
            out.append(row)
    return out, how


def rows_from_objects(items: list, spec: dict) -> list[dict]:
    """JSON rows to {column: value}. Keys are matched like CSV headers, an exact column name first; a row given as a
    list is read in column order; anything else is not a row."""
    cols = [c["name"] for c in spec["columns"]]
    by_name, by_printed = _lookups(spec)
    out = []
    for r in items:
        if isinstance(r, list):
            row = dict(zip(cols, r))
        elif isinstance(r, dict):
            row = {c: r[c] for c in cols if c in r}
            for lookup in (by_name, by_printed):
                for k, v in r.items():
                    name = lookup.get(_key(k))
                    if name and name not in row:
                        row[name] = v
        else:
            continue
        out.append({c: row.get(c) for c in cols})
    return out


_AMOUNT = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d{1,3}(?: \d{3})+|\d+)(?:\.\d*)?|\.\d+")


def money(v) -> float | None:
    """The amount in a money cell, or None when the cell is not exactly one amount.

    £ and GBP are ignored and thousands may be grouped by commas or spaces. Negative: in brackets, a leading or trailing
    minus (any dash), or a CR suffix (DR is positive). "nil" is 0. Not amounts: "-", two numbers ("3,240.00 15,720.00",
    a merged cell), other currencies, words, "£1.85m", continental "1.250,00" (it is not 1.25)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else None
    s = re.sub(r"\s+", " ", re.sub(r"(?i)£|gbp", " ", clean(v))).strip()
    if s.lower() == "nil":
        return 0.0
    neg = False
    m = re.fullmatch(r"(?i)(.+?) ?(cr|dr)\.?", s)
    if m:
        s, neg = m.group(1).strip(), m.group(2).lower() == "cr"
    for _ in range(4):
        if len(s) > 1 and s[0] == "(" and s[-1] == ")":
            s, neg = s[1:-1].strip(), True
        elif s[:1] == "-":
            s, neg = s[1:].strip(), True
        elif s[-1:] == "-":
            s, neg = s[:-1].strip(), True
        elif s[:1] == "+":
            s = s[1:].strip()
        else:
            break
    if not _AMOUNT.fullmatch(s):
        return None
    x = float(s.replace(",", "").replace(" ", ""))
    return -x if neg else x


def norm_id(v) -> str:
    """Case, spaces and dash variants ignored; an all-digit id also ignores leading zeros and a spreadsheet's '.0'."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = re.sub(r"\s+", "", clean(v)).upper()
    m = re.fullmatch(r"0*(\d+?)(?:\.0+)?", s)
    return m.group(1) if m else s


def text_match(a: str, b: str) -> bool:
    """a, b: normalised text (norm_text). Equal, or equal but for spacing (hyphenation, words joined at a line break),
    or close with only spelling slips: never a dropped, added or changed word, or a changed number."""
    if a == b or a.replace(" ", "") == b.replace(" ", ""):
        return True
    if 2 * min(len(a), len(b)) < TEXT_SIMILARITY * (len(a) + len(b)):
        return False   # the lengths alone rule it out (and a huge cell costs nothing)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.quick_ratio() < TEXT_SIMILARITY or sm.ratio() < TEXT_SIMILARITY:
        return False
    ta, tb = a.split(), b.split()
    for op, i1, i2, j1, j2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op != "replace":
            return False   # a word dropped or added: a lost wrapped line, "Ltd" cut off, text from another cell
        wa, wb = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        if re.sub(r"\D", "", wa) != re.sub(r"\D", "", wb):
            return False   # a number changed: Ward 3 for Ward 4, (12 no.) for (22 no.)
        if SequenceMatcher(None, wa, wb, autojunk=False).ratio() < WORD_SLIP:
            return False
    return True


def norm_cell(typ: str, v):
    """None for a blank cell, else the value compared: ISO date, float, id, or normalised text; '?<raw>' when a date or
    money cell cannot be read."""
    if blank(v):
        return None
    if typ == "date":
        return parse_date(clean(v)) or ("?" + str(v))
    if typ == "money":
        x = money(v)
        return round(x, 2) if x is not None else "?" + str(v)
    if typ == "id":
        return norm_id(v)
    return norm_text(clean(v))


def _same(typ: str, g, p) -> bool:
    """Compare two norm_cell values."""
    if g is None or p is None:
        return g is None and p is None
    if typ == "money":
        return isinstance(g, float) and isinstance(p, float) and abs(g - p) <= 0.005
    if typ == "text":
        return text_match(g, p)
    return g == p


def cell_ok(typ: str, gold, pred) -> bool:
    return _same(typ, norm_cell(typ, gold), norm_cell(typ, pred))


def score_case(spec: dict, gold: list[dict], pred: list[dict]) -> dict:
    cols = [(c["name"], c["type"]) for c in spec["columns"]]
    names = [c for c, _t in cols]
    k = len(cols)
    pred = [p for p in pred if not all(blank(p.get(c)) for c in names)]
    n, m = len(gold), len(pred)
    gn = [[norm_cell(t, g.get(c)) for c, t in cols] for g in gold]
    pn = [[norm_cell(t, p.get(c)) for c, t in cols] for p in pred]
    ok = [[[_same(t, gn[i][x], pn[j][x]) for x, (_c, t) in enumerate(cols)] for j in range(m)] for i in range(n)]
    # Alignment weight: matched NON-blank expected cells first, so junk rows cannot pair on shared blanks; then all
    # matched cells, so of two copies of a row the one that also keeps the blank cells blank is paired. big exceeds
    # any possible sum of the second term, which makes the order strict.
    big = n * k + 1
    w = [[0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            content = sum(1 for x in range(k) if ok[i][j][x] and gn[i][x] is not None)
            if content:
                w[i][j] = content * big + sum(ok[i][j])
    S = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(S[i - 1][j], S[i][j - 1])
            if w[i - 1][j - 1] > 0:
                best = max(best, S[i - 1][j - 1] + w[i - 1][j - 1])
            S[i][j] = best
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        if w[i - 1][j - 1] > 0 and S[i][j] == S[i - 1][j - 1] + w[i - 1][j - 1]:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif S[i][j] == S[i - 1][j]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    matched_g = {a for a, _ in pairs}
    matched_p = {b for _, b in pairs}
    per_col = {c: [0, n] for c in names}
    cells_ok = rows_exact = 0
    errors = []
    for a, b in pairs:
        row_ok = True
        for x, c in enumerate(names):
            if ok[a][b][x]:
                cells_ok += 1
                per_col[c][0] += 1
            else:
                row_ok = False
                errors.append({"row": a + 1, "column": c, "expected": gold[a].get(c, ""), "got": pred[b].get(c, "")})
        rows_exact += row_ok
    missing = [a + 1 for a in range(n) if a not in matched_g]
    extra = [{"pred_row": b + 1, "values": {c: pred[b].get(c, "") for c in names if not blank(pred[b].get(c))}}
             for b in range(m) if b not in matched_p]
    scored_cells = (n + len(extra)) * k
    return {
        "case_id": spec["case_id"], "rows_expected": n, "rows_predicted": m, "rows_exact": rows_exact,
        "rows_missing": len(missing), "rows_extra": len(extra),
        "cell_accuracy": round(cells_ok / scored_cells, 3) if scored_cells else None,
        "cell_recall": round(cells_ok / (n * k), 3) if n * k else None,
        "table_exact": rows_exact == n and not extra,
        "per_column": {c: round(v[0] / v[1], 3) if v[1] else None for c, v in per_col.items()},
        "empty_columns": [c for c in names if m and all(blank(p.get(c)) for p in pred)],
        "missing_rows": missing, "extra_rows": extra[:60], "cell_errors": errors[:200],
    }


def load_gold(tables_dir: str, case_id: str, spec: dict) -> list[dict]:
    with open(os.path.join(tables_dir, case_id, "expected.csv"), "rb") as fh:
        return rows_from_csv(read_csv_text(decode(fh.read())), spec)[0]


def _case_prediction(c):
    """One case of a predictions JSON -> (kind, value): ("rows", list), ("csv", text), ("bad", reason) or None."""
    if isinstance(c, list):
        return "rows", c
    if isinstance(c, str):
        return "csv", c
    if not isinstance(c, dict):
        return None
    if c.get("rows") is not None:
        return ("rows", c["rows"]) if isinstance(c["rows"], list) else ("bad", f'"rows" is a {type(c["rows"]).__name__}, not a list')
    if c.get("csv") is not None:
        return ("csv", c["csv"]) if isinstance(c["csv"], str) else ("bad", f'"csv" is a {type(c["csv"]).__name__}, not a string')
    return None


def load_predictions(pred: str, case_ids: list[str], tables_dir: str) -> tuple[dict, dict]:
    meta, out = {}, {}
    if os.path.isdir(pred):
        meta = {"extractor": os.path.basename(os.path.normpath(pred))}
        for cid in case_ids:
            p = os.path.join(pred, f"{cid}.csv")
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    out[cid] = ("csv", decode(fh.read()))
        return meta, out
    with open(pred, "rb") as fh:
        text = decode(fh.read())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{pred} is not valid JSON: {e}") from None
    if not isinstance(obj, dict):
        raise ValueError(f'{pred}: expected a JSON object {{"extractor": ..., "cases": {{...}}}}, got a {type(obj).__name__}')
    cases = obj.get("cases")
    if isinstance(cases, list):   # [{"case_id": "TB-001", "rows": [...]}, ...]
        cases = {c["case_id"]: c for c in cases if isinstance(c, dict) and isinstance(c.get("case_id"), str)}
    if cases is None:
        cases = {}
    if not isinstance(cases, dict):
        raise ValueError(f'{pred}: "cases" must be an object keyed by case id, got a {type(cases).__name__}')
    meta = {k: obj.get(k) for k in ("extractor", "description", "version", "run_at")}
    for cid, c in cases.items():
        p = _case_prediction(c)
        if p:
            out[cid] = p
    return meta, out


def score(tables_dir: str, pred: str) -> dict:
    with open(os.path.join(tables_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    case_ids = [c["case_id"] for c in manifest["cases"]]
    meta, preds = load_predictions(pred, case_ids, tables_dir)
    per_case = {}
    for cid in case_ids:
        spec = load_spec(tables_dir, cid)
        gold = load_gold(tables_dir, cid, spec)
        how = "missing"
        rows: list[dict] = []
        if cid in preds:
            kind, val = preds[cid]
            try:
                if kind == "csv":
                    rows, how = rows_from_csv(read_csv_text(val), spec)
                elif kind == "rows":
                    rows, how = rows_from_objects(val, spec), "rows"
                else:
                    how = f"unreadable: {val}"
            except ValueError as e:
                how = f"unreadable: {e}"
        r = score_case(spec, gold, rows)
        r["column_mapping"] = how
        per_case[cid] = r
    n_cases = len(per_case)
    summary = dict(meta)
    summary.update({
        "track": "tables", "cases": n_cases,
        "cell_accuracy": round(sum(r["cell_accuracy"] or 0 for r in per_case.values()) / n_cases, 3) if n_cases else None,
        "cell_recall": round(sum(r["cell_recall"] or 0 for r in per_case.values()) / n_cases, 3) if n_cases else None,
        "rows_exact": sum(r["rows_exact"] for r in per_case.values()),
        "rows_expected": sum(r["rows_expected"] for r in per_case.values()),
        "rows_extra": sum(r["rows_extra"] for r in per_case.values()),
        "rows_missing": sum(r["rows_missing"] for r in per_case.values()),
        "tables_exact": sum(1 for r in per_case.values() if r["table_exact"]),
    })
    return {"summary": summary, "per_case": per_case}


def _pct(x, places: int) -> str:
    return "n/a" if x is None else f"{x:.{places}%}"


def print_summary(r: dict) -> None:
    s = r["summary"]
    print(f"\n{s.get('extractor')}: cell accuracy {_pct(s['cell_accuracy'], 1)} (recall {_pct(s.get('cell_recall'), 1)}), "
          f"rows exact {s['rows_exact']}/{s['rows_expected']}, extra rows {s['rows_extra']}, missing rows {s['rows_missing']}, "
          f"tables exact {s['tables_exact']}/{s['cases']}")
    for cid, c in r["per_case"].items():
        print(f"{cid}: cells {_pct(c['cell_accuracy'], 0)} (recall {_pct(c.get('cell_recall'), 0)})  rows exact "
              f"{c['rows_exact']}/{c['rows_expected']}  extra {c['rows_extra']}  missing {c['rows_missing']}  "
              f"exact={'yes' if c['table_exact'] else 'no'}  ({c['column_mapping']})")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="tables")
    ap.add_argument("--pred", required=True, help="predictions JSON, or a directory of <case_id>.csv files")
    ap.add_argument("--out", help="default: <pred>.scored.json")
    args = ap.parse_args(argv)
    try:
        r = score(args.tables, args.pred)
    except (OSError, ValueError) as e:
        sys.exit(f"score_tables: {e}")
    if args.out:
        out = args.out
    elif os.path.isdir(args.pred):
        out = os.path.normpath(args.pred) + ".scored.json"
    else:
        root, ext = os.path.splitext(args.pred)
        out = (root if ext.lower() == ".json" else args.pred) + ".scored.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False)
    print_summary(r)
    print("wrote", out)


if __name__ == "__main__":
    main()

"""Tables-track scorer (crtest.score_tables): the behaviour the leaderboard relies on, and the defects found by
red-teaming it. Each defect test says what the input used to score. Run:  python -m pytest -q tests/test_tables.py
"""
import codecs
import csv
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys

import pytest

from crtest import normalise
from crtest import score_tables as st
from crtest.extract_tables_naive import naive_rows

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.path.join(ROOT, "tables")
with open(os.path.join(TABLES, "manifest.json"), encoding="utf-8") as _fh:
    CASES = [c["case_id"] for c in json.load(_fh)["cases"]]
BOM, ZWSP, NBSP = chr(0xFEFF), chr(0x200B), chr(0xA0)
EN_DASH, EM_DASH, NB_HYPHEN, MINUS, RSQUO = chr(0x2013), chr(0x2014), chr(0x2011), chr(0x2212), chr(0x2019)


def spec(cid):
    return st.load_spec(TABLES, cid)


def gold(cid):
    return st.load_gold(TABLES, cid, spec(cid))


def cols(cid):
    return [c["name"] for c in spec(cid)["columns"]]


def printed(cid):
    return [c["printed_header"] for c in spec(cid)["columns"]]


def score_rows(cid, rows):
    return st.score_case(spec(cid), gold(cid), rows)


def to_csv(rows, columns, header=None):
    """rows as CSV text, one column per name in columns; header=None writes no header line."""
    f = io.StringIO()
    w = csv.writer(f)
    if header is not None:
        w.writerow(header)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    return f.getvalue()


def parse_csv(cid, text):
    return st.rows_from_csv(st.read_csv_text(text), spec(cid))


def write_json(tmp_path, obj, name="pred.json"):
    p = tmp_path / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def typed(cid, row):
    """A gold row as an LLM returns it: numbers for money, null for blanks."""
    out = {}
    for c in spec(cid)["columns"]:
        v = row[c["name"]]
        out[c["name"]] = None if v == "" else float(v) if c["type"] == "money" else v
    return out


def naive(cid):
    with open(os.path.join(TABLES, cid, "text.txt"), encoding="utf-8") as fh:
        return naive_rows(fh.read(), spec(cid))


# ---------------------------------------------------------------- behaviour the leaderboard relies on

def test_gold_scores_100_percent_as_csv_files_and_as_json(tmp_path):
    d = tmp_path / "gold"
    d.mkdir()
    pred = {"extractor": "gold-echo", "cases": {}}
    for cid in CASES:
        shutil.copy(os.path.join(TABLES, cid, "expected.csv"), d / f"{cid}.csv")
        pred["cases"][cid] = {"rows": [typed(cid, r) for r in gold(cid)]}
    for p in (str(d), write_json(tmp_path, pred)):
        s = st.score(TABLES, p)["summary"]
        assert s["cell_accuracy"] == 1.0
        assert s["tables_exact"] == s["cases"] == len(CASES)
        assert s["rows_exact"] == s["rows_expected"] and s["rows_extra"] == 0 and s["rows_missing"] == 0


def test_wrong_csv_scores_the_same_as_the_naive_rows():
    for cid in CASES:
        with open(os.path.join(TABLES, cid, "wrong.csv"), encoding="utf-8") as fh:
            rows, how = parse_csv(cid, fh.read())
        assert how == "names"
        assert score_rows(cid, rows) == score_rows(cid, naive(cid)), cid


# What the naive text-dump baseline (crtest.extract_tables_naive) scores on the current cases. Update when the
# cases change; a change here without a case change means the scorer changed.
NAIVE = {
    "TB-001": dict(cell_accuracy=0.235, cell_recall=0.47, rows_exact=0, rows_extra=11, rows_missing=0),
    "TB-002": dict(cell_accuracy=0.079, cell_recall=0.188, rows_exact=2, rows_extra=22, rows_missing=12),
    "TB-003": dict(cell_accuracy=0.256, cell_recall=0.683, rows_exact=1, rows_extra=20, rows_missing=0),   # 0.2.0: no duplicate page-1 header
    "TB-004": dict(cell_accuracy=0.245, cell_recall=0.638, rows_exact=0, rows_extra=24, rows_missing=0),
}


def test_naive_baseline_scores_what_it_scores():
    for cid in CASES:
        r = score_rows(cid, naive(cid))
        assert {k: r[k] for k in NAIVE[cid]} == NAIVE[cid], cid
        assert r["table_exact"] is False
    assert score_rows("TB-004", naive("TB-004"))["empty_columns"] == ["week_ending"]   # the date is a group heading


def test_missing_and_empty_predictions_score_zero(tmp_path):
    none = tmp_path / "none"
    none.mkdir()
    for p in (str(none), write_json(tmp_path, {"cases": {}}, "a.json"),
              write_json(tmp_path, {"cases": {cid: {"rows": []} for cid in CASES}}, "b.json")):
        s = st.score(TABLES, p)["summary"]
        assert s["cell_accuracy"] == 0 and s["rows_exact"] == 0 and s["rows_missing"] == s["rows_expected"]


def test_a_missing_row_costs_only_itself():
    g = gold("TB-002")
    r = score_rows("TB-002", g[:5] + g[6:])
    assert (r["rows_exact"], r["rows_missing"], r["rows_extra"], r["missing_rows"]) == (15, 1, 0, [6])


def test_both_identical_dunmore_rows_are_needed():
    g = gold("TB-002")
    r = score_rows("TB-002", g[:6] + g[7:])   # the second Dunmore row dropped as a "duplicate"
    assert (r["rows_exact"], r["rows_missing"]) == (15, 1)


def test_rows_out_of_document_order_cost_one_missing_and_one_extra_row():
    g = gold("TB-001")
    p = list(g)
    p[3], p[4] = p[4], p[3]
    r = score_rows("TB-001", p)
    assert (r["rows_exact"], r["rows_missing"], r["rows_extra"]) == (10, 1, 1)


def test_junk_rows_do_not_pair_with_gold_rows_on_shared_blank_cells():
    s, g = spec("TB-001"), gold("TB-001")
    junk = {"details": "Page 1 of 1"}   # blank where the brought-forward row is blank (ref, debit, credit)
    r = st.score_case(s, [g[0]], [junk])
    assert (r["rows_missing"], r["rows_extra"], r["cell_accuracy"]) == (1, 1, 0)


# ---------------------------------------------------------------- defects: padding, duplicates, alignment

def test_duplicating_every_row_no_longer_scores_100_percent():
    g = gold("TB-001")
    r = score_rows("TB-001", [row for row in g for _ in range(2)])
    assert (r["rows_exact"], r["rows_extra"], r["table_exact"]) == (11, 11, False)
    assert r["cell_accuracy"] == 0.5   # was 1.0: the copies are extra rows, i.e. rows of wrong cells
    assert r["cell_recall"] == 1.0


def test_two_versions_of_every_row_cannot_beat_either_version():
    g = gold("TB-001")
    in_debit, in_credit, hedged = [], [], []
    for row in g:
        amount = row["debit_gbp"] or row["credit_gbp"]
        a = dict(row, debit_gbp=amount, credit_gbp="")
        b = dict(row, debit_gbp="", credit_gbp=amount)
        in_debit.append(a)
        in_credit.append(b)
        hedged += [a, b] if amount else [a]
    a, b, h = (score_rows("TB-001", x)["cell_accuracy"] for x in (in_debit, in_credit, hedged))
    assert h < min(a, b)   # was 1.0, above both versions (0.879 and 0.818)


def test_an_extra_row_lowers_cell_accuracy():
    totals = {"details": "Totals", "debit_gbp": "10710.95", "credit_gbp": "20325.00"}
    r = score_rows("TB-001", gold("TB-001") + [totals])
    assert r["rows_extra"] == 1 and r["cell_accuracy"] == round(66 / 72, 3)   # was 1.0


def test_blank_rows_are_dropped_from_json_as_they_are_from_csv(tmp_path):
    g = gold("TB-001")
    rows = g[:3] + [{c: "" for c in cols("TB-001")}, {"date": None, "details": "  "}, {}] + g[3:]
    r = st.score(TABLES, write_json(tmp_path, {"cases": {"TB-001": {"rows": rows}}}))["per_case"]["TB-001"]
    assert (r["rows_predicted"], r["rows_extra"], r["table_exact"]) == (11, 0, True)   # was 14 rows, 3 extra, not exact


def test_alignment_pairs_the_right_copy_of_a_duplicated_row():
    s, g = spec("TB-001"), gold("TB-001")
    right, worse = dict(g[1]), dict(g[1], credit_gbp="3240.00")   # same non-blank cells, one blank cell filled in
    for pred in ([right, worse], [worse, right]):
        r = st.score_case(s, [g[1]], pred)
        assert (r["rows_exact"], r["rows_extra"]) == (1, 1), pred   # [right, worse] paired the worse copy


def test_summary_gives_accuracy_and_recall(tmp_path):
    obj = {"cases": {cid: {"rows": [r for r in gold(cid) for _ in range(2)]} for cid in CASES}}
    s = st.score(TABLES, write_json(tmp_path, obj))["summary"]
    assert (s["cell_accuracy"], s["cell_recall"], s["rows_extra"]) == (0.5, 1.0, s["rows_expected"])


# ---------------------------------------------------------------- defects: money

@pytest.mark.parametrize("text,value", [
    # already right
    ("1,250.00", 1250.0), ("£1,250.00", 1250.0), ("1250", 1250), ("1 250.00", 1250.0), ("1,250.00 GBP", 1250.0),
    ("(146.10)", -146.1), ("-146.10", -146.1), (MINUS + "146.10", -146.1), ("-£1,250.00", -1250.0), ("0", 0), ("0.00", 0),
    (3240, 3240), (-146.1, -146.1),
    # used to lose the sign or not parse
    ("£-1,250.00", -1250.0), ("1,250.00-", -1250.0), ("GBP -1,250.00", -1250.0), ("£(146.10)", -146.1),
    ("(£146.10)", -146.1), (EN_DASH + "146.10", -146.1), ("146.10 CR", -146.1), ("146.10CR", -146.1), ("146.10 Dr", 146.1),
    ("nil", 0), ("+1,250.00", 1250.0), ("1" + NBSP + "250.00", 1250.0),
])
def test_money_amounts(text, value):
    assert st.money(text) == pytest.approx(value)


@pytest.mark.parametrize("text", [
    "1.250,00", "1 250,00", "12,48", "1,2,3",                   # continental or broken grouping: were 1.25, 125000, 1248, 123
    "3,240.00 15,720.00", "INV-40871", "$3,240.00", "£1.85m",   # not one GBP amount: were 3240, 40871, 3240, 1850000
    "(146.10", "1e3", "-", EM_DASH, "n/a", True, float("nan"), float("inf"),
])
def test_money_rejects_what_is_not_one_amount(text):
    assert st.money(text) is None


def test_blank_money_cells_must_stay_blank():
    assert st.cell_ok("money", "", "") and st.cell_ok("money", "", None)
    for filled in ("0", "0.00", "-", "nil", "n/a", 0):
        assert not st.cell_ok("money", "", filled), filled
    assert st.cell_ok("money", "0.00", "nil") and st.cell_ok("money", "0.00", 0)   # 'nil' was wrong
    assert not st.cell_ok("money", "0.00", "") and not st.cell_ok("money", "0.00", "-")


def test_money_signs_and_merged_cells():
    assert st.cell_ok("money", "-1250.00", "£-1,250.00")             # was +1250
    assert st.cell_ok("money", "-146.10", "146.10 CR")               # was +146.10
    assert not st.cell_ok("money", "146.10", "146.10 CR")            # was right
    assert not st.cell_ok("money", "3240.00", "3,240.00 15,720.00")  # a merged Debit + Balance cell was right
    assert not st.cell_ok("money", "-146.10", "146.10")


# ---------------------------------------------------------------- defects: dates

@pytest.mark.parametrize("text,iso", [
    # already right
    ("01/02/2026", "2026-02-01"), ("1/2/2026", "2026-02-01"), ("01.02.2026", "2026-02-01"), ("2026-02-01", "2026-02-01"),
    ("1 February 2026", "2026-02-01"), ("1st Feb 2026", "2026-02-01"), ("01-Feb-2026", "2026-02-01"),
    ("February 1, 2026", "2026-02-01"), ("Week ending Friday 3 July 2026", "2026-07-03"), ("2026-02-01 00:00:00", "2026-02-01"),
    # used to be unreadable
    ("01/02/26", "2026-02-01"), ("01-02-2026", "2026-02-01"), ("2026-02-01T00:00:00", "2026-02-01"), ("2026-2-1", "2026-02-01"),
    ("2026/02/01", "2026-02-01"), ("February 1st, 2026", "2026-02-01"), ("1 Sept 2026", "2026-09-01"),
    ("1st Oct. 2026", "2026-10-01"), ("01-Oct-26", "2026-10-01"), (EN_DASH.join(["01", "10", "2026"]), "2026-10-01"),
])
def test_dates_are_read_day_first(text, iso):
    assert st.norm_cell("date", text) == iso


@pytest.mark.parametrize("text", ["31/02/2026", "13/13/2026", "3 Decision 2026", "1 Mayor 2026", "46296", "Balance brought forward"])
def test_things_that_are_not_dates(text):
    assert str(st.norm_cell("date", text)).startswith("?")   # 31/02 was '2026-02-31'; 'Decision' was December


def test_dates_in_us_order_are_wrong_in_a_uk_table():
    assert not st.cell_ok("date", "2026-02-01", "02/01/2026")   # 2 January
    assert not st.cell_ok("date", "2026-10-23", "10/23/2026")
    assert st.cell_ok("date", "2026-10-06", "06/10/2026")


def test_parse_date_takes_datetimes():
    assert normalise.parse_date(dt.datetime(2026, 2, 1, 9, 30)) == "2026-02-01"   # was '2026-02-01T09:30:00'
    assert normalise.parse_date(dt.date(2026, 2, 1)) == "2026-02-01"


# ---------------------------------------------------------------- defects: ids

@pytest.mark.parametrize("gold_id,pred,same", [
    ("INV-40871", "inv-40871", True), ("INV-40871", " INV- 40871 ", True), ("5100231", 5100231, True),   # already right
    ("1", "01", True), ("1", 1.0, True), ("5100231", 5100231.0, True), ("5100231", "5100231.0", True),
    ("INV-40871", "INV" + EN_DASH + "40871", True), ("HWY-310", "HWY" + NB_HYPHEN + "310", True), ("1", BOM + "1", True), ("CN-2207", "CN-2207" + ZWSP, True),
    ("HW-7101", "HW-07101", False), ("5100231", "5100232", False), ("INV-40871", "INV40871", False), ("1", "1.5", False),
    ("CN-2207", "CN-2207A", False), ("1", "", False),
])
def test_ids(gold_id, pred, same):
    assert st.cell_ok("id", gold_id, pred) is same


# ---------------------------------------------------------------- defects: text

LOST_LAST_LINE = [   # (expected, the cell with its last wrapped line lost): every one scored right before
    ("Planned preventative maintenance, Riverside offices: fire alarm and emergency lighting tests",
     "Planned preventative maintenance, Riverside offices: fire alarm and emergency lighting"),
    ("Halbrook Leisure Operations Ltd", "Halbrook Leisure Operations"),
    ("Fenwick Grounds Maintenance Ltd", "Fenwick Grounds Maintenance"),
    ("Dunmore Care Partnership CIC", "Dunmore Care Partnership"),
    ("Pothole repairs, Victoria Square and Market Street (14 no.)", "Pothole repairs, Victoria Square and Market Street"),
    ("Line painting refresh, school keep-clear markings (6 schools)", "Line painting refresh, school keep-clear markings (6"),
    ("Street lighting: column replacement (3 no.), Chapel Street", "Street lighting: column replacement (3 no.), Chapel"),
]
CHANGED_NUMBER = [   # every one scored right before
    ("Gully emptying, Ward 3 cyclic programme", "Gully emptying, Ward 4 cyclic programme"),
    ("Pothole repairs, Ward 5 (22 no.)", "Pothole repairs, Ward 5 (12 no.)"),
    ("Car park lighting: replace 6 failed LED lanterns, columns 4 to 9", "Car park lighting: replace 8 failed LED lanterns, columns 4 to 9"),
    ("Service credit: KPI 3 (emergency response within 2 hours) missed in Q2",
     "Service credit: KPI 3 (emergency response within 2 hours) missed in Q3"),
]
HARMLESS = [
    ("Planned preventative maintenance, Riverside offices: fire alarm and emergency lighting tests",
     "planned  preventative maintenance -- Riverside offices; fire alarm & emergency lighting tests."),
    ("Brightwater Environmental Services Limited", "BRIGHTWATER ENVIRONMENTAL SERVICES LTD"),
    ("Dunmore Care Partnership CIC", "Dunmore Care Partnership Community Interest Company"),
    ("Mobilisation and site set-up", "Mobilisation and site setup"),
    ("Foundations and ground-bearing slab signed off by the Council's structural engineer",
     "Foundations and ground- bearing slab signed off by the Council" + RSQUO + "s structural engineer"),
    ("Containment, cabling and pipework installed and pressure-tested", "Containment, cabling and pipework installed and pressure-\ntested"),
    ("Carriageway resurfacing, Canal Street (inlay 40mm, 1,180 m2), including traffic management",
     "Carriageway resurfacing, Canal Street (inlay 40 mm, 1180 m2), including traffic management"),
    ("Planned preventative maintenance, Riverside offices: fire alarm and emergency lighting tests",
     "Planned preventative maintenance, Riverslde offices: fire alarm and emergency lighting tests"),   # one slip
    ("Grounds maintenance", "Grounds maintenence"),
]


@pytest.mark.parametrize("expected,got", LOST_LAST_LINE + CHANGED_NUMBER)
def test_text_with_a_lost_line_or_a_changed_number_is_wrong(expected, got):
    assert not st.cell_ok("text", expected, got)


@pytest.mark.parametrize("expected,got", HARMLESS)
def test_harmless_text_differences_are_right(expected, got):
    assert st.cell_ok("text", expected, got)


def test_the_cell_split_by_the_page_break():
    g = gold("TB-003")[4]["payment_trigger"]   # milestone 5 (Envelope): page 1 and page 2 halves
    assert st.cell_ok("text", g, g.upper().replace(",", " ,"))
    assert not st.cell_ok("text", g, g.rsplit(" and door seals", 1)[0])   # was right (similarity 0.97)
    assert not st.cell_ok("text", g, g + " Page 2 of 2")                   # footer text merged in: was right
    assert not st.cell_ok("text", g, g.split(", confirmed")[0])            # only the page 1 half


def test_a_supplier_cut_at_its_line_break_makes_the_row_wrong():
    p = [dict(r) for r in gold("TB-002")]
    p[8]["supplier"] = "Halbrook Leisure Operations"   # 'Ltd' wrapped onto the next line and was lost
    r = score_rows("TB-002", p)
    assert (r["rows_exact"], r["per_column"]["supplier"]) == (15, round(15 / 16, 3))   # was 16/16


# ---------------------------------------------------------------- defects: CSV handling

@pytest.mark.parametrize("kind", ["names", "printed", "title case", "names and short printed", "printed and names"])
def test_csv_header_spellings(kind):
    c, p = cols("TB-001"), printed("TB-001")
    header = {"names": c, "printed": p, "title case": [x.replace("_", " ").title() for x in c],
              "names and short printed": ["date", "reference", "details", "debit", "credit", "balance"],  # money columns were dropped
              "printed and names": ["Date", "Ref", "Details", "debit_gbp", "credit_gbp", "balance_gbp"]}[kind]  # Ref was dropped
    rows, how = parse_csv("TB-001", to_csv(gold("TB-001"), c, header))
    assert how != "position" and score_rows("TB-001", rows)["cell_accuracy"] == 1.0


@pytest.mark.parametrize("above", ["\n", "\r\n,,,,,\r\n", "sep=,\n", "TB-001 statement lines\n"])
def test_lines_above_the_header_are_skipped(above):
    c = cols("TB-001")
    rows, how = parse_csv("TB-001", above + to_csv(gold("TB-001"), c, c))
    r = score_rows("TB-001", rows)
    assert (how, r["cell_accuracy"], r["rows_extra"]) == ("names", 1.0, 0)   # a leading blank line scored 0%


def test_a_headerless_csv_keeps_its_rows_above_a_repeated_page_header():
    c = cols("TB-003")
    g = gold("TB-003")
    body = to_csv(g[:4], c) + to_csv([], c, printed("TB-003")) + to_csv(g[4:], c)   # page 2's header repeated as a row
    rows, how = parse_csv("TB-003", body)
    r = score_rows("TB-003", rows)
    assert how == "position" and (r["rows_exact"], r["rows_extra"]) == (12, 1)


def test_an_unrecognised_header_line_is_not_an_extra_row():
    c = cols("TB-001")
    rows, how = parse_csv("TB-001", to_csv(gold("TB-001"), c, ["Posted", "Doc", "Narrative", "Dr", "Cr", "Bal"]))
    r = score_rows("TB-001", rows)
    assert how.startswith("position (first line") and (r["cell_accuracy"], r["rows_extra"]) == (1.0, 0)


def test_a_header_in_column_order_with_one_title_spelled_differently():
    c = cols("TB-001")
    rows, how = parse_csv("TB-001", to_csv(gold("TB-001"), c, ["Date", "Ref", "Description", "Debit", "Credit", "Balance"]))
    assert how == "names and printed headers and position" and score_rows("TB-001", rows)["cell_accuracy"] == 1.0   # details were lost


def test_a_bom_before_the_header():
    c = cols("TB-001")
    rows, how = parse_csv("TB-001", BOM + to_csv(gold("TB-001"), c, c))
    assert how == "names" and score_rows("TB-001", rows)["cell_accuracy"] == 1.0


def test_a_bom_before_headerless_rows_does_not_spoil_the_first_cell():
    c = cols("TB-003")
    rows, how = parse_csv("TB-003", BOM + to_csv(gold("TB-003"), c))
    assert how == "position" and score_rows("TB-003", rows)["cell_accuracy"] == 1.0   # the BOM stuck to milestone 1 made it wrong


def test_headerless_csv_keeps_every_column_even_if_the_first_line_is_short():
    s = {"case_id": "X", "columns": [{"name": n, "printed_header": n.upper(), "type": "text"} for n in ("a", "b", "c")]}
    rows, how = st.rows_from_csv(st.read_csv_text("x\ny,z,w\n"), s)
    assert how == "position" and rows == [{"a": "x", "b": "", "c": ""}, {"a": "y", "b": "z", "c": "w"}]   # b, c were dropped


def test_header_only_csv_is_an_empty_prediction():
    c = cols("TB-001")
    rows, how = parse_csv("TB-001", ",".join(c) + "\r\n")
    assert (rows, how) == ([], "names") and score_rows("TB-001", rows)["rows_missing"] == 11


def test_quoted_newlines_inside_a_cell():
    c = cols("TB-001")
    p = [dict(r, details=r["details"].replace(", ", ",\n")) for r in gold("TB-001")]
    rows, _ = parse_csv("TB-001", to_csv(p, c, c))
    assert score_rows("TB-001", rows)["cell_accuracy"] == 1.0


def test_extra_columns_are_ignored_and_missing_ones_reported():
    c, g = cols("TB-001"), gold("TB-001")
    rows, _ = parse_csv("TB-001", to_csv([dict(r, notes="x") for r in g], c + ["notes"], c + ["notes"]))
    assert score_rows("TB-001", rows)["cell_accuracy"] == 1.0
    no_credit = [x for x in c if x != "credit_gbp"]
    rows, _ = parse_csv("TB-001", to_csv(g, no_credit, no_credit))
    r = score_rows("TB-001", rows)
    assert r["empty_columns"] == ["credit_gbp"] and r["per_column"]["credit_gbp"] == round(7 / 11, 3)


def test_csv_files_saved_by_excel_or_powershell(tmp_path):
    d = tmp_path / "pred"
    d.mkdir()
    (d / "TB-002.csv").write_bytes(to_csv(gold("TB-002"), cols("TB-002"), printed("TB-002")).encode("cp1252"))  # '£' is 0xA3
    (d / "TB-001.csv").write_bytes(to_csv(gold("TB-001"), cols("TB-001"), cols("TB-001")).encode("utf-16"))       # Out-File
    (d / "TB-003.csv").write_bytes((BOM + to_csv(gold("TB-003"), cols("TB-003"), cols("TB-003"))).encode("utf-8"))
    r = st.score(TABLES, str(d))   # the cp1252 file stopped the whole run with UnicodeDecodeError
    for cid in ("TB-001", "TB-002", "TB-003"):
        assert r["per_case"][cid]["cell_accuracy"] == 1.0, cid


def test_an_unreadable_csv_is_reported_not_a_crash(tmp_path):
    d = tmp_path / "pred"
    d.mkdir()
    c = cols("TB-001")
    (d / "TB-001.csv").write_text(",".join(c) + "\n2026-10-01,," + "x" * 200_000 + ",,,12480.00\n", encoding="utf-8")
    (d / "TB-002.csv").write_text(to_csv(gold("TB-002"), cols("TB-002"), cols("TB-002")), encoding="utf-8")
    r = st.score(TABLES, str(d))   # csv.Error 'field larger than field limit' stopped the whole run
    assert r["per_case"]["TB-001"]["column_mapping"].startswith("unreadable")
    assert r["per_case"]["TB-002"]["cell_accuracy"] == 1.0


# ---------------------------------------------------------------- defects: JSON predictions

def test_predictions_json_with_a_bom(tmp_path):
    p = tmp_path / "pred.json"
    p.write_bytes(codecs.BOM_UTF8 + json.dumps({"cases": {"TB-001": {"rows": gold("TB-001")}}}).encode("utf-8"))
    assert st.score(TABLES, str(p))["per_case"]["TB-001"]["cell_accuracy"] == 1.0   # was JSONDecodeError


@pytest.mark.parametrize("raw", ["{not json", "[]", '"TB-001"', '{"cases": "TB-001"}', '{"cases": 3}'])
def test_malformed_predictions_json_is_a_clear_error(tmp_path, raw):
    p = tmp_path / "pred.json"
    p.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="pred.json"):   # was JSONDecodeError or AttributeError
        st.score(TABLES, str(p))


def test_cli_reports_malformed_json_without_a_traceback(tmp_path):
    p = tmp_path / "pred.json"
    p.write_text("{not json", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "crtest.score_tables", "--tables", TABLES, "--pred", str(p),
                        "--out", str(tmp_path / "out.json")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0 and "Traceback" not in r.stderr and "not valid JSON" in r.stderr


def test_prediction_shapes_that_are_accepted(tmp_path):
    cid, g, c, p = "TB-001", gold("TB-001"), cols("TB-001"), printed("TB-001")
    shapes = {
        "rows": {"cases": {cid: {"rows": g}}},
        "csv": {"cases": {cid: {"csv": to_csv(g, c, c)}}},
        "cases as a list": {"cases": [{"case_id": cid, "rows": g}]},                              # crashed
        "a bare list of rows": {"cases": {cid: g}},                                               # scored 0
        "a bare CSV string": {"cases": {cid: to_csv(g, c, c)}},                                   # scored 0
        "rows as lists": {"cases": {cid: {"rows": [[r[x] for x in c] for r in g]}}},              # scored 0
        "keys are printed headers": {"cases": {cid: {"rows": [{h: r[x] for h, x in zip(p, c)} for r in g]}}},   # scored 0
        "keys in capitals": {"cases": {cid: {"rows": [{x.upper(): r[x] for x in c} for r in g]}}},             # scored 0
    }
    for label, obj in shapes.items():
        assert st.score(TABLES, write_json(tmp_path, obj))["per_case"][cid]["cell_accuracy"] == 1.0, label


def test_odd_values_do_not_crash(tmp_path):
    obj = {"cases": {
        "TB-001": {"rows": [{"date": {"d": 1}, "reference": ["INV-40871"], "details": 12, "debit_gbp": True,
                             "credit_gbp": float("nan"), "balance_gbp": "1e400"}, "junk", 5, None, []]},
        "TB-002": {"rows": {"not": "a list"}},
        "TB-003": {"csv": 7},
        "TB-004": None}}
    r = st.score(TABLES, write_json(tmp_path, obj))
    assert r["per_case"]["TB-001"]["rows_exact"] == 0
    assert r["per_case"]["TB-002"]["column_mapping"].startswith("unreadable")
    assert r["per_case"]["TB-003"]["column_mapping"].startswith("unreadable")
    assert r["summary"]["cell_accuracy"] == 0

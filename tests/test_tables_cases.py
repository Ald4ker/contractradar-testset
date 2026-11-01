"""Tables track: the gold, the printed totals and the page-break layout agree (reads the committed tables/ files only)."""
import csv
import json
import os
import re

import pytest

from crtest import score_tables

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.path.join(ROOT, "tables")
MONEY = r"\(?-?[\d,]+\.\d\d\)?"


def gold(cid):
    with open(os.path.join(TABLES, cid, "expected.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pages(cid):
    with open(os.path.join(TABLES, cid, "text.txt"), encoding="utf-8") as fh:
        return [p for p in fh.read().split("\f") if p.strip()]


def amounts(line):
    return [score_tables.money(m) for m in re.findall(MONEY, line)]


def line_starting(cid, label):
    hits = [ln for p in pages(cid) for ln in p.splitlines() if ln.strip().startswith(label)]
    assert len(hits) == 1, (cid, label, hits)
    return hits[0]


def col_sum(rows, col):
    return round(sum(float(r[col] or 0) for r in rows), 2)


def test_gold_echo_scores_100_percent(tmp_path):
    with open(os.path.join(TABLES, "manifest.json"), encoding="utf-8") as fh:
        case_ids = [c["case_id"] for c in json.load(fh)["cases"]]
    for cid in case_ids:
        with open(os.path.join(TABLES, cid, "expected.csv"), encoding="utf-8") as fh:
            (tmp_path / f"{cid}.csv").write_text(fh.read(), encoding="utf-8")
    r = score_tables.score(TABLES, str(tmp_path))
    assert r["summary"]["cell_accuracy"] == 1.0
    assert r["summary"]["tables_exact"] == len(case_ids)


def test_tb001_balances_and_totals_agree():
    rows = gold("TB-001")
    for prev, row in zip(rows, rows[1:]):
        bal = round(float(prev["balance_gbp"]) + float(row["debit_gbp"] or 0) - float(row["credit_gbp"] or 0), 2)
        assert bal == float(row["balance_gbp"]), row
    assert amounts(line_starting("TB-001", "Totals")) == [col_sum(rows, "debit_gbp"), col_sum(rows, "credit_gbp")]
    assert amounts(line_starting("TB-001", "Balance now due")) == [float(rows[-1]["balance_gbp"])]


def test_tb002_total_and_count_agree():
    rows = gold("TB-002")
    m = re.search(r"Total for October 2026: £([\d,]+\.\d\d) \((\d+) transactions\)", "\n".join(pages("TB-002")))
    assert m and score_tables.money(m.group(1)) == col_sum(rows, "amount_gbp") and int(m.group(2)) == len(rows)


def test_tb003_total_header_once_per_page_and_split_row():
    rows = gold("TB-003")
    assert amounts(line_starting("TB-003", "Total")) == [col_sum(rows, "amount_gbp")]
    p1, p2 = pages("TB-003")
    header = re.compile(r"^\s*No\.\s+Milestone\s+Payment trigger\s+Due date", re.M)
    assert len(header.findall(p1)) == 1 and len(header.findall(p2)) == 1   # repeated on page 2 only, never twice on page 1
    flat1, flat2 = " ".join(p1.split()), " ".join(p2.split())
    trigger = rows[4]["payment_trigger"]
    assert trigger.startswith("Roof covering") and "Roof covering" in flat1 and "Roof covering" not in flat2
    assert "door seals" in flat2 and "door seals" not in flat1
    assert p2.split("VAT)", 1)[1].lstrip().startswith("confirmed in writing")  # page 2 opens with the rest of the split row


def test_tb004_week_totals_vat_and_carried_forward_agree():
    rows = gold("TB-004")
    weeks = sorted({r["week_ending"] for r in rows})
    week_lines = [ln for p in pages("TB-004") for ln in p.splitlines() if ln.strip().startswith("Week total")]
    assert len(week_lines) == len(weeks)
    for wk, ln in zip(weeks, week_lines):
        sub = [r for r in rows if r["week_ending"] == wk]
        assert amounts(ln) == [col_sum(sub, "net_gbp"), col_sum(sub, "vat_gbp"), col_sum(sub, "gross_gbp")], wk
    for r in rows:
        rate = 0.0 if r["description"].lower().startswith(("permit fees", "road closure notices and permit fees")) else 0.2
        assert round(float(r["net_gbp"]) * rate, 2) == float(r["vat_gbp"]), r
        assert round(float(r["net_gbp"]) + float(r["vat_gbp"]), 2) == float(r["gross_gbp"]), r
    p1, _p2 = pages("TB-004")
    before_break = [r for r in rows if r["order_no"] in p1]
    cf = amounts(line_starting("TB-004", "Carried forward"))
    assert cf == amounts(line_starting("TB-004", "Brought forward"))
    assert cf == [col_sum(before_break, k) for k in ("net_gbp", "vat_gbp", "gross_gbp")]
    assert amounts(line_starting("TB-004", "Total for July 2026")) == [col_sum(rows, k) for k in ("net_gbp", "vat_gbp", "gross_gbp")]


def test_tb004_week_cut_by_the_page_break_is_not_named_on_page_2():
    rows = gold("TB-004")
    p1, p2 = pages("TB-004")
    n1 = sum(1 for r in rows if r["order_no"] in p1)
    cut = rows[n1]["week_ending"]
    assert rows[n1 - 1]["week_ending"] == cut   # the first order on page 2 continues the last week of page 1
    y, m, d = cut.split("-")
    assert f"{d}/{m}/{y}" not in p2 and f"{int(d)} July {y}" not in p2   # nothing on page 2 names that week


@pytest.mark.parametrize("cid", ["TB-001", "TB-002", "TB-003", "TB-004"])
def test_notes_and_spec_present(cid):
    with open(os.path.join(TABLES, cid, "spec.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    assert spec["rows"] == len(gold(cid)) and spec["pages"] == len(pages(cid))

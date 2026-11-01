"""crtest.extract_tables_tools: header detection and column mapping (needs reportlab); tool runs need pdfplumber / pymupdf."""
import json
import os

import pytest

pytest.importorskip("reportlab")
from crtest import extract_tables_tools as ett  # noqa: E402
from crtest.score_tables import load_gold, load_spec, score_case  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.path.join(ROOT, "tables")
with open(os.path.join(TABLES, "manifest.json"), encoding="utf-8") as _fh:
    CASE_IDS = [c["case_id"] for c in json.load(_fh)["cases"]]


def test_column_bounds_are_contiguous_and_centred():
    for cid in CASE_IDS:
        spec = load_spec(TABLES, cid)
        b = ett.column_bounds(cid, spec)
        assert len(b) == len(ett.printed_columns(spec))
        assert all(abs(prev[1] - nxt[0]) < 1e-6 for prev, nxt in zip(b, b[1:]))
        assert abs((b[0][0] - ett.MARGIN) - (ett.PAGE_W - ett.MARGIN - b[-1][1])) < 1e-6


def test_header_rows_are_found_even_when_a_tool_cuts_header_words():
    w2 = ett.header_words(load_spec(TABLES, "TB-002"))
    assert ett.is_header_row(["Payment date Director", "ate", "Supplier", "", "Expense type", "Transaction A", "mount (£)"], w2)
    assert ett.is_header_row(["", "", "", "", "no\n.", ""], w2)
    assert not ett.is_header_row(["06/10/2026 Environm", "ent", "Brightwater", "Waste collection contract", "5100231", "84,612.00"], w2)
    assert not ett.is_header_row(["", "", "Ltd", "", "", ""], w2)
    w4 = ett.header_words(load_spec(TABLES, "TB-004"))
    assert ett.is_header_row(["Orderno Description\n.", "Costcentre", "Net(£)", "VAT(£)", "Gross(£)"], w4)
    assert not ett.is_header_row(["Week ending Friday 3 July 2026", "", "", "", ""], w4)
    assert not ett.is_header_row(["", "(14 no.)", "", "", "", ""], w4)


def test_cells_go_to_the_printed_column_they_overlap_most():
    bounds = [(0.0, 10.0), (10.0, 30.0), (30.0, 40.0)]

    def join(cells):
        return "".join(t for _, t in cells)

    assert ett.map_cells([((0, 0, 9, 1), "a"), ((9, 0, 31, 1), "b"), ((32, 0, 50, 1), "c")], bounds, join) == ["a", "b", "c"]
    assert ett.map_cells([((10, 0, 20, 1), "Planned preve"), ((20, 0, 29, 1), "ntative")], bounds, join) == ["", "Planned preventative", ""]
    assert ett.map_cells([((45, 0, 50, 1), "x"), ((1, 0, 2, 1), "  ")], bounds, join) == ["", "", "x"]


@pytest.mark.parametrize("tool", ett.TOOLS)
def test_no_mainstream_tool_gets_a_case_fully_right(tool):
    """Tripwire for the benchmark: if a stock extractor reproduces a case exactly, that case's hazards no longer bite."""
    pytest.importorskip("pdfplumber" if tool.startswith("pdfplumber") else "pymupdf")
    for cid in CASE_IDS:
        spec = load_spec(TABLES, cid)
        rows, _info = ett.extract_case(tool, TABLES, cid)
        r = score_case(spec, load_gold(TABLES, cid, spec), rows)
        assert not r["table_exact"], (tool, cid)
        if tool == "pdfplumber_lines" and cid == "TB-003":
            # the ruled schedule: both halves of the split row are boxed cells, so nothing is lost, only split
            assert r["rows_missing"] == 0 and r["rows_exact"] == r["rows_expected"] - 1, r


def test_generic_cleanup_rules():
    spec = {"columns": [{"name": "d", "printed_header": "Date", "type": "date"}, {"name": "t", "printed_header": "Text", "type": "text"},
                        {"name": "m", "printed_header": "Amount", "type": "money"}]}
    rows = [{"d": "", "t": "Statement of account", "m": ""},          # key-less with nothing above: dropped
            {"d": "01/01/2026", "t": "Alpha", "m": "1.00"},
            {"d": "", "t": "continued", "m": ""},                     # continuation of the row above
            {"d": "", "t": "", "m": "2.00"},                          # suppressed repeats: date and text filled down
            {"d": "", "t": "Carried forward", "m": "3.00"}]           # subtotal line: dropped
    assert ett.generic_cleanup(rows, spec) == [{"d": "01/01/2026", "t": "Alpha continued", "m": "1.00"},
                                               {"d": "01/01/2026", "t": "Alpha continued", "m": "2.00"}]

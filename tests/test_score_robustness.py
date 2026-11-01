import json
import os
import shutil

import pytest

from crtest.score import compare, score_predictions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_gold_lot_without_a_printed_value():
    gold = [{"lot_number": 1, "awarded": True, "supplier_name": "Alpha Ltd", "value_gbp": None}]
    assert compare("lots", gold, [{"lot_number": 1, "awarded": True, "supplier_name": "Alpha Ltd", "value_gbp": None}])[0] == "correct"
    assert compare("lots", gold, [{"lot_number": 1, "awarded": True, "supplier_name": "Alpha Ltd", "value_gbp": 5}])[0] == "wrong"


def test_malformed_prediction_is_wrong_not_a_crash():
    pred = {"extractor": "bad", "cases": {"CR-001": {"fields": {"contract_value_gbp": {"x": 1}, "award_date": [1]}}}}
    r = score_predictions(os.path.join(ROOT, "cases"), pred)
    v = r["per_case"]["CR-001"]["verdicts"]
    assert v["contract_value_gbp"]["verdict"] == "wrong" and v["award_date"]["verdict"] == "wrong"


def test_gold_problems_raise_instead_of_blaming_the_submitter(tmp_path):
    cases = tmp_path / "cases"
    shutil.copytree(os.path.join(ROOT, "cases"), cases)
    gold_path = cases / "CR-001" / "gold.json"
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    gold["fields"]["field_from_the_future"] = "x"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    with pytest.raises(KeyError):
        score_predictions(str(cases), {"extractor": "anything", "cases": {}})

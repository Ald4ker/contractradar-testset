"""Score a predictions file against the gold labels.

Run:  python -m crtest.score --cases cases --pred results/naive_text.json
Writes results/<extractor>.scored.json and prints a summary table.

Scoring rules (per field):
- gold null and prediction null/missing  -> not counted
- gold null and prediction non-null      -> wrong (hallucinated value)
- dates: compared as ISO strings after parsing any common format
- money: within 0.1% or £1
- numbers: exact (percent within 0.1)
- strings: normalised (case, punctuation, Ltd/Limited, trading-as stripped); ratio >= 0.92 counts
- lists: cpv_codes as sets; kpis as a set of normalised strings
- lots: every lot must match on supplier, value and awarded; scored as one field plus per-lot detail
A case "passes" when every critical field that is non-null in gold is correct.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

from .normalise import norm_cpv, norm_text, parse_date, parse_money, text_similarity, to_bool, to_float, to_int

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", "schema", "fields.json"), encoding="utf-8") as _f:
    SCHEMA = json.load(_f)
FIELD_TYPES = {f["name"]: f["type"] for f in SCHEMA["fields"]}
CRITICAL = set(SCHEMA["critical_fields"])
HIGH_FLAGS = {f["id"] for f in SCHEMA["flags"] if f["severity"] == "high"}
# Bump when scoring semantics change: crtest.server re-scores stored community submissions when it changes.
SCORER_VERSION = "0.1.1"


def compare(name: str, gold, pred) -> tuple[str, str]:
    """Return (verdict, note). verdict in {correct, wrong, missing, skip}."""
    t = FIELD_TYPES[name]
    gold_empty = gold in (None, "", [], {})
    pred_empty = pred in (None, "", [], {})
    if gold_empty and pred_empty:
        return "skip", ""
    if gold_empty and not pred_empty:
        return "wrong", "value where gold is null"
    if pred_empty:
        return "missing", ""
    if t == "date":
        g, p = parse_date(gold), parse_date(pred)
        return ("correct" if g == p else "wrong"), f"{p!r} vs {g!r}"
    if t == "money":
        g, p = parse_money(gold), parse_money(pred)
        if g is None or p is None:
            return "wrong", f"{pred!r} vs {gold!r}"
        ok = abs(g - p) <= max(1.0, 0.001 * abs(g))
        return ("correct" if ok else "wrong"), f"{p:,.2f} vs {g:,.2f}"
    if t == "integer":
        g, p = to_int(gold), to_int(pred)
        return ("correct" if g == p else "wrong"), f"{p} vs {g}"
    if t == "number":
        g, p = to_float(gold), to_float(pred)
        ok = g is not None and p is not None and abs(g - p) <= 0.1
        return ("correct" if ok else "wrong"), f"{p} vs {g}"
    if t == "boolean":
        g, p = to_bool(gold), to_bool(pred)
        return ("correct" if g == p else "wrong"), f"{p} vs {g}"
    if t == "enum":
        return ("correct" if norm_text(gold) == norm_text(pred) else "wrong"), f"{pred!r} vs {gold!r}"
    if t == "list[string]":
        if name == "cpv_codes":
            g, p = {norm_cpv(x) for x in gold}, {norm_cpv(x) for x in (pred if isinstance(pred, list) else str(pred).split(","))}
        else:
            g, p = {norm_text(x) for x in gold}, {norm_text(x) for x in (pred if isinstance(pred, list) else [pred])}
        return ("correct" if g == p else "wrong"), f"{sorted(p)} vs {sorted(g)}"
    if t == "list[object]":  # lots
        if not isinstance(pred, list):
            return "wrong", "lots not a list"
        gmap = {to_int(l.get("lot_number")): l for l in gold}
        pmap = {to_int(l.get("lot_number")): l for l in pred if isinstance(l, dict)}
        if set(gmap) != set(pmap):
            return "wrong", f"lot numbers {sorted(k for k in pmap if k is not None)} vs {sorted(gmap)}"
        for n, gl in gmap.items():
            pl = pmap[n]
            if to_bool(pl.get("awarded")) != gl["awarded"]:
                return "wrong", f"lot {n} awarded flag"
            if gl["awarded"]:
                if text_similarity(pl.get("supplier_name") or "", gl["supplier_name"]) < 0.92:
                    return "wrong", f"lot {n} supplier {pl.get('supplier_name')!r}"
                if gl.get("value_gbp") is None:   # an awarded lot whose value is not printed
                    if pl.get("value_gbp") not in (None, ""):
                        return "wrong", f"lot {n} value {pl.get('value_gbp')!r} where none is printed"
                    continue
                pv, gv = parse_money(pl.get("value_gbp")), float(gl["value_gbp"])
                if pv is None or abs(pv - gv) > max(1.0, 0.001 * gv):
                    return "wrong", f"lot {n} value {pl.get('value_gbp')!r}"
        return "correct", f"{len(gmap)} lots"
    # string
    sim = text_similarity(str(gold), str(pred))
    return ("correct" if sim >= 0.92 else "wrong"), f"{pred!r} vs {gold!r} (sim {sim:.2f})"


def score(cases_dir: str, pred_path: str) -> dict:
    with open(pred_path, encoding="utf-8") as fh:
        pred = json.load(fh)
    return score_predictions(cases_dir, pred, default_name=os.path.basename(pred_path))


def score_predictions(cases_dir: str, pred: dict, default_name: str = "unnamed") -> dict:
    """Score an in-memory predictions object (the results/ format); score() is the file wrapper."""
    with open(os.path.join(cases_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    per_case = {}
    field_tot = defaultdict(lambda: [0, 0])  # name -> [correct, counted]
    hazard_tot = defaultdict(lambda: [0, 0])
    flag_stats = {"tp": 0, "fp": 0, "fn": 0, "cases_with_flag_output": 0}
    passes = 0
    for c in manifest["cases"]:
        with open(os.path.join(cases_dir, c["gold"]), encoding="utf-8") as fh:
            gold = json.load(fh)
        pred_cases = pred.get("cases") if isinstance(pred.get("cases"), dict) else {}
        p = pred_cases.get(c["case_id"]) if isinstance(pred_cases.get(c["case_id"]), dict) else {}
        pf = p.get("fields") if isinstance(p.get("fields"), dict) else {}
        verdicts = {}
        correct = counted = 0
        crit_ok = True
        for name, gv in gold["fields"].items():
            if name not in FIELD_TYPES:
                raise KeyError(f"{c['case_id']}: gold field {name!r} is not in schema/fields.json")
            try:
                v, note = compare(name, gv, pf.get(name))
            except Exception as exc:
                compare(name, gv, gv)   # raises if the gold itself cannot be compared: a gold or scorer bug, not the submitter's
                v, note = "wrong", f"could not compare the predicted value ({type(exc).__name__})"
            verdicts[name] = {"verdict": v, "note": note, "gold": gv, "pred": pf.get(name)}
            if v == "skip":
                continue
            counted += 1
            field_tot[name][1] += 1
            for h in gold["hazards"]:
                hazard_tot[h][1] += 1
            if v == "correct":
                correct += 1
                field_tot[name][0] += 1
                for h in gold["hazards"]:
                    hazard_tot[h][0] += 1
            elif name in CRITICAL:
                crit_ok = False
        passes += 1 if crit_ok else 0
        exp_flags = {x["id"] for x in gold["expected_flags"] if x["id"] in HIGH_FLAGS}
        got_flags = None
        if isinstance(p.get("flags"), list):
            got_flags = {str(x.get("id")) if isinstance(x, dict) else str(x) for x in p["flags"]} & HIGH_FLAGS
            flag_stats["cases_with_flag_output"] += 1
            flag_stats["tp"] += len(exp_flags & got_flags)
            flag_stats["fp"] += len(got_flags - exp_flags)
            flag_stats["fn"] += len(exp_flags - got_flags)
        per_case[c["case_id"]] = {
            "title": c["title"], "hazards": gold["hazards"], "fields_correct": correct, "fields_counted": counted,
            "field_accuracy": round(correct / counted, 3) if counted else None, "critical_pass": crit_ok,
            "expected_high_flags": sorted(exp_flags), "predicted_high_flags": sorted(got_flags) if got_flags is not None else None,
            "verdicts": verdicts,
        }
    total_c = sum(v[0] for v in field_tot.values())
    total_n = sum(v[1] for v in field_tot.values())
    tp, fp, fn = flag_stats["tp"], flag_stats["fp"], flag_stats["fn"]
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    summary = {
        "extractor": pred.get("extractor", default_name),
        "version": pred.get("version"),
        "description": pred.get("description"),
        "run_at": pred.get("run_at"),
        "cases": len(manifest["cases"]),
        "field_accuracy": round(total_c / total_n, 3) if total_n else None,
        "fields_correct": total_c, "fields_counted": total_n,
        "critical_pass_rate": round(passes / len(manifest["cases"]), 3),
        "cases_passed": passes,
        "per_field": {k: {"correct": v[0], "counted": v[1], "accuracy": round(v[0] / v[1], 3) if v[1] else None} for k, v in sorted(field_tot.items())},
        "per_hazard": {k: {"correct": v[0], "counted": v[1], "accuracy": round(v[0] / v[1], 3) if v[1] else None} for k, v in sorted(hazard_tot.items())},
        "flags": {"cases_with_flag_output": flag_stats["cases_with_flag_output"], "tp": tp, "fp": fp, "fn": fn,
                  "precision": round(prec, 3) if prec is not None else None, "recall": round(rec, 3) if rec is not None else None},
    }
    return {"summary": summary, "per_case": per_case}


def print_summary(r: dict) -> None:
    s = r["summary"]
    print(f"\n{s['extractor']} {s.get('version') or ''}: field accuracy {s['field_accuracy']:.1%} ({s['fields_correct']}/{s['fields_counted']}), "
          f"critical pass {s['cases_passed']}/{s['cases']}")
    print(f"{'case':8} {'acc':>6} {'pass':>5}  title")
    for cid, c in r["per_case"].items():
        acc = f"{c['field_accuracy']:.0%}" if c["field_accuracy"] is not None else "-"
        print(f"{cid:8} {acc:>6} {'yes' if c['critical_pass'] else 'no':>5}  {c['title']}")
    worst = sorted((v["accuracy"], k) for k, v in s["per_field"].items() if v["accuracy"] is not None and v["counted"] >= 3)[:6]
    print("weakest fields:", ", ".join(f"{k} {a:.0%}" for a, k in worst))
    if s["flags"]["cases_with_flag_output"]:
        print(f"high-severity flags: precision {s['flags']['precision']}, recall {s['flags']['recall']}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="cases")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out", help="default: <pred>.scored.json next to the predictions file")
    args = ap.parse_args(argv)
    r = score(args.cases, args.pred)
    out = args.out or args.pred.replace(".json", "") + ".scored.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False)
    print_summary(r)
    print("wrote", out)


if __name__ == "__main__":
    main()

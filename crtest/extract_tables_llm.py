"""LLM extractor for the tables track, over any OpenAI-compatible endpoint (same environment as crtest.extract_llm:
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TIMEOUT).

The model gets the case's columns (name, printed header, type) and the pdftotext -layout text (plus page images with
--vision), and returns {"rows": [...]}, one object per table row. It never sees a case's own notes (spec.json
row_rules / why): those describe the trap. --prompt plain gives only the columns and the output format; --prompt
guided (the default) adds TABLE_RULES, the same generic rules for every case.

Run:  python -m crtest.extract_tables_llm --out results_tables/<name>.json [--prompt plain|guided] [--vision] [--only TB-001]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

from .extract_llm import call_llm, page_images_b64, parse_json, pdf_text
from .score_tables import load_spec


TABLE_RULES = ("Return every data row of the table and nothing else. Header rows (including a header repeated on a new "
               "page), running page headers and footers, and totals, subtotals, carried-forward and brought-forward lines are "
               "not data rows. A cell's text can wrap over several lines or continue onto the next page: it is still one "
               "cell. When a value such as a date or a name is printed once for a group of rows, or as a heading above the "
               "group, it applies to every row of the group, including rows on the next page.")


def build_prompt(spec: dict, mode: str = "guided") -> str:
    lines = ["You extract one table from a UK public-sector document into JSON.",
             'Return ONLY a JSON object {"rows": [...]} with one object per row of the table, in document order, using exactly these keys:']
    for c in spec["columns"]:
        lines.append(f"- {c['name']} ({c['type']}): printed as \"{c['printed_header']}\"")
    lines.append("Dates as ISO YYYY-MM-DD. Money as a plain number: no symbols or thousands separators, negative when printed in "
                 "brackets or with a minus sign. A blank cell is null. Text exactly as printed.")
    if mode == "guided":
        lines.append(TABLE_RULES)
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", default="tables")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vision", action="store_true")
    ap.add_argument("--prompt", choices=("plain", "guided"), default="guided")
    ap.add_argument("--only")
    ap.add_argument("--name")
    args = ap.parse_args(argv)
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key, model = os.environ.get("LLM_API_KEY"), os.environ.get("LLM_MODEL")
    if not api_key or not model:
        sys.exit("set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL for non-OpenAI endpoints)")
    with open(os.path.join(args.tables, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    mode = ("vision+text" if args.vision else "text") + f", {args.prompt} prompt"
    out = {"extractor": args.name or f"llm:{model}:{mode}", "version": "0.1.0", "track": "tables", "prompt": args.prompt,
           "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "description": f"{model} via {base_url} ({mode})", "model": model, "cases": {}}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as fh:
            out["cases"] = json.load(fh).get("cases", {})
    for c in manifest["cases"]:
        cid = c["case_id"]
        if args.only and cid not in args.only.split(","):
            continue
        if cid in out["cases"] and not out["cases"][cid].get("error") and not args.only:
            print(cid, "cached")
            continue
        spec = load_spec(args.tables, cid)
        pdf = os.path.join(args.tables, cid, "document.pdf")
        content = [{"type": "text", "text": "Document text (pdftotext -layout):\n\n" + pdf_text(pdf)}]
        if args.vision:
            content += [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}} for b in page_images_b64(pdf)]
        content.append({"type": "text", "text": "Return the JSON object now."})
        t0 = time.time()
        err, rows, raw = None, [], ""
        try:
            raw = call_llm([{"role": "system", "content": build_prompt(spec, args.prompt)}, {"role": "user", "content": content}], model, base_url, api_key)
            obj = parse_json(raw)
            rows = obj.get("rows") if isinstance(obj, dict) else obj
            if not isinstance(rows, list):
                rows, err = [], "no rows list in the reply"
        except (ValueError, RuntimeError) as e:
            err = f"{type(e).__name__}: {e}"
        out["cases"][cid] = {"rows": rows, "seconds": round(time.time() - t0, 1), "error": err, "raw": (raw or "")[:6000]}
        print(cid, f"{time.time() - t0:.1f}s", err or f"{len(rows)} rows", flush=True)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
    print("wrote", args.out)


if __name__ == "__main__":
    main()

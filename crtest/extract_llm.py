"""LLM extractor over any OpenAI-compatible chat completions endpoint.

Works with OpenAI, DeepSeek, OpenRouter, Alibaba DashScope (compatible mode),
a local vLLM/llama.cpp server, etc. Text mode feeds `pdftotext -layout`
output; `--vision` also attaches page images (for scans and tricky layouts).

Environment:
  LLM_BASE_URL   e.g. https://api.deepseek.com/v1   (default https://api.openai.com/v1)
  LLM_API_KEY    bearer token
  LLM_MODEL      model name, e.g. deepseek-chat, gpt-4.1-mini, qwen-plus

Run:  python -m crtest.extract_llm --cases cases --out results/<name>.json [--vision] [--ocr]
No keys are stored in this repository.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from .schema import FIELD_NAMES, SCHEMA

HERE = os.path.dirname(os.path.abspath(__file__))


def build_prompt() -> str:
    lines = ["You extract key fields from UK public-sector contract documents (Procurement Act 2023 era).",
             "Return ONLY a JSON object with exactly these keys. Use null when the document does not state a value. Never guess.",
             "Dates: ISO YYYY-MM-DD. Money: a number in pounds with no symbols (2310000 not '£2.31m'). Lists: JSON arrays.",
             "Legal names only: strip 'trading as' names. If an annual price and a total are both given, contract_value_gbp is the total.",
             "A totals row is not a lot. An unawarded lot is still a lot with awarded=false and supplier_name=null.",
             "If a percentage is not printed, compute value_change_percent from the values, rounded to 1 decimal place.", ""]
    for f in SCHEMA["fields"]:
        extra = f" One of: {', '.join(f['values'])}." if f.get("values") else ""
        lines.append(f"- {f['name']} ({f['type']}): {f['description']}{extra}")
    lines.append("")
    lines.append("Also return \"flags\": an array of rule ids from this list that you believe apply, or [] if none:")
    for fl in SCHEMA["flags"]:
        lines.append(f"- {fl['id']}: {fl['description']}")
    return "\n".join(lines)


def pdf_text(path: str, ocr: bool = False) -> str:
    text = subprocess.run(["pdftotext", "-layout", path, "-"], check=True, capture_output=True, text=True).stdout
    if len(text.strip()) < 50 and ocr:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["pdftoppm", "-r", "200", "-gray", "-png", path, os.path.join(td, "p")], check=True)
            parts = []
            for name in sorted(os.listdir(td)):
                r = subprocess.run(["tesseract", os.path.join(td, name), "-", "--psm", "4"], capture_output=True, text=True)
                parts.append(r.stdout)
            text = "\n\f\n".join(parts)
    return text


def page_images_b64(path: str, dpi: int = 110, max_pages: int = 6) -> list[str]:
    out = []
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-l", str(max_pages), path, os.path.join(td, "p")], check=True)
        for name in sorted(os.listdir(td)):
            with open(os.path.join(td, name), "rb") as fh:
                out.append(base64.b64encode(fh.read()).decode())
    return out


def call_llm(messages: list, model: str, base_url: str, api_key: str, temperature: float = 0.0, retries: int = 5) -> str:
    # Reasoning models (GLM-5.x, DeepSeek-R1 style) spend tokens thinking before the JSON; LLM_MAX_TOKENS raises the cap.
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "4000"))}
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=int(os.environ.get("LLM_TIMEOUT", "180"))) as resp:   # reasoning models can take minutes
                data = json.load(resp)
            msg = data["choices"][0]["message"]
            content = msg.get("content")
            if not content:
                # Some reasoning models return content=null and leave the answer (or a truncated think) in reasoning_content.
                content = msg.get("reasoning_content") or msg.get("reasoning") or ""
            return content if isinstance(content, str) else json.dumps(content)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:  # pragma: no cover
            last = e
            # Free tiers rate-limit per minute: back off hard on 429/5xx and honour Retry-After.
            code = getattr(e, "code", None)
            retry_after = None
            if hasattr(e, "headers") and e.headers is not None:
                try:
                    retry_after = float(e.headers.get("Retry-After") or 0) or None
                except ValueError:
                    retry_after = None
            if code == 429 or (code is not None and code >= 500):
                wait = retry_after or min(120.0, 15.0 * (2 ** attempt))
            elif code is not None and 400 <= code < 500:
                break  # auth/quota/model errors do not heal by waiting
            else:
                wait = 2 * (attempt + 1)
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed: {last}")


def parse_json(s: str) -> dict:
    if not s or not isinstance(s, str):
        raise ValueError("empty response")
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        s = s[start:end + 1]
    return json.loads(s)


def coerce(obj: dict) -> tuple[dict, list]:
    fields = {k: obj.get(k) for k in FIELD_NAMES}
    flags = obj.get("flags") or []
    return fields, flags


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="cases")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vision", action="store_true", help="attach page images (model must support image input)")
    ap.add_argument("--ocr", action="store_true", help="run tesseract when the PDF has no text layer")
    ap.add_argument("--no-text", action="store_true", help="vision only: do not send the text dump")
    ap.add_argument("--only")
    ap.add_argument("--name", help="extractor name recorded in the output (default: llm:<model>)")
    args = ap.parse_args(argv)
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    if not api_key or not model:
        sys.exit("set LLM_API_KEY and LLM_MODEL (and LLM_BASE_URL for non-OpenAI endpoints)")
    with open(os.path.join(args.cases, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    system = build_prompt()
    mode = ("vision" if args.vision else "") + ("+text" if not args.no_text else "") + ("+ocr" if args.ocr else "")
    name = args.name or f"llm:{model}:{mode.strip('+') or 'text'}"
    out = {"extractor": name, "version": "0.1.0", "run_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "description": f"{model} via {base_url} ({mode.strip('+') or 'text'})", "model": model, "cases": {}}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as fh:
            out["cases"] = json.load(fh).get("cases", {})
    for c in manifest["cases"]:
        if args.only and c["case_id"] not in args.only.split(","):
            continue
        if c["case_id"] in out["cases"] and not args.only:
            print(c["case_id"], "cached")
            continue
        pdf = os.path.join(args.cases, c["document"])
        content = []
        if not args.no_text:
            text = pdf_text(pdf, ocr=args.ocr)
            content.append({"type": "text", "text": "Document text (pdftotext -layout):\n\n" + (text if text.strip() else "[no text layer]")})
        if args.vision:
            for b64 in page_images_b64(pdf):
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        content.append({"type": "text", "text": "Return the JSON object now."})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        t0 = time.time()
        raw = call_llm(messages, model, base_url, api_key)
        try:
            fields, flags = coerce(parse_json(raw))
            err = None
        except (ValueError, json.JSONDecodeError) as e:
            fields, flags, err = {k: None for k in FIELD_NAMES}, [], f"unparseable: {e}"
        out["cases"][c["case_id"]] = {"fields": fields, "flags": flags, "seconds": round(time.time() - t0, 1), "error": err, "raw": raw[:4000]}
        print(c["case_id"], f"{time.time() - t0:.1f}s", err or "ok")
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
    print("wrote", args.out)


if __name__ == "__main__":
    main()

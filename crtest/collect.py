"""Collect real council notices (OCDS JSON) from the two UK publication services.

Sources (both Open Government Licence v3.0, no API key):
  - Find a Tender (statutory platform for Procurement Act 2023 notices since 24 Feb 2025)
      GET https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?updatedFrom=..&updatedTo=..
  - Contracts Finder (pre-Act and below-threshold notices)
      GET https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search?publishedFrom=..&publishedTo=..

Only releases whose buyer looks like a local authority are kept. Every file written
records its source URL, fetch time and licence so the provenance rule of the pilot
("source and licence linked") is met automatically.

Run:  python -m crtest.collect --from 2026-09-01 --to 2026-09-07 --out collected [--source fts|cf|both] [--download-docs]
Attached documents are the publisher's own files; check their licence before redistributing.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request

FTS = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
CF = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
LICENCE = "Open Government Licence v3.0 (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)"
UA = "contractradar-testset/0.1 (+https://github.com/Marxist-Leninist/contractradar-testset)"
COUNCIL_RE = re.compile(r"\b(council|borough|district|county|city of|london borough|unitary|combined authority|metropolitan)\b", re.I)


def get_json(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def buyer_name(rel: dict) -> str:
    b = rel.get("buyer") or {}
    name = b.get("name")
    if not name:
        for p in rel.get("parties", []):
            if "buyer" in (p.get("roles") or []):
                name = p.get("name")
                break
    return name or ""


def is_council(rel: dict) -> bool:
    return bool(COUNCIL_RE.search(buyer_name(rel)))


def iter_fts(date_from: str, date_to: str, limit: int = 100):
    url = f"{FTS}?{urllib.parse.urlencode({'updatedFrom': date_from + 'T00:00:00', 'updatedTo': date_to + 'T23:59:59', 'limit': limit})}"
    while url:
        pkg = get_json(url)
        for rel in pkg.get("releases", []):
            yield rel, url
        nxt = (pkg.get("links") or {}).get("next")
        url = nxt if nxt and nxt != url else None


def iter_cf(date_from: str, date_to: str, limit: int = 100):
    url = f"{CF}?{urllib.parse.urlencode({'publishedFrom': date_from, 'publishedTo': date_to, 'limit': limit})}"
    while url:
        pkg = get_json(url)
        for rel in pkg.get("releases", []):
            yield rel, url
        nxt = (pkg.get("links") or {}).get("next")
        url = nxt if nxt and nxt != url else None


def documents(rel: dict):
    for section in ("planning", "tender"):
        for d in (rel.get(section) or {}).get("documents", []) or []:
            yield section, d
    for a in rel.get("awards", []) or []:
        for d in a.get("documents", []) or []:
            yield "award", d
    for c in rel.get("contracts", []) or []:
        for d in c.get("documents", []) or []:
            yield "contract", d


def summarise(rel: dict) -> dict:
    tender = rel.get("tender") or {}
    awards = rel.get("awards") or []
    value = (tender.get("value") or {}).get("amount")
    if value is None and awards:
        value = (awards[0].get("value") or {}).get("amount")
    suppliers = sorted({s.get("name", "") for a in awards for s in a.get("suppliers", [])})
    return {
        "ocid": rel.get("ocid"), "release_id": rel.get("id"), "tags": ",".join(rel.get("tag", [])), "published": rel.get("date"),
        "buyer": buyer_name(rel), "title": tender.get("title"), "value_gbp": value, "suppliers": "; ".join(suppliers),
        "procurement_method": tender.get("procurementMethod"), "main_category": tender.get("mainProcurementCategory"),
        "n_documents": sum(1 for _ in documents(rel)),
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--out", default="collected")
    ap.add_argument("--source", choices=["fts", "cf", "both"], default="both")
    ap.add_argument("--max", type=int, default=500, help="stop after this many council releases per source")
    ap.add_argument("--download-docs", action="store_true", help="also download PDF attachments (max 15 MB each)")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    index_path = os.path.join(args.out, "index.csv")
    seen = set()
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            seen = {r["ocid"] + "|" + r["release_id"] for r in csv.DictReader(fh)}
    fields = ["source", "ocid", "release_id", "tags", "published", "buyer", "title", "value_gbp", "suppliers", "procurement_method", "main_category", "n_documents", "source_url", "fetched_at", "licence", "file"]
    new_rows = []
    doc_rows = []
    sources = [("fts", iter_fts)] if args.source == "fts" else [("cf", iter_cf)] if args.source == "cf" else [("fts", iter_fts), ("cf", iter_cf)]
    for src, it in sources:
        kept = 0
        for rel, page_url in it(args.date_from, args.date_to):
            if not is_council(rel):
                continue
            key = f"{rel.get('ocid')}|{rel.get('id')}"
            if key in seen:
                continue
            seen.add(key)
            d = os.path.join(args.out, src)
            os.makedirs(d, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{rel.get('ocid')}__{rel.get('id')}")[:150]
            fname = os.path.join(d, safe + ".json")
            fetched = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(fname, "w", encoding="utf-8") as fh:
                json.dump({"_provenance": {"source": src, "source_url": page_url, "fetched_at": fetched, "licence": LICENCE}, "release": rel}, fh, indent=1, ensure_ascii=False)
            row = {"source": src, **summarise(rel), "source_url": page_url, "fetched_at": fetched, "licence": "OGL-3.0", "file": os.path.relpath(fname, args.out)}
            new_rows.append(row)
            for section, doc in documents(rel):
                doc_rows.append({"source": src, "ocid": rel.get("ocid"), "section": section, "document_type": doc.get("documentType"), "title": doc.get("title"),
                                 "format": doc.get("format"), "url": doc.get("url"), "downloaded": ""})
                if args.download_docs and doc.get("url") and (doc.get("format") or "").lower() in ("application/pdf", "pdf") or (doc.get("url") or "").lower().endswith(".pdf"):
                    if args.download_docs and doc.get("url"):
                        try:
                            ddir = os.path.join(args.out, "docs", re.sub(r"[^A-Za-z0-9._-]", "_", rel.get("ocid") or "unknown"))
                            os.makedirs(ddir, exist_ok=True)
                            req = urllib.request.Request(doc["url"], headers={"User-Agent": UA})
                            with urllib.request.urlopen(req, timeout=120) as r:
                                data = r.read(15 * 1024 * 1024 + 1)
                            if len(data) <= 15 * 1024 * 1024:
                                name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(urllib.parse.urlparse(doc["url"]).path) or "document.pdf")
                                with open(os.path.join(ddir, name), "wb") as fh:
                                    fh.write(data)
                                doc_rows[-1]["downloaded"] = os.path.relpath(os.path.join(ddir, name), args.out)
                        except Exception as e:  # noqa: BLE001
                            doc_rows[-1]["downloaded"] = f"ERROR {e}"
            kept += 1
            print(f"{src} {row['published'][:10] if row['published'] else '?'} {row['buyer'][:40]:40} {row['tags']:16} {str(row['title'])[:50]}")
            if kept >= args.max:
                break
    write_header = not os.path.exists(index_path)
    with open(index_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerows(new_rows)
    if doc_rows:
        dpath = os.path.join(args.out, "documents.csv")
        write_header = not os.path.exists(dpath)
        with open(dpath, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["source", "ocid", "section", "document_type", "title", "format", "url", "downloaded"])
            if write_header:
                w.writeheader()
            w.writerows(doc_rows)
    with open(os.path.join(args.out, "LICENCE.md"), "w", encoding="utf-8") as fh:
        fh.write("Contains public sector information licensed under the Open Government Licence v3.0.\n"
                 "Sources: Find a Tender (Cabinet Office) and Contracts Finder (Cabinet Office). Each JSON file carries its source URL and fetch time under `_provenance`.\n"
                 "Attached documents listed in documents.csv are the publishers' own files: check each one's licence before redistributing.\n")
    print(f"kept {len(new_rows)} council releases, {len(doc_rows)} document links -> {args.out}")


if __name__ == "__main__":
    main()

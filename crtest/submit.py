"""Post a predictions file (the results/ format) to the community leaderboard and print the score.

Run:  python -m crtest.submit --pred results/my_extractor.json [--contact https://github.com/you] [--name "..."]
The same scorer runs locally with `python -m crtest.score --pred ...`; this just publishes the result.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://contractradar.opentransformers.online"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True, help="predictions JSON: {extractor, description?, cases: {CR-001: {fields, flags}}}")
    ap.add_argument("--url", default=DEFAULT_URL, help="site base URL")
    ap.add_argument("--name", help="extractor name (default: the file's 'extractor')")
    ap.add_argument("--description", help="default: the file's 'description'")
    ap.add_argument("--contact", help="URL or handle shown with your row")
    args = ap.parse_args(argv)
    with open(args.pred, encoding="utf-8") as fh:
        pred = json.load(fh)
    body = {"extractor": args.name or pred.get("extractor"), "description": args.description or pred.get("description"),
            "version": pred.get("version"), "contact": args.contact, "cases": pred.get("cases")}
    req = urllib.request.Request(args.url.rstrip("/") + "/api/submit", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "crtest.submit/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            r = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error")
        except Exception:
            msg = e.reason
        sys.exit(f"submission rejected ({e.code}): {msg}")
    except urllib.error.URLError as e:
        sys.exit(f"could not reach {args.url}: {e.reason}")
    s = r.get("summary") or {}
    acc = s.get("field_accuracy")
    print(f"{s.get('extractor')}: field accuracy {acc:.1%}" if acc is not None else s.get("extractor"),
          f"| critical pass {s.get('cases_passed')}/{s.get('cases')} | community table rank {r.get('rank')} of {r.get('of')}"
          f" (overall {r.get('overall_rank')} of {r.get('overall_of')}, curated rows included)")
    if r.get("duplicate_of_earlier_submission"):
        print("identical predictions were already submitted; this is the earlier result")
    for key in ("ignored_cases", "ignored_fields", "ignored_flags"):
        if r.get(key):
            print(f"{key.replace('_', ' ')}: {', '.join(r[key])}")
    print(r.get("note", ""))
    print("submission", r.get("submission_id"), "->", r.get("leaderboard_url"))


if __name__ == "__main__":
    main()

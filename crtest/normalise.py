"""Value normalisation shared by the scorer and the extractors."""
from __future__ import annotations

import datetime as dt
import re
from difflib import SequenceMatcher

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})

_WORD_NUM = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
             "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_WORD_MUL = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}


def parse_date(s) -> str | None:
    """Return ISO date or None. Accepts 3 March 2026, 3rd March 2026, 03/03/2026, 2026-03-03, 03-Mar-2026."""
    if s is None:
        return None
    if isinstance(s, dt.date):
        return s.isoformat()
    s = str(s).strip()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[ -]([A-Za-z]{3,9})[ ,-]*(\d{4})\b", s)
    if m and m.group(2).lower()[:3] in MONTHS:
        mo = MONTHS[m.group(2).lower()] if m.group(2).lower() in MONTHS else MONTHS[m.group(2).lower()[:3]]
        return f"{m.group(3)}-{mo:02d}-{int(m.group(1)):02d}"
    m = re.search(r"\b([A-Za-z]{3,9}) (\d{1,2}),? (\d{4})\b", s)
    if m and m.group(1).lower()[:3] in MONTHS:
        mo = MONTHS.get(m.group(1).lower()) or MONTHS[m.group(1).lower()[:3]]
        return f"{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}"
    return None


def words_to_number(text: str) -> int | None:
    tokens = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    total, current, seen = 0, 0, False
    for t in tokens:
        if t in _WORD_NUM:
            current += _WORD_NUM[t]
            seen = True
        elif t == "hundred":
            current *= 100
        elif t in _WORD_MUL:
            total += current * _WORD_MUL[t]
            current = 0
        elif t in ("and", "pounds", "pound"):
            continue
        else:
            if seen:
                break
    return total + current if seen else None


def parse_money(s) -> float | None:
    """Return pounds as float. Handles £1,234.56, £1.85m, £450k, £4 200 000, 1,234.00 GBP, 'two million pounds (£2,000,000)'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    m = re.search(r"£\s?(\d[\d,\s]*)(?:\.(\d{1,2}))?\s*(m|million|k|bn)?\b", t, re.I)
    if m:
        digits = re.sub(r"[,\s]", "", m.group(1))
        val = float(digits + ("." + m.group(2) if m.group(2) else ""))
        suf = (m.group(3) or "").lower()
        if suf in ("m", "million"):
            val *= 1e6
        elif suf == "k":
            val *= 1e3
        elif suf == "bn":
            val *= 1e9
        return val
    m = re.search(r"(\d[\d,\s]*(?:\.\d{1,2})?)\s*(?:GBP|pounds)\b", t, re.I)
    if m:
        return float(re.sub(r"[,\s]", "", m.group(1)))
    w = words_to_number(t)
    if w is not None and w > 0:
        return float(w)
    m = re.search(r"\b(\d[\d,]*(?:\.\d{1,2})?)\b", t)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


_ORG_SUBS = [(r"\blimited\b", "ltd"), (r"\bcommunity interest company\b", "cic"), (r"\bpublic limited company\b", "plc"), (r"\bincorporated\b", "inc"),
             (r"\(t/?a [^)]*\)", ""), (r"\(trading as [^)]*\)", ""), (r"\btrading as .*$", ""), (r"\bt/a .*$", "")]


def norm_text(s) -> str:
    if s is None:
        return ""
    s = str(s).lower()
    s = s.replace("&", "and").replace("’", "'").replace("–", "-").replace("—", "-")
    for pat, rep in _ORG_SUBS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm_text(a), norm_text(b)).ratio()


def norm_cpv(code) -> str:
    return re.sub(r"\D", "", str(code))[:8]


def to_bool(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    return None


def to_int(v) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    m = re.search(r"-?\d+", str(v).replace(",", ""))
    return int(m.group(0)) if m else None


def to_float(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v).replace(",", ""))
    return float(m.group(0)) if m else None

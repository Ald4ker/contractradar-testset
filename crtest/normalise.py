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


_ISO = re.compile(r"\b(\d{4})([-/.])(\d{1,2})\2(\d{1,2})(?!\d)")                    # 2026-03-03, 2026/3/3, 2026-03-03T09:00
_DMY = re.compile(r"\b(\d{1,2})([/.-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")                # 03/03/2026, 3-3-2026, 03.03.26
_D_MON_Y = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[ -]([A-Za-z]{3,9})\.?[ ,-]*(\d{4}|\d{2})(?!\d)")   # 3rd March 2026, 03-Mar-26
_MON_D_Y = re.compile(r"\b([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})(?!\d)")    # March 3rd, 2026


def _month(word: str) -> int | None:
    w = word.lower()
    return MONTHS.get(w) or (9 if w == "sept" else None)


def _iso(y: int, mo: int | None, d: int) -> str | None:
    if not mo:
        return None
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _year(s: str) -> int:
    y = int(s)
    return y if len(s) == 4 else y + (2000 if y < 69 else 1900)   # 2-digit years as strptime's %y


def parse_date(s) -> str | None:
    """Return ISO date or None. Accepts 3 March 2026, 3rd March 2026, March 3rd, 2026, 03/03/2026, 03-03-2026, 03.03.26,
    2026-03-03 (also with a time after it), 2026/03/03, 03-Mar-2026, 3 Sept 2026. Numeric dates are day first, as in the
    UK: 01/02/2026 is 1 February 2026. Month names must be names or abbreviations, and impossible dates are not dates."""
    if s is None:
        return None
    if isinstance(s, dt.datetime):
        return s.date().isoformat()
    if isinstance(s, dt.date):
        return s.isoformat()
    s = str(s).strip()
    for pattern, ymd in ((_ISO, lambda m: (int(m[1]), int(m[3]), int(m[4]))),
                         (_DMY, lambda m: (_year(m[4]), int(m[3]), int(m[1]))),
                         (_D_MON_Y, lambda m: (_year(m[3]), _month(m[2]), int(m[1]))),
                         (_MON_D_Y, lambda m: (int(m[3]), _month(m[1]), int(m[2])))):
        for m in pattern.finditer(s):
            d = _iso(*ymd(m))
            if d:
                return d
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

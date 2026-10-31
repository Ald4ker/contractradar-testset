"""Reference checks against the Procurement Act 2023.

This is NOT a substitute for ContractRadar's rule engine. It exists so that
every synthetic case carries a set of *expected* flags, computed from the
gold fields, which a real rule engine can be scored against.

Thresholds are inclusive of VAT (Sch 1, as amended by SI 2025/1200 from
1 January 2026). Procurements commenced before 1 Jan 2026 use the earlier
figures; both sets are kept here.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

THRESHOLDS = {
    # date from which the row applies -> {category: £ inc VAT}
    "2024-01-01": {
        "sub_central_goods_services": 214_904,
        "central_goods_services": 139_688,
        "works": 5_372_609,
        "light_touch": 663_540,
    },
    "2026-01-01": {
        "sub_central_goods_services": 207_720,
        "central_goods_services": 135_018,
        "works": 5_193_000,
        "light_touch": 663_540,
    },
}

FIVE_MILLION = 5_000_000  # s.52 KPIs, s.53(3)/s.77 publish contract, s.71 performance notices
STANDSTILL_WORKING_DAYS = 8  # s.51
CDN_DAYS = 30  # s.53(2): contract details notice within 30 days of entering into the contract
IMPLIED_PAYMENT_DAYS = 30  # s.68
MOD_VALUE_PCT = {"goods": 10.0, "services": 10.0, "works": 15.0}  # s.74(4), s.75(2)
MOD_TERM_PCT = 10.0  # s.74(3)(a), s.75(2)(b)
SCH8_PARA3_CAP_PCT = 50.0  # Sch 8 para 3(2) unforeseeable circumstances
SCH8_PARA5_CAP_PCT = 50.0  # Sch 8 para 5 additional goods/services/works

SCH8_GROUNDS = {
    "sch8_para1_provided_for",
    "sch8_para2_urgency",
    "sch8_para3_unforeseeable",
    "sch8_para4_known_risk",
    "sch8_para5_additional",
    "sch8_para6_restructuring",
}


def thresholds_for(date: dt.date | None) -> dict[str, int]:
    keys = sorted(THRESHOLDS)
    chosen = keys[0]
    if date is not None:
        for k in keys:
            if date >= dt.date.fromisoformat(k):
                chosen = k
    return THRESHOLDS[chosen]


def _d(v: Any) -> dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def working_days_between(a: dt.date, b: dt.date) -> int:
    """Working days strictly after a up to and including b (Mon-Fri, no bank holidays)."""
    if b <= a:
        return 0
    n = 0
    cur = a
    while cur < b:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def expected_flags(f: dict[str, Any]) -> list[dict[str, str]]:
    """Compute the flags a rule engine should raise for these gold fields."""
    flags: list[dict[str, str]] = []
    ntype = f.get("notice_type")
    ptype = f.get("procurement_type") or "services"
    value = f.get("contract_value_gbp")
    is_modification = f.get("modification_number") is not None
    if is_modification and value is None:
        value = f.get("original_contract_value_gbp")
    pub = _d(f.get("notice_published_date"))
    ref_date = pub or _d(f.get("award_date")) or _d(f.get("contract_signed_date"))
    th = thresholds_for(ref_date)
    if f.get("light_touch"):
        threshold = th["light_touch"]
    elif ptype == "works":
        threshold = th["works"]
    else:
        threshold = th["sub_central_goods_services"] if f.get("contracting_authority_type") != "central" else th["central_goods_services"]

    if value is not None and value >= threshold:
        row = "light touch" if f.get("light_touch") else ptype
        flags.append({
            "id": "PA23-threshold-in-scope",
            "severity": "info",
            "detail": f"Value £{value:,.0f} is at or above the {row} threshold £{threshold:,} (inc VAT) applicable on {ref_date}.",
        })

    if ntype == "contract_award_notice":
        se = _d(f.get("standstill_end_date"))
        if se and pub and working_days_between(pub, se) < STANDSTILL_WORKING_DAYS:
            flags.append({
                "id": "PA23-s51-standstill-short",
                "severity": "high",
                "detail": f"Standstill ends {se} which is only {working_days_between(pub, se)} working days after publication on {pub}; s.51 requires 8.",
            })
        if f.get("procedure") == "direct_award" and value is not None and value >= threshold:
            flags.append({
                "id": "AUDIT-direct-award-above-threshold",
                "severity": "medium",
                "detail": "Direct award of an above-threshold contract: a s.41 justification must be recorded in the notice.",
            })

    if ntype in ("contract_details_notice", "contract_document", "contract_award_notice"):
        kpis = f.get("kpis") or []
        if value is not None and value > FIVE_MILLION and len(kpis) < 3 and ntype != "contract_award_notice":
            flags.append({
                "id": "PA23-s52-kpi-min3",
                "severity": "high",
                "detail": f"Value £{value:,.0f} exceeds £5m but only {len(kpis)} KPI(s) set; s.52 requires at least three unless inappropriate.",
            })
        pt = f.get("payment_terms_days")
        if pt is not None and pt > IMPLIED_PAYMENT_DAYS:
            flags.append({
                "id": "PA23-s68-payment-over-30d",
                "severity": "medium",
                "detail": f"Payment terms of {pt} days exceed the 30-day implied term in s.68.",
            })

    if ntype == "contract_details_notice":
        signed = _d(f.get("contract_signed_date"))
        if signed and pub and (pub - signed).days > CDN_DAYS:
            flags.append({
                "id": "PA23-s53-cdn-late",
                "severity": "medium",
                "detail": f"Contract entered into {signed}, notice published {pub}: {(pub - signed).days} days, over the 30-day limit in s.53.",
            })

    if is_modification:
        orig_v = f.get("original_contract_value_gbp")
        delta_v = f.get("value_change_gbp") or 0
        pct_v = f.get("value_change_percent")
        if pct_v is None and orig_v:
            pct_v = round(100.0 * delta_v / orig_v, 1)
        pct_v = pct_v or 0.0
        term_delta = f.get("term_change_months") or 0
        max_term = f.get("maximum_term_months")
        pct_t = round(100.0 * term_delta / max_term, 1) if max_term else 0.0
        ground = f.get("modification_ground")
        cap = MOD_VALUE_PCT.get(ptype, 10.0)
        ccn_required = abs(pct_v) > cap or abs(pct_t) > MOD_TERM_PCT

        if ground == "s74_below_threshold" and abs(pct_v) > cap:
            flags.append({
                "id": "PA23-s74-exceeds-below-threshold",
                "severity": "high",
                "detail": f"Value change {pct_v:+.1f}% exceeds the {cap:.0f}% below-threshold limit for {ptype} in s.74(4).",
            })
        if abs(pct_t) > MOD_TERM_PCT and ground not in SCH8_GROUNDS:
            flags.append({
                "id": "PA23-s74-substantial-term",
                "severity": "high",
                "detail": f"Term change {term_delta:+d} months is {pct_t:+.1f}% of the {max_term}-month maximum term: a substantial modification under s.74(3)(a) with no Schedule 8 ground.",
            })
        if ground == "sch8_para3_unforeseeable" and pct_v > SCH8_PARA3_CAP_PCT:
            flags.append({
                "id": "PA23-sch8-para3-cap-50pc",
                "severity": "high",
                "detail": f"Increase of {pct_v:.1f}% exceeds the 50% cap in Schedule 8 para 3.",
            })
        if ccn_required and f.get("contract_change_notice_published") is False:
            flags.append({
                "id": "PA23-s75-ccn-required-not-published",
                "severity": "high",
                "detail": f"Value change {pct_v:+.1f}% / term change {pct_t:+.1f}% exceeds the s.75(2) exemption but no contract change notice was published.",
            })
        rev_v = f.get("revised_contract_value_gbp")
        if ccn_required and rev_v is not None and rev_v > FIVE_MILLION:
            flags.append({
                "id": "PA23-s77-publish-modified-contract",
                "severity": "info",
                "detail": "Qualifying modification to a contract over £5m: publish a copy of the contract as modified within 90 days (s.77).",
            })
        orig_end = _d(f.get("original_end_date"))
        mod_date = _d(f.get("modification_date"))
        if orig_end and mod_date and mod_date > orig_end:
            flags.append({
                "id": "AUDIT-retrospective-extension",
                "severity": "high",
                "detail": f"Modification dated {mod_date} but the contract expired on {orig_end}: a retrospective extension of an expired contract.",
            })
    return flags

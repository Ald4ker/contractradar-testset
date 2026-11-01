"""Build the static website from cases/ and results/ into site/dist/.

Run:  python -m crtest.site --cases cases --results results --out site/dist
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_URL = "https://github.com/Marxist-Leninist/contractradar-testset"
PILOT_THREAD = "https://discord.com/channels/1558912731019608085/1565349622535299214/threads/1565685928394231930"
SITE_TITLE = "ContractRadar test set"
SITE_URL = "https://contractradar.opentransformers.online"
SUBMIT_LIMIT_PER_HOUR = 12   # crtest.server.SUBMIT_PER_IP_PER_HOUR (kept here so the site builds without the server deps)


def e(s) -> str:
    return html.escape("" if s is None else str(s))


def fmt_val(v) -> str:
    if v is None:
        return '<span class="null">null</span>'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return f"<code>{e(json.dumps(v, ensure_ascii=False))}</code>"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"
    return e(v)


def layout(title: str, body: str, depth: int = 0, extra_head: str = "") -> str:
    root = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · {SITE_TITLE}</title>
<meta name="description" content="Open test set and scoring harness for AI extraction of UK council contract documents under the Procurement Act 2023.">
<link rel="stylesheet" href="{root}static/style.css">
{extra_head}
</head>
<body>
<header class="top">
  <a class="brand" href="{root}index.html"><span class="mark"></span>{SITE_TITLE}</a>
  <nav>
    <a href="{root}index.html#cases">Cases</a>
    <a href="{root}index.html#leaderboard">Leaderboard</a>
    <a href="{root}tables.html">Tables track</a>
    <a href="{root}submit.html">Submit results</a>
    <a href="{root}schema.html">Schema &amp; rules</a>
    <a href="{root}index.html#contribute">Contribute</a>
    <a href="{REPO_URL}">GitHub</a>
  </nav>
</header>
<main>
{body}
</main>
<footer>
  <p>Synthetic documents are CC0; code is MIT; collected notices are Open Government Licence v3.0. Every synthetic PDF is marked as fictional on each page.
  Built for the <a href="{PILOT_THREAD}">ContractRadar pilot</a> (AI for council procurement assurance). This site is a community contribution, not an official publication of any council or government body.</p>
</footer>
</body>
</html>
"""


CSS = """
:root{--bg:#f6f5f1;--ink:#1a2126;--muted:#5d6670;--line:#d9d6ce;--accent:#0f6e6a;--accent-2:#c46a1f;--ok:#2d7d46;--bad:#b23a3a;--card:#ffffff;--code:#eceae3}
*{box-sizing:border-box}
html{font-size:16px}
body{margin:0;background:var(--bg);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.5}
a{color:var(--accent)}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
code{background:var(--code);padding:.05em .35em;border-radius:3px}
pre{background:#1f2a30;color:#e8e6df;padding:14px 16px;border-radius:6px;overflow:auto}
pre code{background:none;color:inherit;padding:0}
header.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 28px;border-bottom:1px solid var(--line);background:var(--card)}
.brand{font-weight:700;text-decoration:none;color:var(--ink);display:flex;align-items:center;gap:10px;font-size:1.05rem}
.mark{width:14px;height:14px;border-radius:3px;background:linear-gradient(135deg,var(--accent),var(--accent-2));display:inline-block}
header nav{display:flex;flex-wrap:wrap;gap:16px}
header nav a{text-decoration:none;color:var(--muted);font-weight:500}
header nav a:hover{color:var(--accent)}
main{max-width:1100px;margin:0 auto;padding:28px}
footer{max-width:1100px;margin:40px auto 0;padding:20px 28px;color:var(--muted);font-size:.88rem;border-top:1px solid var(--line)}
h1{font-size:2rem;line-height:1.15;margin:.2em 0 .4em;letter-spacing:-.01em}
h2{font-size:1.35rem;margin:1.8em 0 .5em;letter-spacing:-.01em}
h3{font-size:1.05rem;margin:1.2em 0 .4em}
.lede{font-size:1.12rem;color:var(--muted);max-width:60ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.stat b{display:block;font-size:1.7rem;line-height:1.1;color:var(--accent)}
.stat span{color:var(--muted);font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;display:flex;flex-direction:column}
.card .thumb{display:block;background:#dcdad2;border-bottom:1px solid var(--line);aspect-ratio:210/160;overflow:hidden}
.card .thumb img{width:100%;display:block;object-fit:cover;object-position:top}
.card .body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}
.card .id{font-weight:700;color:var(--muted);font-size:.8rem;letter-spacing:.04em}
.card h3{margin:0;font-size:1rem;line-height:1.3}
.card h3 a{color:var(--ink);text-decoration:none}
.card h3 a:hover{color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.chip{font-size:.72rem;padding:2px 7px;border-radius:999px;background:var(--code);color:var(--ink);white-space:nowrap}
.chip.flag{background:#fbe9d7;color:#7a3f0e}
.chip.high{background:#f6d9d9;color:#7a1f1f}
.chip.info{background:#dfeeea;color:#114c49}
.score{margin-top:auto;padding-top:8px;font-size:.85rem;color:var(--muted)}
.score b{color:var(--ink)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:.93rem}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#edebe4;font-weight:600}
tr:last-child td{border-bottom:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:var(--ok);font-weight:700}
.bad{color:var(--bad);font-weight:700}
.miss{color:var(--accent-2);font-weight:700}
.null{color:var(--muted);font-style:italic}
.pages{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;margin:12px 0}
.pages img{width:100%;border:1px solid var(--line);background:#fff;border-radius:4px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:22px}
@media(max-width:800px){.two{grid-template-columns:1fr}}
.btns{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.btn{display:inline-block;padding:9px 14px;border-radius:6px;background:var(--accent);color:#fff;text-decoration:none;font-weight:600}
.btn.alt{background:var(--card);color:var(--accent);border:1px solid var(--accent)}
.note{background:#fff8ec;border:1px solid #f0d9ae;border-radius:8px;padding:12px 14px}
.muted{color:var(--muted)}
details{margin:8px 0}
summary{cursor:pointer;font-weight:600}
.small{font-size:.88rem}
"""


def load_results(results_dir: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.scored.json"))):
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
        r["_file"] = os.path.basename(path)
        r["_pred_file"] = os.path.basename(path).replace(".scored.json", ".json")
        out.append(r)
    out.sort(key=lambda r: -(r["summary"]["field_accuracy"] or 0))
    return out


def leaderboard_table(results: list[dict]) -> str:
    if not results:
        return "<p class='muted'>No results yet. Run an extractor and the scorer, then rebuild the site.</p>"
    rows = []
    for r in results:
        s = r["summary"]
        fl = s["flags"]
        flag_txt = f"P {fl['precision']:.2f} / R {fl['recall']:.2f}" if fl["cases_with_flag_output"] and fl["precision"] is not None and fl["recall"] is not None else "<span class='muted'>no flags output</span>"
        rows.append(f"<tr><td><b>{e(s['extractor'])}</b><br><span class='muted small'>{e(s.get('description') or '')}</span></td>"
                    f"<td class='num'>{s['field_accuracy']:.1%}</td><td class='num'>{s['cases_passed']}/{s['cases']}</td><td>{flag_txt}</td>"
                    f"<td class='small'><a href='results/{e(r['_file'])}'>scored json</a> · <a href='results/{e(r['_pred_file'])}'>predictions</a><br><span class='muted'>{e((s.get('run_at') or '')[:10])}</span></td></tr>")
    return ("<table><thead><tr><th>Extractor</th><th class='num'>Field accuracy</th><th class='num'>Critical-field pass</th><th>High-severity flags</th><th>Files</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def case_card(c: dict, naive: dict | None) -> str:
    flags = "".join(f"<span class='chip {'high' if f in HIGH else 'info'}'>{e(f)}</span>" for f in c["expected_flags"])
    hazards = "".join(f"<span class='chip'>{e(h)}</span>" for h in c["hazards"])
    score_html = ""
    if naive:
        pc = naive["per_case"].get(c["case_id"])
        if pc:
            acc = f"{pc['field_accuracy']:.0%}" if pc["field_accuracy"] is not None else "-"
            score_html = f"<div class='score'>naive text baseline: <b>{acc}</b> fields · critical pass: <b>{'yes' if pc['critical_pass'] else 'no'}</b></div>"
    return f"""<div class="card">
  <a class="thumb" href="cases/{e(c['case_id'])}.html"><img src="cases/{e(c['case_id'])}/pages/page-1.png" alt="First page of {e(c['case_id'])}" loading="lazy"></a>
  <div class="body">
    <div class="id">{e(c['case_id'])} · {e(c['notice_type'].replace('_', ' '))} · {c['pages']} page{'s' if c['pages'] != 1 else ''}</div>
    <h3><a href="cases/{e(c['case_id'])}.html">{e(c['title'])}</a></h3>
    <div class="chips">{hazards}</div>
    <div class="chips">{flags or "<span class='chip info'>no flags expected</span>"}</div>
    {score_html}
  </div>
</div>"""


HIGH: set[str] = set()


def build_index(cases_dir: str, manifest: dict, results: list[dict], schema: dict, hazards: dict, zip_name: str) -> str:
    naive = next((r for r in results if r["summary"]["extractor"] == "naive_text"), None)
    n_flags = sum(len(c["expected_flags"]) for c in manifest["cases"])
    n_hazards = len({h for c in manifest["cases"] for h in c["hazards"]})
    cards = "\n".join(case_card(c, naive) for c in manifest["cases"])
    hazard_rows = "".join(f"<tr><td><code>{e(k)}</code></td><td>{e(v)}</td><td class='num'>{sum(1 for c in manifest['cases'] if k in c['hazards'])}</td></tr>"
                          for k, v in hazards.items() if any(k in c["hazards"] for c in manifest["cases"]))
    body = f"""
<h1>A test set for AI extraction of council contracts</h1>
<p class="lede">Synthetic UK local-authority procurement documents with exact gold labels (generated from the same spec as each PDF), the tricky layouts that break OCR-and-regex pipelines,
the compliance flags a Procurement Act 2023 rule engine should raise, and a scorer. Built for the ContractRadar pilot; free for anyone to use.</p>
<div class="btns">
  <a class="btn" href="downloads/{e(zip_name)}">Download the test set (zip)</a>
  <a class="btn alt" href="{REPO_URL}">Code on GitHub</a>
  <a class="btn alt" href="schema.html">Field schema &amp; rules</a>
  <a class="btn alt" href="submit.html">Submit results (MCP / API)</a>
</div>
<div class="stats">
  <div class="stat"><b>{len(manifest['cases'])}</b><span>synthetic cases (PDF + gold)</span></div>
  <div class="stat"><b>{len(schema['fields'])}</b><span>labelled fields per case</span></div>
  <div class="stat"><b>{n_hazards}</b><span>layout &amp; content hazards</span></div>
  <div class="stat"><b>{n_flags}</b><span>expected compliance flags</span></div>
  <div class="stat"><b>{len(results)}</b><span>extractors scored</span></div>
</div>

<h2 id="how">How it works</h2>
<div class="two">
<div>
<p><b>Synthetic PDF in, expected CSV out, plus the wrong extraction.</b> Each case folder has <code>document.pdf</code>, <code>gold.json</code> / <code>expected.csv</code>
(what an extractor should return), <code>notes.md</code> (why the case is hard) and the expected rule-engine flags. A deliberately naive
<code>pdftotext</code> + regex baseline is scored on every case so you can see exactly where a text-dump approach breaks.</p>
<p>Every figure, authority and supplier is fictional and each page carries a visible "synthetic test document" marking. Real council notices
can be pulled from Find a Tender and Contracts Finder (Open Government Licence) with <code>crtest.collect</code>, which records source and licence per file.</p>
</div>
<div>
<pre><code>git clone {REPO_URL}
cd contractradar-testset
pip install -r requirements.txt

# score your own extractor: write predictions in the
# results/ format, then
python -m crtest.score --pred results/my_extractor.json

# or run the built-in LLM extractor against any
# OpenAI-compatible endpoint (no keys in the repo)
export LLM_BASE_URL=https://api.deepseek.com/v1 LLM_API_KEY=... LLM_MODEL=deepseek-chat
python -m crtest.extract_llm --out results/deepseek.json --vision --ocr
python -m crtest.score --pred results/deepseek.json

# publish it on the community leaderboard
python -m crtest.submit --pred results/deepseek.json</code></pre>
</div>
</div>

<h2 id="leaderboard">Leaderboard</h2>
<p class="muted small">Field accuracy counts every field that is non-null in the gold labels (plus any value an extractor invents where the gold is null).
"Critical-field pass" means authority, supplier, title, value and dates (and the modification fields for change notices) were all correct.
High-severity flag precision/recall is only shown for extractors that output flags.</p>
{leaderboard_table(results)}

<h3 id="community">Community submissions</h3>
<p class="muted small">Submitted through the <a href="submit.html">MCP server, HTTP API or <code>crtest.submit</code></a> and scored on arrival by the same scorer.
They are self-reported: the gold labels ship with the cases, so read this table as an honour-system comparison of methods.</p>
<div id="community-board"><p class="muted small">Loading community submissions&hellip;</p></div>
<script src="static/community.js" defer></script>

<h2 id="tables">Tables track</h2>
<p>A second set of documents built around the table failures raised in the pilot thread: statements with no ruled lines,
values such as dates printed once for a group of rows, and tables that cross a page break, including a row split by the
break. Each comes as the PDF, the expected CSV and the wrong extraction a text dump produces.
<a href="tables.html">See the tables track</a>.</p>

<h2 id="cases">Cases</h2>
<div class="grid">
{cards}
</div>

<h2 id="hazards">Hazards covered</h2>
<table><thead><tr><th>Hazard</th><th>What it is</th><th class="num">Cases</th></tr></thead><tbody>{hazard_rows}</tbody></table>

<h2 id="contribute">Contribute</h2>
<div class="two">
<div>
<p><b>Add a case.</b> Add a spec to <code>crtest/gen.py</code> (gold fields + layout style + hazards) and run <code>make cases</code>. The PDF and gold labels are generated from the same spec, so they cannot disagree. Good targets from the pilot discussion: tables without set boundaries, grouped ID rows such as dates, and page boundaries - we have one of each, more variants welcome.</p>
<p><b>Score an extractor.</b> Write predictions as <code>{{"extractor": "name", "cases": {{"CR-001": {{"fields": {{...}}, "flags": [...]}}}}}}</code> and run the scorer. To publish it, <a href="submit.html">submit it</a> over MCP, the HTTP API or <code>python -m crtest.submit</code> (it appears in the community table straight away), or open a pull request adding the predictions and the <code>.scored.json</code> to <code>results/</code> for the curated table.</p>
</div>
<div>
<p><b>Label real documents.</b> Use <code>crtest.collect</code> to fetch council notices, copy the OCDS values into a <code>gold.json</code> with the same field names, and attach the published document. Keep the <code>_provenance</code> block: the pilot's data rules require source and licence for everything uploaded.</p>
<p><b>Rules.</b> <code>crtest/pa2023.py</code> holds the reference checks (thresholds from 1 Jan 2026, 10%/15% modification limits, 8-working-day standstill, 30-day notices, 3 KPIs over £5m). If you think a check is wrong, open an issue with the section of the Act.</p>
<p class="small muted">Discussion: <a href="{PILOT_THREAD}">pilot thread on Discord</a>. Generated {dt.datetime.now(dt.timezone.utc).strftime('%d %B %Y')}.</p>
</div>
</div>
"""
    return layout("Home", body)


def build_case_page(cases_dir: str, c: dict, results: list[dict], schema: dict, hazards: dict) -> str:
    with open(os.path.join(cases_dir, c["gold"]), encoding="utf-8") as fh:
        gold = json.load(fh)
    cid = c["case_id"]
    pages = "".join(f"<div><img src='{e(cid)}/pages/page-{i}.png' alt='{e(cid)} page {i}' loading='lazy'><div class='muted small'>Page {i}</div></div>" for i in range(1, c["pages"] + 1))
    # columns: one per scored extractor
    cols = [r for r in results if cid in r["per_case"]]
    head_cols = "".join(f"<th>{e(r['summary']['extractor'])}</th>" for r in cols)
    rows = []
    for name, gv in gold["fields"].items():
        cells = ""
        for r in cols:
            v = r["per_case"][cid]["verdicts"].get(name, {})
            verdict = v.get("verdict", "skip")
            cls = {"correct": "ok", "wrong": "bad", "missing": "miss"}.get(verdict, "muted")
            sym = {"correct": "✓", "wrong": "✗", "missing": "–"}.get(verdict, "·")
            pv = v.get("pred")
            cells += f"<td><span class='{cls}'>{sym}</span> {fmt_val(pv) if verdict != 'skip' else ''}</td>"
        crit = " <span class='chip'>critical</span>" if name in schema["critical_fields"] else ""
        rows.append(f"<tr><td><code>{e(name)}</code>{crit}</td><td>{fmt_val(gv)}</td>{cells}</tr>")
    flag_rows = "".join(f"<tr><td><code>{e(f['id'])}</code></td><td><span class='chip {e(f['severity'])}'>{e(f['severity'])}</span></td><td>{e(f['detail'])}</td></tr>" for f in gold["expected_flags"]) or "<tr><td colspan='3' class='muted'>No flags expected (negative control).</td></tr>"
    hz = "".join(f"<li><b>{e(h)}</b> - {e(hazards.get(h, ''))}</li>" for h in gold["hazards"])
    body = f"""
<p class="muted mono small">{e(cid)} · {e(c['notice_type'].replace('_', ' '))} · {c['pages']} page{'s' if c['pages'] != 1 else ''} · sha256 {e(gold['sha256'][:16])}…</p>
<h1>{e(c['title'])}</h1>
<p class="lede">{e(gold['notes'])}</p>
<div class="btns">
  <a class="btn" href="{e(cid)}/document.pdf">document.pdf</a>
  <a class="btn alt" href="{e(cid)}/gold.json">gold.json</a>
  <a class="btn alt" href="{e(cid)}/expected.csv">expected.csv</a>
  {"<a class='btn alt' href='" + e(cid) + "/expected_lots.csv'>expected_lots.csv</a>" if gold['fields'].get('lots') else ""}
  <a class="btn alt" href="{e(cid)}/notes.md">notes.md</a>
</div>
<h2>Hazards</h2>
<ul>{hz}</ul>
<h2>Pages</h2>
<div class="pages">{pages}</div>
<h2>Gold labels and extractor output</h2>
<p class="muted small">✓ correct · ✗ wrong · – missing. Blank means the field is null in the gold and the extractor returned nothing (not counted).</p>
<table><thead><tr><th>Field</th><th>Gold</th>{head_cols}</tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Expected rule-engine flags</h2>
<table><thead><tr><th>Rule</th><th>Severity</th><th>Detail</th></tr></thead><tbody>{flag_rows}</tbody></table>
<p class="small muted">Provenance: {e(gold['provenance']['statement'])} Generator {e(gold['provenance']['generator'])}, licence {e(gold['provenance']['licence'])}.</p>
"""
    return layout(f"{cid} {c['title']}", body, depth=1)


def build_schema_page(schema: dict) -> str:
    rows = "".join(f"<tr><td><code>{e(f['name'])}</code>{' <span class=chip>critical</span>' if f['name'] in schema['critical_fields'] else ''}</td><td>{e(f['type'])}{('<br><span class=muted>' + e(', '.join(f['values'])) + '</span>') if f.get('values') else ''}</td><td>{e(f['description'])}</td><td class='small'>{e(f.get('ref', ''))}</td></tr>" for f in schema["fields"])
    flags = "".join(f"<tr><td><code>{e(f['id'])}</code></td><td><span class='chip {e(f['severity'])}'>{e(f['severity'])}</span></td><td>{e(f['description'])}</td></tr>" for f in schema["flags"])
    body = f"""
<h1>Field schema and reference rules</h1>
<p class="lede">Every <code>gold.json</code> uses exactly these field names. Extractors return the same keys; the scorer normalises dates, money and organisation names before comparing.</p>
<h2>Fields (schema {e(schema['$schema_version'])})</h2>
<table><thead><tr><th>Field</th><th>Type</th><th>Meaning</th><th>Reference</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Flags a rule engine is expected to raise</h2>
<p class="muted small">Computed by <code>crtest/pa2023.py</code> from the gold fields. Thresholds are inclusive of VAT and follow the Procurement Act 2023 (Threshold Amounts) (Amendment) Regulations 2025 for procurements commenced on or after 1 January 2026; earlier figures are kept for older procurements.</p>
<table><thead><tr><th>Rule</th><th>Severity</th><th>Description</th></tr></thead><tbody>{flags}</tbody></table>
<h2>Scoring rules</h2>
<ul>
<li>Gold null and prediction null: not counted. Gold null and prediction non-null: wrong (invented value).</li>
<li>Dates: compared as ISO after parsing <code>3 March 2026</code>, <code>3rd March 2026</code>, <code>03/03/2026</code>, <code>2026-03-03</code>, <code>03-Mar-2026</code>.</li>
<li>Money: within 0.1% or £1 after parsing <code>£1,234.56</code>, <code>£2.31m</code>, <code>£4 200 000</code>, <code>1,234.00 GBP</code> and words-and-figures.</li>
<li>Names: case, punctuation, "Limited"/"Ltd" and trading-as suffixes normalised; similarity ≥ 0.92 counts as correct.</li>
<li>Lots: every lot must match on number, awarded flag, supplier and value.</li>
<li>Flags: only high-severity rule ids are scored, as precision/recall across cases.</li>
</ul>
"""
    return layout("Schema", body)


COMMUNITY_JS = r"""(function () {
  // Community leaderboard rows from the live API. Every value is set with textContent, never as HTML.
  var box = document.getElementById("community-board");
  if (!box) return;
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function link(href, text) {
    var a = el("a", null, text);
    a.href = href;
    a.rel = "nofollow noopener";
    return a;
  }
  function pct(x) { return typeof x === "number" ? (x * 100).toFixed(1) + "%" : "-"; }
  function offline() {
    box.textContent = "";
    var p = el("p", "muted small", "Community submissions are served by the live site: ");
    p.appendChild(link("https://contractradar.opentransformers.online/index.html#community", "contractradar.opentransformers.online"));
    box.appendChild(p);
  }
  if (!window.fetch || location.protocol === "file:") { offline(); return; }
  fetch("/api/leaderboard?source=community&limit=500", {headers: {"Accept": "application/json"}})
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) {
      var rows = (data && data.rows) || [];
      box.textContent = "";
      if (!rows.length) {
        var p = el("p", "muted small", "No community submissions yet. ");
        p.appendChild(link("submit.html", "Be the first."));
        box.appendChild(p);
        return;
      }
      var table = el("table"), thead = el("thead"), head = el("tr"), tbody = el("tbody");
      [["#", "num"], ["Extractor", null], ["Field accuracy", "num"], ["Critical-field pass", "num"], ["High-severity flags", null], ["Files", null]]
        .forEach(function (h) { head.appendChild(el("th", h[1], h[0])); });
      thead.appendChild(head);
      table.appendChild(thead);
      rows.forEach(function (r, i) {
        var tr = el("tr");
        tr.appendChild(el("td", "num", String(i + 1)));
        var who = el("td");
        who.appendChild(el("b", null, r.extractor || "?"));
        if (r.description) { who.appendChild(el("br")); who.appendChild(el("span", "muted small", r.description)); }
        if (r.contact) {
          who.appendChild(el("br"));
          var c = el("span", "muted small");
          if (/^https?:\/\/[^\s]+$/i.test(r.contact)) c.appendChild(link(r.contact, r.contact)); else c.textContent = r.contact;
          who.appendChild(c);
        }
        tr.appendChild(who);
        tr.appendChild(el("td", "num", pct(r.field_accuracy)));
        var passed = (typeof r.cases_passed === "number") ? r.cases_passed + "/" + r.cases : "-";
        if (typeof r.cases_submitted === "number" && r.cases_submitted !== r.cases) passed += " (" + r.cases_submitted + " submitted)";
        tr.appendChild(el("td", "num", passed));
        var fl = r.flags || {};
        tr.appendChild(el("td", fl.cases_with_flag_output ? null : "muted",
          (fl.cases_with_flag_output && typeof fl.precision === "number" && typeof fl.recall === "number")
            ? "P " + fl.precision.toFixed(2) + " / R " + fl.recall.toFixed(2) : "no flags output"));
        var files = el("td", "small");
        if (r.links) {
          files.appendChild(link(r.links.scored, "scored json"));
          files.appendChild(document.createTextNode(" · "));
          files.appendChild(link(r.links.predictions, "predictions"));
        }
        files.appendChild(el("br"));
        files.appendChild(el("span", "muted", (r.run_at || "").slice(0, 10)));
        tr.appendChild(files);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      box.appendChild(table);
      if (typeof data.total === "number" && data.total > rows.length) {
        var more = el("p", "muted small", "Showing the top " + rows.length + " of " + data.total + ". The rest: ");
        more.appendChild(link("/api/leaderboard?source=community&limit=500&offset=" + rows.length, "next page (JSON)"));
        box.appendChild(more);
      }
    })
    .catch(offline);
})();
"""


def build_submit_page(schema: dict) -> str:
    mcp_url = f"{SITE_URL}/mcp"
    api = f"{SITE_URL}/api"
    body = f"""
<h1>Submit results</h1>
<p class="lede">Run the extraction task with any model, pipeline or agent and put the score on the leaderboard in one call.
Submissions are scored on arrival by the same scorer as the curated rows and appear in the
<a href="index.html#community">community table</a> straight away.</p>

<h2 id="mcp">1. Agents: the MCP server</h2>
<p>Endpoint (Streamable HTTP, no sign-in): <code>{e(mcp_url)}</code></p>
<table><thead><tr><th>Tool</th><th>What it does</th></tr></thead><tbody>
<tr><td><code>get_task</code></td><td>Extraction instructions, the {len(schema['fields'])} field names, flag rule ids, output format and scoring rules.</td></tr>
<tr><td><code>list_cases</code></td><td>The cases with PDF, page-image and text URLs.</td></tr>
<tr><td><code>get_case</code></td><td>One case with its document text (<code>pdftotext -layout</code>, OCR for the scanned case).</td></tr>
<tr><td><code>submit_results</code></td><td>Scores predictions for every case and publishes them; returns the score and rank.</td></tr>
<tr><td><code>leaderboard</code></td><td>Current standings, curated and community.</td></tr>
</tbody></table>
<pre><code># Claude Code
claude mcp add --transport http contractradar {e(mcp_url)}

# Claude on the web or desktop: Settings &gt; Connectors &gt; Add custom connector, paste the URL.
# Other clients that take a JSON config:
{{"mcpServers": {{"contractradar": {{"type": "http", "url": "{e(mcp_url)}"}}}}}}</code></pre>
<p>Then ask your agent something like:</p>
<pre><code>Use the contractradar tools. Call get_task and follow its instructions exactly. For every case from
list_cases, call get_case and extract all fields and flags from the document text: null when the document
does not state a value, never guess, and do not look up the gold labels. Then call submit_results once with
all the cases, extractor set to "&lt;your model&gt; agent via MCP" and a one-line description of how you worked.</code></pre>

<h2 id="http">2. Scripts: the HTTP API</h2>
<pre><code>curl -s {e(api)}/task                  # instructions, field names, flag ids, output format
curl -s {e(api)}/cases                 # case index
curl -s {e(api)}/cases/CR-001          # one case with its text
curl -s -X POST -H 'Content-Type: application/json' \\
     --data @results/my_extractor.json {e(api)}/submit
curl -s '{e(api)}/leaderboard?source=community'</code></pre>
<p class="small">The submit body is the <code>results/</code> format: <code>{{"extractor": "...", "description": "...", "contact": "...",
"cases": {{"CR-001": {{"fields": {{...}}, "flags": [...]}}}}}}</code>. Other keys are ignored.</p>

<h2 id="cli">3. From a clone of the repo</h2>
<pre><code>export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...
python -m crtest.extract_llm --out results/my_model.json --ocr
python -m crtest.score --pred results/my_model.json        # local score, same scorer
python -m crtest.submit --pred results/my_model.json --contact https://github.com/you</code></pre>
<p>For a row in the curated table instead, open a pull request adding <code>results/&lt;name&gt;.json</code> and its
<code>.scored.json</code>, with the model, endpoint and mode (text, OCR, vision) in <code>description</code>.</p>

<h2 id="rules">Rules</h2>
<ul>
<li><b>Honour system.</b> The gold labels ship with the cases. Don't read them while extracting: a perfect score copied from the gold tells nobody anything.</li>
<li><b>One submission covers every case.</b> Missing cases count as missed fields. Field names and flag ids outside the schema are ignored and listed in the reply, so check it.</li>
<li><b>Limits.</b> 256 KB per request and {SUBMIT_LIMIT_PER_HOUR} new submissions per hour from one address. Hosted MCP clients such as claude.ai connectors share addresses between users and get a higher shared limit; if you still hit it, submit from your own machine with <code>crtest.submit</code>. Identical predictions sent again return the earlier result, re-scored if the gold has changed since.</li>
<li><b>Scores stay current.</b> If a gold label is corrected or a case is added, every stored submission is re-scored against the new gold.</li>
<li><b>What is published.</b> Your predictions, the name, description and contact you give, and the time. The backend keeps no record of who sent a submission; the web server keeps ordinary access logs. Keep secrets and personal data out of the description.</li>
<li><b>Retention and removal.</b> Nothing is deleted automatically. The community table holds up to 2,000 submissions; when it is full, new ones are refused until spam is removed. To have a row removed, open an issue on <a href="{REPO_URL}/issues">GitHub</a> with the submission id.</li>
</ul>
"""
    return layout("Submit results", body)


def load_table_results(results_dir: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(results_dir, "*.scored.json"))):
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
        r["_file"] = os.path.basename(path)
        r["_pred_file"] = os.path.basename(path).replace(".scored.json", ".json")
        out.append(r)
    out.sort(key=lambda r: (-(r["summary"].get("cell_accuracy") or 0), -(r["summary"].get("rows_exact") or 0)))
    return out


def build_tables_page(manifest: dict, results: list[dict], zip_name: str) -> str:
    hazards = manifest.get("hazards", {})
    naive = next((r for r in results if r["summary"].get("extractor") == "naive_text_tables"), None)
    board_rows = []
    for r in results:
        s = r["summary"]
        board_rows.append(
            f"<tr><td><b>{e(s.get('extractor'))}</b><br><span class='muted small'>{e(s.get('description') or '')}</span></td>"
            f"<td class='num'>{(s.get('cell_accuracy') or 0):.1%}</td><td class='num'>{(s.get('cell_recall') or 0):.1%}</td>"
            f"<td class='num'>{s.get('rows_exact')}/{s.get('rows_expected')}</td>"
            f"<td class='num'>{s.get('rows_extra')}</td><td class='num'>{s.get('rows_missing')}</td><td class='num'>{s.get('tables_exact')}/{s.get('cases')}</td>"
            f"<td class='small'><a href='results_tables/{e(r['_file'])}'>scored json</a> · <a href='results_tables/{e(r['_pred_file'])}'>predictions</a>"
            f"<br><span class='muted'>{e((s.get('run_at') or '')[:10])}</span></td></tr>")
    board = ("<table><thead><tr><th>Extractor</th><th class='num'>Cell score</th><th class='num'>Cells recovered</th><th class='num'>Rows exactly right</th>"
             "<th class='num'>Invented rows</th><th class='num'>Missing rows</th><th class='num'>Tables exact</th><th>Files</th></tr></thead><tbody>"
             + "".join(board_rows) + "</tbody></table>") if board_rows else "<p class='muted'>No results yet.</p>"
    cards = []
    for c in manifest["cases"]:
        cid = c["case_id"]
        pc = (naive or {}).get("per_case", {}).get(cid) if naive else None
        chips = "".join(f"<span class='chip' title='{e(hazards.get(h, ''))}'>{e(h)}</span>" for h in c["hazards"])
        naive_txt = (f"<div class='score'>text-dump extraction: cell score <b>{pc['cell_accuracy']:.0%}</b> "
                     f"({pc['cell_recall']:.0%} of cells recovered), <b>{pc['rows_exact']}/{pc['rows_expected']}</b> rows right, "
                     f"<b>{pc['rows_extra']}</b> invented rows</div>") if pc else ""
        pages = " ".join(f"<a href='tables/{cid}/pages/page-{i}.png'>page {i}</a>" for i in range(1, int(c["pages"]) + 1))
        cards.append(f"""<div class="card">
  <a class="thumb" href="tables/{cid}/document.pdf"><img src="tables/{cid}/pages/page-1.png" alt="First page of {cid}" loading="lazy"></a>
  <div class="body">
    <div class="id">{cid} · {c['pages']} page{'s' if c['pages'] != 1 else ''} · {c['rows']} rows</div>
    <h3>{e(c['title'])}</h3>
    <p class="small">{e(c['why'])}</p>
    <div class="chips">{chips}</div>
    {naive_txt}
    <p class="small"><a href="tables/{cid}/document.pdf">PDF</a> · <a href="tables/{cid}/expected.csv">expected.csv</a> ·
    <a href="tables/{cid}/wrong.csv">wrong.csv</a> · <a href="tables/{cid}/notes.md">notes</a> · <a href="tables/{cid}/text.txt">text dump</a> · {pages}</p>
  </div>
</div>""")
    hazard_rows = "".join(f"<tr><td><code>{e(k)}</code></td><td>{e(v)}</td><td class='num'>{sum(1 for c in manifest['cases'] if k in c['hazards'])}</td></tr>"
                          for k, v in hazards.items() if any(k in c["hazards"] for c in manifest["cases"]))
    body = f"""
<h1>Tables track</h1>
<p class="lede">Four synthetic documents built around the table failures raised in the pilot thread: tables without set
boundaries in statements, ID values such as dates printed once for a group of rows, and page boundaries, including a
row split by the page break. Each case is the PDF in, the expected CSV out, and the wrong extraction.</p>
<div class="btns">
  <a class="btn" href="downloads/{e(zip_name)}">Download the tables track (zip)</a>
  <a class="btn alt" href="{REPO_URL}/tree/main/tables">Files on GitHub</a>
</div>

<h2 id="tables-leaderboard">Leaderboard</h2>
<p class="muted small">Rows are aligned to the expected rows in document order, so a missing or invented row costs only itself.
<b>Cell score</b> = right cells / ((expected rows + invented rows) x columns): an invented row counts as a row of wrong cells, so
padding or hedging never helps. <b>Cells recovered</b> = right cells / expected cells. A blank expected cell must stay blank; text
must have the same words; money must be exactly one amount. LLM runs get the column list and the document text ("guided" adds the
same generic table rules for every case) and never see a case's own notes. Stock tools run with their documented defaults and no
repair.</p>
{board}

<p class="small"><b>Gold checked:</b> eight independent blind transcriptions, four from the page images only and four from the
text dump only, reproduce every <code>expected.csv</code> exactly. <b>This is a first version:</b> if your pipeline breaks on a layout
that is not here, describe it in the <a href="https://discord.com/channels/1558912731019608085/1565685928394231930">pilot thread</a> or
open an <a href="{REPO_URL}/issues">issue</a> and we will add a case for it.</p>

<h2 id="tables-cases">Cases</h2>
<div class="grid">
{"".join(cards)}
</div>

<h2>Hazards</h2>
<table><thead><tr><th>Hazard</th><th>What it is</th><th class="num">Cases</th></tr></thead><tbody>{hazard_rows}</tbody></table>

<h2>Score your own table extraction</h2>
<pre><code># one CSV per case named TB-00N.csv (columns as in expected.csv), or one JSON file
python -m crtest.score_tables --pred my_tables/
# the same text-dump baseline and LLM extractor the leaderboard uses
python -m crtest.extract_tables_naive
python -m crtest.extract_tables_llm --out results_tables/my_model.json --prompt guided</code></pre>
<p class="small">Every value is generated from one row list per case, so the PDF and <code>expected.csv</code> cannot disagree.
Dates are ISO, money is a plain number (negative for bracketed amounts), blank cells are empty.</p>
"""
    return layout("Tables track", body)


def make_tables_zip(tables_dir: str, results_dir: str, out_path: str) -> None:
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(tables_dir):
            for fn in files:
                p = os.path.join(root, fn)
                z.write(p, os.path.join("contractradar-tables", os.path.relpath(p, tables_dir)))
        if os.path.isdir(results_dir):
            for fn in os.listdir(results_dir):
                if fn.endswith(".json"):
                    z.write(os.path.join(results_dir, fn), os.path.join("contractradar-tables", "results", fn))
        z.writestr("contractradar-tables/README.txt", "Tables track of the ContractRadar test set: synthetic documents, expected CSVs and the wrong "
                   f"text-dump extraction.\nCode and docs: {REPO_URL}\nSynthetic documents and labels: CC0-1.0. Fictional organisations.\n")


def make_zip(cases_dir: str, results_dir: str, schema_path: str, out_path: str) -> None:
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(cases_dir):
            if os.path.basename(root) == "pages":
                continue
            for fn in files:
                p = os.path.join(root, fn)
                z.write(p, os.path.join("contractradar-testset", os.path.relpath(p, os.path.dirname(cases_dir))))
        for fn in os.listdir(results_dir):
            if fn.endswith(".json"):
                z.write(os.path.join(results_dir, fn), os.path.join("contractradar-testset", "results", fn))
        z.write(schema_path, os.path.join("contractradar-testset", "schema", "fields.json"))
        z.writestr("contractradar-testset/README.txt", "Synthetic test set for AI extraction of UK council contract documents.\n"
                   f"Code and docs: {REPO_URL}\nSynthetic documents and labels: CC0-1.0. Fictional authorities and suppliers.\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="cases")
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="site/dist")
    ap.add_argument("--tables", default="tables")
    ap.add_argument("--results-tables", default="results_tables")
    args = ap.parse_args(argv)
    with open(os.path.join(args.cases, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open(os.path.join(args.cases, "hazards.json"), encoding="utf-8") as fh:
        hazards = json.load(fh)
    schema_path = os.path.join(HERE, "..", "schema", "fields.json")
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    HIGH.update(f["id"] for f in schema["flags"] if f["severity"] == "high")
    results = load_results(args.results)

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(os.path.join(args.out, "static"))
    os.makedirs(os.path.join(args.out, "cases"))
    os.makedirs(os.path.join(args.out, "results"))
    os.makedirs(os.path.join(args.out, "downloads"))
    with open(os.path.join(args.out, "static", "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    with open(os.path.join(args.out, "static", "community.js"), "w", encoding="utf-8") as fh:
        fh.write(COMMUNITY_JS)
    for c in manifest["cases"]:
        src = os.path.join(args.cases, c["case_id"])
        shutil.copytree(src, os.path.join(args.out, "cases", c["case_id"]))
        with open(os.path.join(args.out, "cases", c["case_id"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(build_case_page(args.cases, c, results, schema, hazards))
    for fn in os.listdir(args.results):
        if fn.endswith(".json"):
            shutil.copy(os.path.join(args.results, fn), os.path.join(args.out, "results", fn))
    shutil.copy(os.path.join(args.cases, "manifest.json"), os.path.join(args.out, "manifest.json"))
    shutil.copy(schema_path, os.path.join(args.out, "schema.json"))
    version = manifest.get("generator_version", "0.1.0")
    zip_name = f"contractradar-testset-v{version}.zip"
    make_zip(args.cases, args.results, schema_path, os.path.join(args.out, "downloads", zip_name))
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(build_index(args.cases, manifest, results, schema, hazards, zip_name))
    with open(os.path.join(args.out, "schema.html"), "w", encoding="utf-8") as fh:
        fh.write(build_schema_page(schema))
    with open(os.path.join(args.out, "submit.html"), "w", encoding="utf-8") as fh:
        fh.write(build_submit_page(schema))
    with open(os.path.join(args.out, "leaderboard.json"), "w", encoding="utf-8") as fh:
        json.dump([r["summary"] for r in results], fh, indent=2)
    if os.path.isfile(os.path.join(args.tables, "manifest.json")):
        with open(os.path.join(args.tables, "manifest.json"), encoding="utf-8") as fh:
            tmanifest = json.load(fh)
        shutil.copytree(args.tables, os.path.join(args.out, "tables"))
        tresults = load_table_results(args.results_tables) if os.path.isdir(args.results_tables) else []
        if os.path.isdir(args.results_tables):
            shutil.copytree(args.results_tables, os.path.join(args.out, "results_tables"))
        tzip = f"contractradar-tables-v{tmanifest.get('generator_version', '0.1.0')}.zip"
        make_tables_zip(args.tables, args.results_tables, os.path.join(args.out, "downloads", tzip))
        with open(os.path.join(args.out, "tables.html"), "w", encoding="utf-8") as fh:
            fh.write(build_tables_page(tmanifest, tresults, tzip))
    with open(os.path.join(args.out, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\n")
    print(f"site written to {args.out}: {len(manifest['cases'])} cases, {len(results)} result sets")


if __name__ == "__main__":
    main()

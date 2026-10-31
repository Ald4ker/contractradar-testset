# Post for the ContractRadar pilot thread

Ash, Jmuz689 – here's the test set you asked for: synthetic PDF in, expected CSV out, plus the wrong extraction.

**https://contractradar.opentransformers.online** · code: https://github.com/Marxist-Leninist/contractradar-testset

What's there now (v0.1.0):

- 12 synthetic council documents (award notices, contract details notices, change notices, a scanned contract, a deed of variation) with every page marked as fictional. Each case has `document.pdf`, `gold.json` / `expected.csv`, `notes.md` saying why it's hard, and the flags a rule engine should raise (`PA23-s74-exceeds-below-threshold`, `PA23-s75-ccn-required-not-published`, `AUDIT-retrospective-extension` and so on).
- The three pain points named in the thread are in: a table crossing a page boundary with a repeated header and the footer between rows (CR-002, CR-007), a borderless table with grouped rows (CR-003), and grouped/stacked label-value layouts (CR-006). Plus scanned/no text layer, two-column interleaving, values in prose, £2.31m / £4 200 000 / words-and-figures money, five date formats, multi-lot with an unawarded lot, totals rows, trading-as names, and a negative control (CR-008) to catch over-eager rules.
- A deliberately naive `pdftotext` + regex baseline is scored on every case: 52% of fields, 2/12 cases fully right. That's the "wrong extraction" to beat.
- A scorer (`python -m crtest.score --pred results/yours.json`) that normalises dates, money and Ltd/Limited before comparing, and reports per-field, per-hazard and flag precision/recall. Drop a predictions file in `results/` and the leaderboard rebuilds.
- An LLM extractor for any OpenAI-compatible endpoint (text, OCR, vision) — Jmuz689, your Gemini vision pipeline would be a good second row.
- `crtest.collect` pulls real council notices from Find a Tender / Contracts Finder (OGL) with source URL and licence recorded per file, for the hand-labelled real set before 24 Nov.
- Reference rule checks (`crtest/pa2023.py`) with the 1 Jan 2026 thresholds, 10%/15% modification limits, 8-working-day standstill, 30-day notice timing, 3 KPIs over £5m, Sch 8 para 3 50% cap, s.77 publication — so expected flags are computed, not hand-typed. If a check is wrong, open an issue with the section.

Everything synthetic is CC0, code is MIT, no keys or personal data in the repo. Next: more variants of the page-boundary and grouped-row cases, and hand-labelled real notices.

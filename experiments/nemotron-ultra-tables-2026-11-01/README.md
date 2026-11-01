# Nemotron 3 Ultra: TB-001 and TB-003

Two independent runs of the public ContractRadar table extractor, recorded on 1 November 2026. Both tables passed the unchanged scorer. This contribution publishes those recorded runs. No inference calls or tests were repeated for publication, and the results have not been submitted to the public leaderboard.

| Case | Rows correct | Cells correct | Missing rows | Invented rows | Request time | Reported cost |
|---|---:|---:|---:|---:|---:|---:|
| TB-001 | 11/11 | 66/66 | 0 | 0 | 94.466 s | $0 |
| TB-003 | 12/12 | 60/60 | 0 | 0 | 99.817 s | $0 |

Each table has 100% cell accuracy and recall, with no cell errors. Cell correctness uses the existing scorer's normalisation, rather than literal character equality. These are two cases out of the four-table benchmark, not a complete benchmark run. The published guided-table result was already perfect; this is independent confirmation on two tables, not a new record.

## Method and settings

Source repository: https://github.com/Marxist-Leninist/contractradar-testset

Source commit: `9fc81b1dee25661e3ae2e6ef1e608d63ba9ab22f`.

| Setting | Both runs |
|---|---|
| Gateway | OpenRouter |
| Base URL | `https://openrouter.ai/api/v1` |
| Model requested | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| Provider returned | `Nvidia` |
| Extractor | `crtest.extract_tables_llm` |
| Prompt | Existing `guided` template, `TABLE_RULES_VERSION = 2` |
| Input | PDF text from `pdftotext -layout`; no OCR or images |
| Temperature | `0.0` |
| Output token limit | `4000` |
| Timeout | `180` seconds per HTTP attempt |
| Retry policy | Original client, up to five attempts |
| Attempts used | One per case; no retries |
| Other sampling parameters | Not supplied |
| Response finish reason | `stop` for both runs |
| Python / Poppler | Python 3.13.7 / Poppler 26.09.0 |
| Operating system | Windows 10, build 19045 |

The prompt template, generic rules and extraction method were unchanged between runs. The column definitions necessarily differ between a supplier statement and a milestone schedule, as does the source document text. The exact request bodies are included. No case-specific instructions were added.

| Case | Input tokens | Output tokens | Reasoning tokens within output | Total tokens | Extractor time | Total elapsed time |
|---|---:|---:|---:|---:|---:|---:|
| TB-001 | 1,199 | 3,277 | 1,576 | 4,476 | 95.037 s | 96.081 s |
| TB-003 | 1,817 | 2,402 | 1,047 | 4,219 | 99.907 s | 101.004 s |

Token counts and zero cost are taken from the full provider responses. Times are local measurements. Total elapsed time includes the driver's setup and packaging work during that run, but excludes later verification and publication preparation. Precise UTC timestamps and response identifiers are in each case's metadata.

## Evidence

The original inputs are already in the repository:

| Case | PDF | Expected CSV |
|---|---|---|
| TB-001 | [document.pdf](../../tables/TB-001/document.pdf) | [expected.csv](../../tables/TB-001/expected.csv) |
| TB-003 | [document.pdf](../../tables/TB-003/document.pdf) | [expected.csv](../../tables/TB-003/expected.csv) |

Each case folder here contains the unmodified extractor prediction, exported actual CSV, full model reply, full provider response, request body, token usage, scoring results, catalogue entry, metadata and original capture driver. Each case folder also contains byte-identical copies of its original PDF and expected CSV beside the outputs, so the recorded experiment can be downloaded together. The original benchmark files remain unchanged.

`score.json` gives the result for the named case. `score-all-tables.json` preserves the original scorer output. Its headline is 25% for each single-case submission because it also counts three unsubmitted tables. Use the per-case result when assessing these runs. No score has been claimed for TB-002 or TB-004.

## Validity checks

The model received only freshly extracted PDF text and generic column names, types and printed headers. It did not receive expected CSV data, `wrong.csv`, notes, hazards, row rules, generator answers or scorer verdicts. The saved requests can be reconstructed from just those permitted inputs. Knowing the public benchmark's gold prevents a claim of fully blinded evaluation, but the captured requests contain no answer-key material.

After each response, its rows were exported in their original order using Python's CSV writer. Only the header of the expected CSV was used to select column order. Null cells became blank CSV cells. The exported values match the response rows, and the CSVs produce the same scores as the JSON predictions. No output was manually corrected.

The TB-001 opening balance was retained, empty debit and credit cells stayed empty, wrapped details stayed in their cells and the bracketed balance was interpreted as negative. TB-003's milestone 5 trigger was joined across the page break. Neither run emitted headers, footers or totals as rows.

The benchmark assets, extractors, prompts, schema, legal checks and scorers were not modified. The local checkout has an earlier test portability change replacing a fixed `/tmp` path with pytest's temporary folder; that change does not affect extraction or scoring and is not included in this proposed publication.

One limitation of the original extractor is that it keeps at most 6,000 characters in its `raw` field. Full replies and provider responses are therefore retained separately. Poppler reports syntax warnings for the original TB-001 PDF while successfully extracting and rendering it. The input was retained unchanged, and the saved text matches a fresh extraction.

These are single runs on public synthetic documents. Temperature zero does not guarantee identical future output, and a free model alias may change backend or availability. This is a test of the public harness, not a test of the Chronara application. No conclusions about all four tables, the 12 contract cases or unseen documents follow from these two results.

## Reproduction

Use the stated source commit and Python 3.13.7. Create a virtual environment and install the versions in `requirements-resolved.txt`. Install Poppler 26.09.0 and put its command-line tools on `PATH`. OCR tools are not needed. On Windows, set `PYTHONUTF8=1` before starting Python.

Set the key securely in `LLM_API_KEY` in your process environment. Do not put its value in documentation, command history or tracked files. Recheck that the exact `:free` route still has zero prices before making a call. Do not add paid fallbacks or plugins.

From the repository root, these PowerShell commands repeat the same extraction settings. Supply the key separately before running them. Use fresh filenames, because the extractor can load and overwrite existing results.

```powershell
$env:PYTHONUTF8 = '1'
$env:LLM_BASE_URL = 'https://openrouter.ai/api/v1'
$env:LLM_MODEL = 'nvidia/nemotron-3-ultra-550b-a55b:free'
$env:LLM_MAX_TOKENS = '4000'
$env:LLM_TIMEOUT = '180'
New-Item -ItemType Directory -Force reruns | Out-Null
python -m crtest.extract_tables_llm --only TB-001 --prompt guided --out reruns/TB-001.json
python -m crtest.score_tables --pred reruns/TB-001.json --out reruns/TB-001.scored.json
python -m crtest.extract_tables_llm --only TB-003 --prompt guided --out reruns/TB-003.json
python -m crtest.score_tables --pred reruns/TB-003.json --out reruns/TB-003.scored.json
```

Export a real prediction to CSV without altering it:

```python
import csv
import json
from pathlib import Path

case_id = 'TB-001'  # Change to TB-003 for the other case.
prediction = json.loads(Path(f'reruns/{case_id}.json').read_text(encoding='utf-8'))
case = prediction['cases'][case_id]
assert case['error'] is None, case['error']
with Path(f'tables/{case_id}/expected.csv').open(encoding='utf-8', newline='') as source:
    columns = next(csv.reader(source))
with Path(f'reruns/{case_id}.csv').open('w', encoding='utf-8', newline='') as target:
    writer = csv.DictWriter(target, fieldnames=columns)
    writer.writeheader()
    writer.writerows(case['rows'])
```

The original `capture.py` in each case folder is included for audit. It wrapped the HTTP transport to record the request body, full response and timings, then invoked the unchanged extractor. It did not alter generation settings or source material. These historical drivers expect a workspace containing `work/contractradar-testset`, `work/poppler-26.09.0-0/poppler-26.09.0/Library/bin` and an ignored key file at `work/contractradar-testset/.env.local`. To reuse a driver with that layout, copy it to `work/run_tb001.py` or `work/run_tb003.py` and run it with UTF-8 enabled. It will create a new timestamped folder under `outputs`. The normal module commands above do not need this layout, but do not retain the provider's full usage response.

Verify the supplied results without a key or network access:

```powershell
python experiments/nemotron-ultra-tables-2026-11-01/verify.py
python -m pytest -q -rs tests
```

The verifier reconstructs the source-only requests, compares model parameters, checks hashes and responses, verifies the CSV export and reruns the unchanged scorer on both JSON and CSV. Verification was completed locally before publication. The existing repository test suite previously passed with 176 tests and four optional-dependency skips after the separate test portability fix. An unmodified Windows checkout may still encounter the original fixed `/tmp` test-path problem; it does not affect the evidence verifier.

No keys, authorisation headers or account quota records are included. Synthetic inputs are CC0 and code is MIT under the repository's existing licences. This contribution contains the recorded results only; it does not introduce a new extraction run or a leaderboard submission.

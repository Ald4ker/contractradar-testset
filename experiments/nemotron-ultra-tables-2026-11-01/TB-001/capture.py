"""Instrument the unchanged repository extractor; never log request credentials."""
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
repo = root / 'work/contractradar-testset'
sys.path.insert(0, str(repo))
model = 'nvidia/nemotron-3-ultra-550b-a55b:free'
base = 'https://openrouter.ai/api/v1'
secret_file = repo / '.env.local'
values = {}
for line in secret_file.read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k, v = line.split('=', 1)
        values[k.strip()] = v.strip().strip('\"').strip("'")
key = values.get('LLM_API_KEY', '')
if not key or key == 'PASTE_YOUR_KEY_HERE':
    sys.exit('Key not configured in the local file. No API request made.')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-c', f'safe.directory={repo.as_posix()}', *args], cwd=repo).decode().strip()

def save(path, obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if key in text:
        raise RuntimeError('Credential detected in output; refusing to save.')
    path.write_text(text, encoding='utf-8')

start = datetime.now(timezone.utc)
out = root / 'outputs' / ('TB-001-first-run-' + start.strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(exist_ok=False)
manifest = {'status': 'preflight', 'started_at_utc': start.isoformat(), 'repository': 'https://github.com/Marxist-Leninist/contractradar-testset',
            'commit': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'), 'model': model, 'base_url': base,
            'gateway': 'OpenRouter', 'mode': 'text, guided v2', 'temperature': 0, 'max_tokens': 4000, 'timeout_seconds': 180,
            'max_attempts': 5, 'attempts': [], 'maximum_authorised_cost_usd': 0, 'python': sys.version, 'platform': platform.platform(),
            'case': 'TB-001', 'gold_rows': 11, 'contract_extraction': 'NOT RUN', 'benchmark_and_scorer_modified': False}
save(out / 'manifest.json', manifest)
original_urlopen = urllib.request.urlopen
try:
    with original_urlopen(base + '/models', timeout=30) as response:
        catalogue = json.load(response)
    selected = next(m for m in catalogue['data'] if m['id'] == model)
    assert model.endswith(':free') and float(selected['pricing']['prompt']) == 0 and float(selected['pricing']['completion']) == 0
    for fee in ('request', 'image', 'web_search', 'internal_reasoning'):
        assert float(selected['pricing'].get(fee, 0) or 0) == 0, f'Non-zero {fee} price'
    save(out / 'model-catalogue-entry.json', selected)
    req = urllib.request.Request(base + '/key', headers={'Authorization': 'Bearer ' + key})
    with original_urlopen(req, timeout=30) as response:
        account = json.load(response)['data']
    quota = account.get('free_model_daily_requests')
    save(out / 'account-quota.json', {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'is_free_tier': account.get('is_free_tier'), 'free_model_daily_requests': quota})
    if quota and quota.get('remaining') is not None and quota['remaining'] < 1:
        raise RuntimeError('Free daily quota exhausted; no inference attempted.')
    os.environ.update(LLM_BASE_URL=base, LLM_MODEL=model, LLM_API_KEY=key, LLM_MAX_TOKENS='4000', LLM_TIMEOUT='180')
    os.environ['PATH'] = str(root / 'work/poppler-26.09.0-0/poppler-26.09.0/Library/bin') + os.pathsep + os.environ['PATH']
    os.chdir(repo)
    from crtest import extract_tables_llm, score_tables
    protected = ['crtest/score_tables.py', 'crtest/score.py', 'crtest/extract_tables_llm.py', 'crtest/extract_llm.py', 'crtest/pa2023.py']
    for p in protected:
        assert not git('diff', 'HEAD', '--', p), p
    assert not git('diff', 'HEAD', '--', 'cases', 'tables', 'schema', 'results', 'results_tables')
    manifest['protected_sha256'] = {p: sha(repo / p) for p in protected}
    manifest['driver_sha256'] = sha(__file__)

    def capture(request, *args, **kwargs):
        if isinstance(request, urllib.request.Request) and request.full_url == base + '/chat/completions':
            body = json.loads(request.data)
            assert body['model'] == model and 'models' not in body and 'plugins' not in body
            save(out / 'request.json', body)  # Request body only: no Authorization header.
            attempt = {'number': len(manifest['attempts']) + 1, 'started_at_utc': datetime.now(timezone.utc).isoformat()}
            manifest['attempts'].append(attempt)
            save(out / 'manifest.json', manifest)
            t0 = time.monotonic()
            try:
                with original_urlopen(request, *args, **kwargs) as response:
                    raw = response.read()
                    status = response.status
                parsed = json.loads(raw)
                assert key.encode() not in raw
                (out / f'provider-response-{attempt["number"]}.json').write_bytes(raw)
                attempt.update(http_status=status, seconds=round(time.monotonic() - t0, 3), provider=parsed.get('provider'), response_id=parsed.get('id'), finish_reason=parsed.get('choices', [{}])[0].get('finish_reason'), usage=parsed.get('usage'))
                save(out / 'manifest.json', manifest)
                return io.BytesIO(raw)
            except urllib.error.HTTPError as error:
                raw = error.read()
                if key.encode() not in raw:
                    (out / f'provider-error-{attempt["number"]}.json').write_bytes(raw)
                attempt.update(http_status=error.code, seconds=round(time.monotonic() - t0, 3))
                save(out / 'manifest.json', manifest)
                raise
            except Exception as error:
                attempt.update(error_type=type(error).__name__, seconds=round(time.monotonic() - t0, 3))
                save(out / 'manifest.json', manifest)
                raise
        return original_urlopen(request, *args, **kwargs)

    urllib.request.urlopen = capture
    print('Verified zero token/extra fees; key accepted. Running TB-001 with ' + model, flush=True)
    t0 = time.monotonic()
    extract_tables_llm.main(['--only', 'TB-001', '--prompt', 'guided', '--out', str(out / 'actual_output.json')])
    manifest['extraction_seconds'] = round(time.monotonic() - t0, 3)
    prediction = json.loads((out / 'actual_output.json').read_text(encoding='utf-8'))
    case = prediction['cases']['TB-001']
    scored = score_tables.score(str(repo / 'tables'), str(out / 'actual_output.json'))
    save(out / 'score-all-tables.json', scored)
    save(out / 'score-TB-001.json', scored['per_case']['TB-001'])
    with (repo / 'tables/TB-001/expected.csv').open(encoding='utf-8', newline='') as stream:
        header = next(csv.reader(stream))
    assert isinstance(case['rows'], list) and all(isinstance(r, dict) for r in case['rows'])
    with (out / 'actual_output.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=header, extrasaction='raise')
        writer.writeheader()
        writer.writerows(case['rows'])
    for name in ['document.pdf', 'expected.csv']:
        shutil.copyfile(repo / 'tables/TB-001' / name, out / name)
        assert sha(out / name) == sha(repo / 'tables/TB-001' / name)
    manifest['status'] = 'completed' if not case['error'] else 'extraction_failed'
    manifest['extractor_error'] = case['error']
    manifest['tb001_score'] = scored['per_case']['TB-001']
except Exception as error:
    manifest['status'] = 'blocked_or_failed'
    manifest['error'] = str(error).replace(key, '[REDACTED]')
finally:
    urllib.request.urlopen = original_urlopen
    manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['total_wall_seconds'] = round((datetime.now(timezone.utc) - start).total_seconds(), 3)
    manifest['artifact_sha256'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'}
    save(out / 'manifest.json', manifest)
    print(json.dumps({'status': manifest['status'], 'output': str(out), 'attempts': len(manifest['attempts']), 'error': manifest.get('error'), 'table_score': manifest.get('tb001_score')}), flush=True)

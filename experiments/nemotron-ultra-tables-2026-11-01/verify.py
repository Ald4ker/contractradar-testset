"""Check saved evidence against the original source and scorer. No API calls."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from crtest import extract_tables_llm, score_tables
from crtest.extract_llm import parse_json


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(case_id):
    folder = HERE / case_id
    meta = load(folder / 'metadata.json')
    request = load(folder / 'request.json')
    response = load(folder / 'provider-response.json')
    prediction = load(folder / 'actual_output.json')
    spec = score_tables.load_spec(str(ROOT / 'tables'), case_id)
    for path, digest in meta['sha256'].items():
        assert sha(HERE / path) == digest, path
    for path, digest in meta['source_sha256'].items():
        raw = (ROOT / path).read_bytes()
        normalised = hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()
        assert sha(ROOT / path) == digest or normalised == meta['source_text_sha256_lf'].get(path), path
    for path, digest in meta['protected_code_sha256'].items():
        # Windows checkouts may have CRLF; the metadata records LF-normalised code.
        raw = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(raw).hexdigest() == digest, path
    assert request['model'] == 'nvidia/nemotron-3-ultra-550b-a55b:free'
    assert request['temperature'] == 0 and request['max_tokens'] == 4000
    assert set(request) == {'model', 'messages', 'temperature', 'max_tokens'}
    columns = {'columns': [{k: c[k] for k in ('name', 'type', 'printed_header')} for c in spec['columns']]}
    text = subprocess.check_output(['pdftotext', '-layout', str(ROOT / 'tables' / case_id / 'document.pdf'), '-']).decode('utf-8').replace('\r\n', '\n')
    expected_messages = [
        {'role': 'system', 'content': extract_tables_llm.build_prompt(columns, 'guided')},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Document text (pdftotext -layout):\n\n' + text},
            {'type': 'text', 'text': 'Return the JSON object now.'},
        ]},
    ]
    assert request['messages'] == expected_messages, 'Request differs from source-only prompt'
    case = prediction['cases'][case_id]
    assert not case['error'] and set(prediction['cases']) == {case_id}
    assert response['choices'][0]['finish_reason'] == 'stop'
    assert response['choices'][0]['message']['content'] == (folder / 'actual_reply.txt').read_text(encoding='utf-8')
    assert parse_json(response['choices'][0]['message']['content'])['rows'] == case['rows']
    with (folder / 'actual_output.csv').open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames
        exported = list(reader)
    with (ROOT / 'tables' / case_id / 'expected.csv').open(encoding='utf-8', newline='') as stream:
        assert header == next(csv.reader(stream))
    assert exported == [{k: '' if r.get(k) is None else str(r.get(k)) for k in header} for r in case['rows']]
    scored = score_tables.score(str(ROOT / 'tables'), str(folder / 'actual_output.json'))
    assert scored == load(folder / 'score-all-tables.json')
    assert scored['per_case'][case_id] == load(folder / 'score.json')
    csv_rows, _ = score_tables.rows_from_csv(score_tables.read_csv_text((folder / 'actual_output.csv').read_text(encoding='utf-8')), spec)
    gold = score_tables.load_gold(str(ROOT / 'tables'), case_id, spec)
    from_csv = score_tables.score_case(spec, gold, csv_rows)
    from_json = dict(scored['per_case'][case_id])
    from_json.pop('column_mapping')
    assert from_csv == from_json
    assert meta['usage'] == response['usage'] and response['usage']['cost'] == 0
    return request, scored['per_case'][case_id]


if __name__ == '__main__':
    a, s1 = verify('TB-001')
    b, s3 = verify('TB-003')
    assert {k: v for k, v in a.items() if k != 'messages'} == {k: v for k, v in b.items() if k != 'messages'}
    print('Evidence valid: source-only requests, matching settings, original responses, unedited CSVs and unchanged scoring.')
    for cid, score in [('TB-001', s1), ('TB-003', s3)]:
        print(f"{cid}: {score['rows_exact']}/{score['rows_expected']} rows; cells {score['cell_accuracy']:.1%}; pass={score['table_exact']}")

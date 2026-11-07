"""Synthetic receipt validation only; never writes owner receipts."""
import copy
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('review_server', root / 'serve.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data, digest = module.snapshot()
base = {'snapshot_sha256': digest, 'selected_ids': ['TEST-GATE'], 'decisions': {
    'TEST-GATE': {'action': 'approve', 'choice': '', 'comment': ''}}}
# Find choices by identity, not position.
base['decisions']['TEST-GATE']['choice'] = next(x for x in data['items'] if x['id'] == 'TEST-GATE')['choices'][0]
checks = []

def reject(name, payload):
    try:
        module.validate(payload, data, digest)
    except ValueError:
        checks.append(name)
    else:
        raise AssertionError(name)

def changed(**updates):
    p = copy.deepcopy(base)
    p.update(updates)
    return p

reject('empty selection', changed(selected_ids=[], decisions={}))
reject('unknown id', changed(selected_ids=['UNKNOWN']))
reject('duplicate id', changed(selected_ids=['TEST-GATE', 'TEST-GATE']))
reject('stale snapshot', changed(snapshot_sha256='0' * 64))
reject('extra unselected decision', changed(decisions={**base['decisions'], 'F-PLAN': {'action': 'confirm_existing'}}))
reject('missing action', changed(decisions={'TEST-GATE': {}}))
reject('missing amend comment', changed(decisions={'TEST-GATE': {'action': 'amend', 'comment': ''}}))
reject('invalid choice', changed(decisions={'TEST-GATE': {'action': 'approve', 'choice': 'forged'}}))
reject('pending cannot confirm existing', changed(decisions={'TEST-GATE': {'action': 'confirm_existing'}}))
ids, decisions = module.validate(base, data, digest)
assert ids == ['TEST-GATE'] and list(decisions) == ids
checks.append('valid selected-only approval')
hold = changed(selected_ids=['F-UI'], decisions={'F-UI': {'action': 'keep_deferred', 'comment': ''}})
assert module.validate(hold, data, digest)[0] == ['F-UI']
checks.append('hold without extra radio')
amend = changed(selected_ids=['F-PLAN'], decisions={'F-PLAN': {'action': 'amend', 'comment': 'Synthetic QA: revised requirement'}})
assert module.validate(amend, data, digest)[1]['F-PLAN']['comment'].startswith('Synthetic QA')
checks.append('amend approved item with verbatim comment')
assert len(data['items']) == 25 and len({x['id'] for x in data['items']}) == 25
assert sum(x['group'] == 'Chức năng' for x in data['items']) == 11
checks.append('25 unique items and 11 functions')
assert not (root / 'receipts').exists() or not list((root / 'receipts').glob('*.json'))
checks.append('no owner receipts created by QA')
result = {'kind': 'SYNTHETIC_VALIDATION_QA_NOT_OWNER_APPROVAL', 'passed': len(checks), 'checks': checks,
          'snapshot_sha256': digest, 'browser': 'Page rendered; no approval controls selected or submitted by QA.'}
(root / 'qa-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(checks), 'owner_receipts_created': 0}))

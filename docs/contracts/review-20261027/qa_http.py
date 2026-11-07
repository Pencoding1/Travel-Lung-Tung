"""Isolated synthetic HTTP QA. Output is never an owner approval."""
import http.client
import importlib.util
import json
import threading
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('server', root / 'serve.py')
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)
server = server_module.ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
server.receipt_dir = root / 'qa-synthetic-receipts'
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
port = server.server_port
origin = f'http://127.0.0.1:{port}'
checks = []

def request(method, path, payload=None, headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    all_headers = {'Content-Type': 'application/json', 'Origin': origin}
    all_headers.update(headers or {})
    body = json.dumps(payload) if payload is not None else None
    connection.request(method, path, body=body, headers=all_headers)
    result = connection.getresponse()
    status, raw = result.status, result.read()
    connection.close()
    return status, json.loads(raw)

try:
    status, value = request('GET', '/snapshot')
    assert status == 200
    checks.append('GET snapshot')
    digest = value['snapshot_sha256']
    payload = {'snapshot_sha256': digest, 'selected_ids': ['F-UI'], 'decisions': {
        'F-UI': {'action': 'keep_deferred', 'comment': 'SYNTHETIC QA ONLY — NOT OWNER APPROVAL'}}}
    for method, path, body, headers, expected in [
        ('POST', '/submit', payload, {'Origin': 'http://evil.invalid'}, 403),
        ('POST', '/submit', payload, {'Host': 'evil.invalid'}, 403),
        ('POST', '/submit', payload, {'Content-Type': 'text/plain'}, 415),
        ('GET', '/../content.json', None, {}, 404),
        ('POST', '/submit', {**payload, 'snapshot_sha256': 'stale'}, {}, 422),
        ('POST', '/submit', {**payload, 'selected_ids': []}, {}, 422),
    ]:
        assert request(method, path, body, headers)[0] == expected
        checks.append(f'{method} {path}: expected {expected}')
    results = [request('POST', '/submit', payload) for _ in range(2)]
    assert all(status == 201 for status, _ in results)
    assert results[0][1]['receipt_id'] != results[1][1]['receipt_id']
    for _, receipt_result in results:
        receipt = json.loads(Path(receipt_result['path']).read_text(encoding='utf-8'))
        assert receipt['selected_ids'] == ['F-UI']
        assert list(receipt['decisions']) == ['F-UI']
        assert receipt['snapshot_sha256'] == digest and receipt['snapshot'] == value['snapshot']
        assert receipt['application_status'] == 'NOT_APPLIED'
    checks.append('two unique synthetic receipts bound to server snapshot, selected-only, not applied')
    result = {'kind': 'SYNTHETIC_HTTP_QA_NOT_OWNER_APPROVAL', 'passed': len(checks), 'checks': checks}
    (root / 'qa-http-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'passed': len(checks), 'production_receipts_created': 0, 'synthetic_receipts': 2}))
finally:
    server.shutdown()
    server.server_close()

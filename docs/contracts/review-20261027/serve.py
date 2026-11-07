"""Local behavior review; does not apply receipts to contracts or product code."""
import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ACTIONS = {'confirm_existing', 'approve', 'amend', 'keep_deferred'}

def snapshot():
    raw = (ROOT / 'content.json').read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def validate(payload, data, digest):
    if not isinstance(payload, dict) or payload.get('snapshot_sha256') != digest:
        raise ValueError('Snapshot đã đổi hoặc không hợp lệ. Tải lại form; không tự chuyển lựa chọn cũ.')
    ids = payload.get('selected_ids')
    decisions = payload.get('decisions')
    index = {x['id']: x for x in data['items']}
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids):
        raise ValueError('Chọn ít nhất một mục để gửi.')
    if len(ids) != len(set(ids)) or any(x not in index for x in ids):
        raise ValueError('ID trùng hoặc không thuộc snapshot.')
    if not isinstance(decisions, dict) or set(decisions) != set(ids):
        raise ValueError('Chỉ gửi quyết định của đúng các mục đã chọn.')
    cleaned = {}
    for key in ids:
        decision = decisions[key]
        if not isinstance(decision, dict):
            raise ValueError('Quyết định sai định dạng.')
        action = decision.get('action')
        comment = decision.get('comment', '')
        choice = decision.get('choice', '')
        if action not in ACTIONS or not isinstance(comment, str) or len(comment) > 12000:
            raise ValueError('Hành động hoặc ghi chú không hợp lệ.')
        if not isinstance(choice, str):
            raise ValueError('Lựa chọn không hợp lệ.')
        item = index[key]
        if action == 'amend' and not comment.strip():
            raise ValueError('Yêu cầu sửa phải có nội dung: ' + key)
        if action == 'approve' and (item['status'] != 'PENDING' or choice not in item['choices']):
            raise ValueError('Duyệt mục mở cần đúng một phương án: ' + key)
        if action == 'confirm_existing' and item['status'] != 'APPROVED':
            raise ValueError('Mục này chưa có phê duyệt để xác nhận lại: ' + key)
        if action != 'approve' and choice:
            raise ValueError('Phương án chỉ đi cùng hành động duyệt mục mở.')
        cleaned[key] = dict(action=action, choice=choice, comment=comment)
    return ids, cleaned

class Handler(BaseHTTPRequestHandler):
    def send(self, status, value, mime='application/json; charset=utf-8'):
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(raw)

    def trusted(self):
        host = '127.0.0.1:' + str(self.server.server_port)
        return self.headers.get('Host') == host and self.headers.get('Origin', 'http://' + host) == 'http://' + host

    def do_GET(self):
        if not self.trusted():
            return self.send(403, {'error': 'Host/Origin không hợp lệ.'})
        if self.path == '/':
            return self.send(200, (ROOT / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/snapshot':
            data, digest = snapshot()
            return self.send(200, {'snapshot': data, 'snapshot_sha256': digest})
        return self.send(404, {'error': 'Không có route này.'})

    def do_POST(self):
        if not self.trusted():
            return self.send(403, {'error': 'Host/Origin không hợp lệ.'})
        if self.path != '/submit':
            return self.send(404, {'error': 'Không có route này.'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(415, {'error': 'Cần application/json.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 262144:
                return self.send(413, {'error': 'Payload rỗng hoặc quá lớn.'})
            payload = json.loads(self.rfile.read(size))
            data, digest = snapshot()
            ids, decisions = validate(payload, data, digest)
        except (ValueError, TypeError, UnicodeError) as exc:
            return self.send(422, {'error': str(exc) if not isinstance(exc, json.JSONDecodeError) else 'JSON không hợp lệ.'})
        timestamp = datetime.now(timezone.utc).isoformat()
        receipt_id = 'receipt-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex
        receipt = dict(schema_version=1, receipt_id=receipt_id, created_at=timestamp,
                       review_id=data['id'], snapshot_sha256=digest, selected_ids=ids,
                       decisions=decisions, snapshot=data, application_status='NOT_APPLIED')
        target = self.server.receipt_dir / (receipt_id + '.json')
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
        except OSError:
            return self.send(500, {'error': 'Chưa lưu được biên nhận; không được coi là đã gửi thành công.'})
        self.send(201, dict(receipt_id=receipt_id, path=str(target), selected_ids=ids,
                            application_status='NOT_APPLIED'))

    def log_message(self, format, *args):
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=19127)
    parser.add_argument('--receipt-dir', type=Path, default=ROOT / 'receipts')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.receipt_dir = args.receipt_dir.resolve()
    print('Review form: http://127.0.0.1:' + str(server.server_port) + '/', flush=True)
    server.serve_forever()

if __name__ == '__main__':
    main()

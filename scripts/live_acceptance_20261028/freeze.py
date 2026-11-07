"""Freeze only explicitly allowlisted public contract/source files; no secrets."""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'docs/contracts/frozen/TVLT-BEHAVIOR-20261028-v1'
SOURCES = [
 'docs/contracts/FREEZE_2026-10-28.md',
 'docs/contracts/F-CHAT_MVP_CONTRACT.md',
 'docs/contracts/F-BOOKING_MVP_CONTRACT.md',
 'docs/contracts/APPROVAL_REVIEW_2026-10-27.md',
 'docs/contracts/F-CHAT_MVP_TEST_ARCHITECTURE.md',
 'docs/contracts/F-CHAT_MVP_TEST_PLAN.md',
 'docs/contracts/review-20261027/content.json',
 'docs/contracts/review-20261027/receipts/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb.json',
 'docs/contracts/review-20261027/applications/receipt-20261028T095530Z-da8144773f584090ab604bfc46005cfb/application.json',
]
CODE = [
 'ai_service/main.py', 'ai_service/domains/payloads.py', 'ai_service/domains/jev_intent.py',
 'ai_service/domains/chat_agent.py', 'ai_service/domains/source_gate.py', 'ai_service/domains/grounding.py',
 'ai_service/domains/planning_adapter.py', 'ai_service/domains/planning/scheduler.py',
 'ai_service/domains/planning/validator.py', 'ai_service/domains/providers/opencode_cli.py',
 'ai_service/domains/providers/config.py', 'ai_service/domains/memory.py',
 'ai_service/static/travel.html', 'POI_service/app/api/mcp/tools.py',
 'backend_service/app/main.py', 'backend_service/app/api/rest/v1/endpoint_itinerary.py',
 'POI_service/app/api/rest/v1/endpoint_ingestion.py', 'POI_service/app/main.py',
]

def sha(p):
 return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
 manifest = TARGET / 'manifest.json'
 if manifest.exists():
  old = json.loads(manifest.read_text(encoding='utf-8'))
  for row in old['files']:
   assert sha(TARGET / row['snapshot_path']) == row['sha256']
  print('Frozen snapshot exists; bytes verified; not overwritten.')
  return
 TARGET.mkdir(parents=True, exist_ok=False)
 rows = []
 for rel in SOURCES:
  source = ROOT / rel
  dest = TARGET / 'sources' / rel
  dest.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(source, dest)
  rows.append({'source': rel, 'snapshot_path': dest.relative_to(TARGET).as_posix(), 'sha256': sha(dest)})
 result = {'id': TARGET.name, 'status': 'FROZEN_APPROVED_BEHAVIOR_NOT_IMPLEMENTATION_PASS',
  'created_at': datetime.now(timezone.utc).isoformat(), 'ui_design': 'HOLD',
  'contract_sources': 'explicit allowlist; excludes secrets, private incident, unrelated history',
  'git_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'files': rows, 'code_baseline': [{'path': x, 'sha256': sha(ROOT / x)} for x in CODE],
  'commit_or_tag_created': False, 'real_booking_authorized': False,
  'live_acceptance_authorized': True, 'test_outcome': 'NOT_RUN'}
 manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'frozen_files': len(rows), 'public_code_pins': len(CODE), 'manifest': str(manifest)}))

if __name__ == '__main__':
 main()

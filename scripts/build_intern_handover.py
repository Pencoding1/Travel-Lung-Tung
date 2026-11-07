"""Build/validate a docs-only handover from explicit non-secret inputs.

No network, environment enumeration, credential loading, service or model calls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HAND=ROOT/'docs/handover/2026-10-29'
SKILL=ROOT/'skills/before'
DOCS=[
 'docs/contracts/APPROVAL_REVIEW_2026-10-27.md',
 'docs/contracts/FREEZE_2026-10-28.md',
 'docs/contracts/CHAT_INTENT_AMENDMENT_2026-10-28.md',
 'docs/contracts/F-CHAT_MVP_CONTRACT.md',
 'docs/contracts/F-BOOKING_MVP_CONTRACT.md',
 'docs/contracts/F-CHAT_MVP_TEST_ARCHITECTURE.md',
 'docs/contracts/F-CHAT_MVP_TEST_PLAN.md',
 'docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/manifest.json',
 'docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/CHAT_INTENT_AMENDMENT_2026-10-28.md',
 'docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/F-CHAT_MVP_CONTRACT.md',
 'docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/chat_v1_1_cases.json',
 'tests/behavior_specs/chat_v1_1_cases.json',
 'docs/project/FOUR_PHASE_PLAN.md',
 'docs/project/PHASE2_SCOPE_FOR_APPROVAL_VI.md',
 'docs/project/EXECUTOR_POLICY.md',
 'docs/data/PRIMARY_POI_AUDIT.md',
 'docs/data/PRIMARY_GRAPH_READY_SNAPSHOT.md',
 'docs/data/PRIMARY_IMPORT_CONTRACT.md',
 'docs/research/agent-memory-p2/RECOMMENDATION_VI.md',
 'docs/research/agent-memory-p2/P2_ACCEPTANCE.md',
 'docs/research/agent-memory-p2/SOURCES.md',
 'docs/research/social-poi/SOURCE_MATRIX.md',
 'docs/research/social-poi/PIPELINE_VI.md',
 'docs/research/social-poi/QA_PLAN.md',
 'docs/reports/live-acceptance-2026-10-28/COMPOSE_V11_REPORT.md',
 'docs/project/checkpoints/2026-10-28-typesafe-jev-aibox-restored.md',
]
CODE=[
 'ai_service/main.py','ai_service/domains/jev_intent.py','ai_service/domains/chat_agent.py',
 'ai_service/domains/source_gate.py','ai_service/domains/planning_adapter.py',
 'ai_service/domains/planning/scheduler.py','ai_service/domains/planning/validator.py',
 'ai_service/domains/memory.py','ai_service/static/travel.html',
 'POI_service/app/api/mcp/tools.py','POI_service/app/core/services/ingestion.py',
 'backend_service/app/api/rest/v1/endpoint_itinerary.py','scripts/aibox_adapter.py',
 'scripts/run_legacy.py','scripts/legacy_demo_import.py','docker-compose.yaml',
 'graphhopper/data/config.yml',
]
DENIED={'legacy','.git','.venv','node_modules','secrets','credentials','auth','ai_chat_mvp_hidden'}
AUTHORED=[
 'README.md','01_OWNER_BRIEF.md','02_ARCHITECTURE_AND_CODEMAP.md',
 '03_CONTRACTS_AND_DECISIONS.md','04_RUNTIME_RUNBOOK.md','05_OPEN_ISSUES.md',
 '06_ROADMAP_AND_POST_MVP.md','07_TESTING_AND_ACCEPTANCE.md',
 '08_DATA_AND_RESEARCH.md','09_BEFORE_WORKFLOW.md','10_INTERACTIVE_DOCS_AGENT_BRIEF.md',
 '11_AGENT_BOOTSTRAP.md','12_GITHUB_PACKAGE.md','13_FIRST_SPRINT.md',
 '14_ACCEPTANCE_AND_SIGNOFF.md','knowledge-map.json',
 'evidence/source-pins.json','evidence/protected-baseline.json',
]

def sha(raw):return hashlib.sha256(raw).hexdigest()
def write_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def allowed(path):
 parts=set(path.parts)
 return not (parts&DENIED or path.name.startswith('.env') or path.suffix.lower() in {'.log','.db','.sqlite','.pbf','.pem','.key','.exe'} or path.name=='KEY_EXPOSURE_EXCERPT_PRIVATE.txt')
def checked_read(rel):
 path=ROOT/rel
 if not allowed(Path(rel)) or '..' in Path(rel).parts or not path.resolve().is_relative_to(ROOT.resolve()):
  raise ValueError('forbidden source path: '+rel)
 for component in [path,*path.parents]:
  if component==ROOT:break
  if component.is_symlink():raise ValueError('symlink source path: '+rel)
 return path.read_bytes()

def evidence():
 rows=[];pending=[]
 for rel in DOCS:
  raw=checked_read(rel);target=HAND/'evidence/repository'/rel
  pending.append((target,raw))
  rows.append({'source':rel,'sha256':sha(raw),'snapshot':str(target.relative_to(HAND)).replace('\\','/'),'kind':'document'})
 for rel in CODE:
  rows.append({'source':rel,'sha256':sha(checked_read(rel)),'snapshot':None,'kind':'source_code_pin_only_not_shipped'})
 result={'as_of':'2026-10-29','claim_boundary':'Content hashes only. Not runtime readiness or acceptance. Source code not copied into docs-only archive.','sources':rows}
 old=HAND/'evidence/source-pins.json'
 if old.exists() and json.loads(checked_read(str(old.relative_to(ROOT))))!=result:
  raise ValueError('source divergence: create a new handover/version or review changed sources before refreshing evidence')
 for target,raw in pending:
  # Existing snapshots must already agree; never overwrite divergent evidence.
  if target.exists() and checked_read(str(target.relative_to(ROOT)))!=raw:
   raise ValueError('existing evidence snapshot divergence: '+str(target.relative_to(HAND)))
 for target,raw in pending:
  if not target.exists():
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 write_json(old,result)

def package_files():
 files=[ROOT/p for p in ['HANDOVER_PACKAGE.md','START_HERE_FOR_AGENTS.md','BEFORE_DECISIONS.md','AGENTS.md','scripts/build_intern_handover.py']]
 provenance=json.loads(checked_read('skills/before/PROVENANCE.json'))
 files+=[SKILL/row['path'] for row in provenance['files']]
 files+=[SKILL/'PROVENANCE.json']
 files+=[HAND/name for name in AUTHORED]
 files+=[HAND/'evidence/repository'/rel for rel in DOCS]
 for path in files:checked_read(str(path.relative_to(ROOT)))
 return files

def validate(files):
 findings=[]
 for path in files:
  rel=path.relative_to(ROOT)
  if not allowed(rel) or path.is_symlink():findings.append('unsafe path '+str(rel))
  raw=path.read_bytes()
  for pattern in [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\bsk-[A-Za-z0-9_-]{24,}\b']:
   if re.search(pattern,raw):findings.append('potential secret-shaped content in '+str(rel))
 # New authored onboarding docs must resolve local links; copied historical evidence
 # can reference intentionally absent private/raw artifacts and is not rewritten.
 for path in [*HAND.glob('*.md'),ROOT/'START_HERE_FOR_AGENTS.md',ROOT/'HANDOVER_PACKAGE.md']:
  text=path.read_text(encoding='utf-8')
  for link in re.findall(r'\]\(([^)]+)\)',text):
   if '://' in link or link.startswith('#'):continue
   target=(path.parent/link.split('#')[0].split(':')[0]).resolve()
   if not target.exists():findings.append('broken authored link '+str(path.relative_to(ROOT))+': '+link)
 manifest=json.loads((SKILL/'PROVENANCE.json').read_text(encoding='utf-8'))
 for row in manifest['files']:
  if sha((SKILL/row['path']).read_bytes())!=row['sha256']:findings.append('vendored skill changed '+row['path'])
 if (ROOT/'BEFORE_DECISIONS.md').read_bytes()!=(SKILL/'references/decisions.md').read_bytes():findings.append('BEFORE canonical/snapshot divergence')
 for row in json.loads((HAND/'evidence/source-pins.json').read_text(encoding='utf-8'))['sources']:
  if sha(checked_read(row['source']))!=row['sha256']:findings.append('source pin changed '+row['source'])
  if row['snapshot'] and sha((HAND/row['snapshot']).read_bytes())!=row['sha256']:findings.append('evidence snapshot changed '+row['source'])
 before=json.loads((HAND/'evidence/protected-baseline.json').read_text(encoding='utf-8'))
 for rel,value in before.items():
  if sha((ROOT/rel).read_bytes())!=value:findings.append('protected file changed '+rel)
 spec=json.loads((ROOT/'tests/behavior_specs/chat_v1_1_cases.json').read_text(encoding='utf-8'))
 if len(spec['cases'])!=24:findings.append('case count changed')
 if len(manifest['files'])!=13:findings.append('skill source file count changed')
 report={'as_of':'2026-10-29','status':'pass' if not findings else 'fail','findings':findings,
 'file_count':len(files),'checks':['allowlisted paths','secret-shaped markers in allowlisted text only','new authored Markdown local links','13 vendored skill hashes','canonical/snapshot parity','source/evidence pins','AGENTS and frozen spec unchanged','24 public case count'],
 'limits':['Not an exhaustive secret scanner or Git history audit','No service/model calls performed','Copied historical docs may reference artifacts absent from package','This package does not contain full source/data/legacy','No auto-discovery proof on intern IDE; explicit bootstrap required']}
 write_json(HAND/'QA_REPORT.json',report)
 if findings:raise ValueError(json.dumps(report,ensure_ascii=False))
 return report

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--build',action='store_true');parser.add_argument('--validate',action='store_true');args=parser.parse_args()
 if args.build:evidence()
 files=package_files();report=validate(files)
 rows=[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files]
 manifest={'kind':'DOCS_ONLY_NOT_FULL_APPLICATION','as_of':'2026-10-29','files':rows}
 manifest_path=HAND/'package-manifest.json'
 if args.build:write_json(manifest_path,manifest)
 elif not manifest_path.exists() or json.loads(manifest_path.read_text(encoding='utf-8'))!=manifest:
  raise ValueError('package manifest differs; review changes and rebuild before validation')
 if args.build:
  out=ROOT/'docs/handover/releases/TVLT_Intern_Handover_2026-10-29.zip';out.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
   for path in [*files,HAND/'QA_REPORT.json',HAND/'package-manifest.json']:
    bundle.write(path,str(path.relative_to(ROOT)).replace('\\','/'))
  with zipfile.ZipFile(out) as bundle:
   if len(bundle.namelist())!=len(files)+2 or bundle.testzip() is not None:raise ValueError('archive integrity failed')
  print(json.dumps({'archive':str(out),'bytes':out.stat().st_size,'sha256':sha(out.read_bytes()),'validation':report['status'],'files':len(files)+2},ensure_ascii=False))
 else:
  out=ROOT/'docs/handover/releases/TVLT_Intern_Handover_2026-10-29.zip'
  if out.exists():
   with zipfile.ZipFile(out) as bundle:
    expected={str(p.relative_to(ROOT)).replace('\\','/') for p in [*files,HAND/'QA_REPORT.json',manifest_path]}
    if set(bundle.namelist())!=expected or bundle.testzip() is not None:raise ValueError('archive entries or CRC differ')
    for row in rows:
     if sha(bundle.read(row['path']))!=row['sha256']:raise ValueError('archive member hash differs: '+row['path'])
  print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()

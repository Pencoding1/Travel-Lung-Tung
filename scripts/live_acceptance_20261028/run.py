"""Real HTTP acceptance against actual isolated processes, not fake dependencies.

Never imports test harnesses, mocks, ASGITransport or modifies product code.
"""
import argparse
import hashlib
import http.client
import json
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cases import CASES, CRITERIA

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PORTS={'ai':19112,'backend':19113,'poi':19114,'mcp':19111}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def clean(value):
 if isinstance(value,dict):
  return {k:('[REDACTED]' if re.search(r'(?i)^(authorization|api[_-]?key|access_token|refresh_token|password|secret|traceback)$',k)
    else '[ERROR_TEXT_OMITTED]' if k in ['detail','error'] and isinstance(v,str) else clean(v)) for k,v in value.items()}
 if isinstance(value,list):return [clean(x) for x in value]
 if isinstance(value,str):return re.sub(r'(?i)Bearer\s+[^\s"<>]+','Bearer [REDACTED]',value)
 return value

def connected(port):
 with socket.socket() as connection:
  connection.settimeout(.3)
  return connection.connect_ex(('127.0.0.1',port))==0

def request(port,method,path,payload=None,timeout=80):
 start=time.monotonic()
 connection=http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
 try:
  connection.request(method,path,body=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
    headers={'Content-Type':'application/json'} if payload is not None else {})
  response=connection.getresponse();raw=response.read(2_000_001)
  if len(raw)>2_000_000:raise ValueError('response_too_large')
  try:body=json.loads(raw)
  except (ValueError,UnicodeError):body={'non_json':True,'bytes':len(raw)}
  return {'http':response.status,'body':clean(body),'seconds':round(time.monotonic()-start,3)}
 except Exception as exc:return {'http':None,'error_type':type(exc).__name__,'seconds':round(time.monotonic()-start,3)}
 finally:connection.close()

def assertions(kind,body):
 if not isinstance(body,dict):return ['response_not_object']
 errors=[]
 def require(ok,reason):
  if not ok:errors.append(reason)
 actions=body.get('actions');plan=body.get('planning') or {};booking=body.get('booking') or {}
 if kind=='claims':
  claims=body.get('claims');require(isinstance(claims,list) and bool(claims) and all(isinstance(x,dict) for x in claims),'atomic_claims_missing')
 elif kind in ('booking','booking_absent'):
  require(body.get('intent')=='BOOKING','intent_not_BOOKING');require(booking.get('type') in ['table','vehicle','room','service'],'booking_type_missing')
  require(booking.get('destination_status') in ['FOUND','NOT_FOUND','UNSPECIFIED'],'destination_status_missing')
  if booking.get('destination_status')=='FOUND':require(bool(booking.get('destination')) and bool(body.get('source_evidence_ids')),'FOUND_without_evidence')
 elif kind in ('planning_form','planning_options'):
  require(body.get('intent')=='PLAN','intent_not_PLAN');require(isinstance(plan.get('form'),dict),'editable_planning_form_missing')
  require(not body.get('handoff'),'unconfirmed_handoff')
  if kind=='planning_options':
   options=plan.get('options');require(isinstance(options,list) and len(options)>=3,'three_options_missing')
   if isinstance(options,list) and len(options)>=3:
    for n,a in enumerate(options):
     for b in options[n+1:]:
      if not isinstance(a,dict) or not isinstance(b,dict):
       require(False,'option_not_object');continue
      dims=['area_ids','pace','budget','experience_types']
      require(all(k in a and k in b for k in dims),'option_dimensions_missing')
      if any(not isinstance(x.get(k,[]),list) for x in [a,b] for k in ['area_ids','experience_types','poi_ids']):
       require(False,'option_sets_malformed');continue
      equal=lambda k:sorted(map(str,a.get(k,[])))==sorted(map(str,b.get(k,[]))) if k in ['area_ids','experience_types'] else a.get(k)==b.get(k)
      require(sum(not equal(k) for k in dims)>=2 and sorted(map(str,a.get('poi_ids',[])))!=sorted(map(str,b.get('poi_ids',[]))),'options_not_meaningfully_distinct')
 elif kind=='grounded':
  require(body.get('intent')=='CHITCHAT','information_intent_not_CHITCHAT_under_new_contract')
  require(bool(body.get('source_evidence_ids')) and bool(body.get('tool_chain')),'live_retrieval_evidence_missing')
 elif kind=='absence':
  require(body.get('status')=='insufficient_data','missing_explicit_absence_or_insufficient_data')
  require(bool(body.get('tool_chain')),'absence_without_actual_retrieval')
 elif kind in ('information_only','withdrawn','clarify_order','invalid_handoff'):
  require(isinstance(actions,list),'actions_journal_missing')
  require(not actions,'unexpected_feature_action');require(not body.get('handoff'),'unexpected_handoff')
  if kind=='information_only':require(body.get('intent')=='CHITCHAT','information_intent_not_CHITCHAT')
  if kind=='clarify_order':require(body.get('clarification_required') is True or body.get('status')=='needs_clarification','priority_clarification_missing')
 elif kind=='handoff':require(isinstance(body.get('handoff'),dict),'confirmed_handoff_missing')
 return errors

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
 out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
 results=[];processes={};runtime={};runid='live-'+uuid.uuid4().hex[:12];started=time.time();generation_blocked=False;unknown_active=False
 freeze=ROOT/'docs/contracts/frozen/TVLT-BEHAVIOR-20261028-v1/manifest.json'
 manifest=json.loads(freeze.read_text(encoding='utf-8'))
 for row in manifest['files']:assert digest(freeze.parent/row['snapshot_path'])==row['sha256']
 for row in manifest['code_baseline']:assert digest(ROOT/row['path'])==row['sha256'],'public code changed before run'
 suite={'id':'LIVE-ACCEPTANCE-20261028-v1','run_id':runid,'cases':CASES,'criteria':CRITERIA,
  'llm_attempt_policy':'one attempt per call; no retry, no fallback; stop dependent branch on fatal provider failure',
  'max_chat_http_calls':32,'max_typed_calls':2,'max_provider_component_calls':1,
  'not_equivalent_to':'historical offline 20+100; no unit/mock suite used',
  'excluded':'real booking, primary writes, crawler network/Finalizing, H1, frozen science cohorts'}
 suitepath=out/'suite-before-run.json';suitepath.write_text(json.dumps(suite,ensure_ascii=False,indent=2),encoding='utf-8')
 def persist():
  summary={'run_id':runid,'status':'IN_PROGRESS','results':results,'runtime':runtime,
   'elapsed_seconds':round(time.time()-started,2),'suite_sha256':digest(suitepath),'contract_manifest_sha256':digest(freeze)}
  (out/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 def record(id,feature,status,reason,observation=None):
  row={'id':id,'feature':feature,'status':status,'reason':reason,'observation':observation}
  results.append(row);persist();print(json.dumps({'case':id,'status':status,'reason':reason},ensure_ascii=False),flush=True)
 def drain(proc,meta):
  for line in proc.stdout:
   if line.startswith('LIVE-BOOT '):
    try:meta['startup_error']=json.loads(line[len('LIVE-BOOT '):])
    except ValueError:pass
 try:
  runtime['environment']={'missing_cached_engine_tree':not (ROOT/'.runtime-native').exists(),
    'legacy_native_venv_exists':(ROOT/'.venv-mcp-validation/Scripts/python.exe').exists(),
    'requested_application_model':'opencode-go/deepseek-v4.1-flash','requested_router':'jev-1.13.0'}
  for name,port in [('memgraph',17687),('graphhopper',18989)]:runtime[name]={'port':port,'tcp_connected':connected(port)}
  for kind,port in PORTS.items():
   meta={'port':port,'owned':False};runtime[kind]=meta
   if connected(port):meta['status']='FOREIGN_PORT_DO_NOT_ADOPT';continue
   proc=subprocess.Popen([sys.executable,'-X','utf8',str(HERE/'service_entry.py'),kind,str(port)],cwd=HERE,
    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
   processes[kind]=proc;meta.update(pid=proc.pid,owned=True)
   threading.Thread(target=drain,args=(proc,meta),daemon=True).start()
   deadline=time.monotonic()+18
   while time.monotonic()<deadline and proc.poll() is None and not connected(port):time.sleep(.25)
   meta.update(tcp_connected=connected(port),exit_code=proc.poll())
  ai=runtime['ai'].get('tcp_connected',False);backend=runtime['backend'].get('tcp_connected',False)
  if ai:
   for id,path,expected in [('OPS-AI','/healthz',200),('UI-DRAFT','/travel',200),('SCOPE-SNAPSHOTS','/catalog/snapshots',200)]:
    obs=request(PORTS['ai'],'GET',path,timeout=20)
    okay=obs.get('http')==expected
    record(id,'F-SCOPE' if id.startswith('SCOPE') else 'F-OPS','PASS' if okay else 'BLOCKED_DEPENDENCY',
      'observed_real_http' if okay else 'service_dependency_unavailable',obs)
   for id,payload in [('BOUNDARY-MODE',{'transport_mode':'bike'}),('BOUNDARY-SCOPE',{'source_scope':{'dataset_namespace':'bad','input_sha256':'x','source_area_id':'bad'}})]:
    obs=request(PORTS['ai'],'POST','/chat',{'session_id':runid+id,'message':'Xin chào','memory_enabled':False,**payload})
    record(id,'F-SCOPE','PASS' if obs['http']==422 else 'FAIL_BEHAVIOR','invalid_context_must_reject_before_models',obs)
   obs=request(PORTS['ai'],'POST','/memory/short/clear',{'session_id':runid+'-empty'})
   record('MEM-CLEAR','F-MEMORY','PASS' if obs['http']==200 and obs.get('body',{}).get('scope')=='anonymous_local_only' else 'FAIL_BEHAVIOR','clear_owned_anonymous_session',obs)
   obs=request(PORTS['ai'],'GET','/memory/profile')
   record('MEM-AUTH','F-MEMORY','PASS' if obs['http'] in [401,403,503] else 'FAIL_BEHAVIOR','anonymous_must_not_read_durable_profile',obs)
   obs=request(PORTS['ai'],'POST','/chat',{'session_id':runid+'-hello','message':'Xin chào bạn!','memory_enabled':False})
   body=obs.get('body',{});router=body.get('router',{})
   unavailable=body.get('status') in ['unavailable','failed'] or obs.get('http') in [401,403,429,503,None]
   generation_blocked=unavailable and router.get('status')=='ok'
   record('LIVE-CHAT-PREFLIGHT','F-CHAT','BLOCKED_PROVIDER' if unavailable else 'PASS_TRANSPORT_ONLY',
     'real_chat_failure_no_retry' if unavailable else 'real_response_observed_not_new_contract_acceptance',obs)
   fatal=unavailable
   for case in CASES:
    id,clause,message,kind=case[:4]
    if fatal:
     record(id,'F-CHAT','NOT_EXERCISED','dependent_chat_branch_stopped_after_provider_failure');continue
    if kind in ['absence','booking_absent','grounded'] and not runtime['memgraph']['tcp_connected']:
     record(id,'F-CHAT','BLOCKED_DEPENDENCY','grounding_or_absence_requires_actual_graph_truth');continue
    session=runid+'-'+id
    if len(case)>4:
     prep=request(PORTS['ai'],'POST','/chat',{'session_id':session,'message':case[4],'memory_enabled':True})
     prep_body=prep.get('body',{})
     if prep.get('http') in [401,403,429,503,None] or prep_body.get('status') in ['failed','unavailable']:
      fatal=True;generation_blocked=prep_body.get('router',{}).get('status')=='ok'
      record(id,'F-CHAT','BLOCKED_PROVIDER','preparatory_request_failed_no_retry',prep);continue
     options=(prep_body.get('planning') or {}).get('options',[])
     if len(options)<3:
      record(id,'F-CHAT','FAIL_BEHAVIOR','actual_preparatory_options_missing_handoff_not_exercised',prep);continue
    obs=request(PORTS['ai'],'POST','/chat',{'session_id':session,'message':message,'memory_enabled':False if len(case)==4 else True})
    body=obs.get('body',{});status=body.get('status')
    if obs.get('http') in [401,403,429,503,None] or status in ['failed','unavailable']:
     record(id,'F-CHAT','BLOCKED_PROVIDER' if status in ['unavailable','failed'] else 'BLOCKED_DEPENDENCY','real_request_failed_no_retry',obs)
     generation_blocked=body.get('router',{}).get('status')=='ok'
     fatal=True;continue
    errors=assertions(kind,body)
    # Even structurally valid grounding/booking cannot pass without cross-checking live source truth.
    if not errors:
     record(id,'F-CHAT','NOT_VERIFIED','structure_observed_but_source_or_browser_proof_still_required',obs)
    else:record(id,'F-CHAT','FAIL_BEHAVIOR',';'.join(errors),obs)
   for mode in ['car','foot']:
    if generation_blocked:
     record('PLAN-'+mode,'F-PLAN','NOT_EXERCISED','generation_provider_failed_stop_dependent_requests');continue
    obs=request(PORTS['ai'],'POST','/generate_itinerary',{'session_id':runid+'-'+mode,'travel_type':'sightseeing',
      'num_travelers':2,'start_date':'2026-11-07','target_district':'Quan 1','duration_days':1,
      'budget_range':'2000000 VND','budget_amount':2000000,'budget_currency':'VND','budget_unit':'per_party',
      'user_description':'Ưu tiên bảo tàng và cà phê, cần 2 điểm có tuyến thật.','minimum_stops':2,'maximum_stops':2,
      'memory_enabled':False,'transport_mode':mode},timeout=80)
    plan=obs.get('body',{}).get('planning',{})
    if not runtime['memgraph']['tcp_connected'] or not runtime['graphhopper']['tcp_connected']:
     record('PLAN-'+mode,'F-PLAN','BLOCKED_DEPENDENCY','real_graph_and_route_engine_required',obs)
    else:record('PLAN-'+mode,'F-PLAN','NOT_VERIFIED','requires_independent_stop_route_validation',obs)
  else:
   for case in CASES:record(case[0],'F-CHAT','NOT_EXERCISED','AI production service failed startup')
  if backend:
   for id,path,allowed in [('OPS-BACKEND-HEALTH','/health',[200]),('OPS-BACKEND-READY','/ready',[503]),('SAVED-AUTH','/api/v1/itineraries',[401,403,503])]:
    obs=request(PORTS['backend'],'GET',path)
    record(id,'F-SAVED' if id.startswith('SAVED') else 'F-OPS','PASS' if obs['http'] in allowed else 'FAIL_BEHAVIOR','production_default_no_storage_or_no_caller_identity',obs)
  # Execute the real preparation CLI over immutable real input into a new run-owned output.
  source=ROOT/'data/primary_20261016/hcm_pois_final.geojson'
  if source.is_file():
   before=digest(source);destination=out/'actual-acquisition-output'
   command=[sys.executable,'-X','utf8','-m','crawler_service.app.primary_dataset.cli','--input',str(source),'--out',str(destination)]
   try:
    completed=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,text=True,encoding='utf-8')
    try:observed=json.loads(completed.stdout)
    except ValueError:observed={'error':'no_structured_cli_result','exit_code':completed.returncode}
    assert digest(source)==before,'primary source changed'
    record('ACQUIRE-REAL-INPUT','F-ACQUIRE','PASS_PIPELINE_ONLY' if completed.returncode==0 else 'BLOCKED_DEPENDENCY',
      'actual_local_preparation_no_graph_or_network;not_full_acquisition_acceptance',{'exit_code':completed.returncode,'result':clean(observed),'input_sha256':before,'source_unchanged':True})
   except subprocess.TimeoutExpired:record('ACQUIRE-REAL-INPUT','F-ACQUIRE','NOT_EXERCISED','actual_CLI_deadline')
  else:record('ACQUIRE-REAL-INPUT','F-ACQUIRE','BLOCKED_DEPENDENCY','actual_primary_source_missing')
  for feature,reason in [('F-LOOKUP','real_MCP_graph_and_GraphHopper_required'),('F-INGEST','positive_writes_require_isolated_graph_and_legitimate_auth'),
    ('F-SAVED','positive_CRUD_requires_legitimate_authenticated_identity_and_real_storage'),
    ('F-MEMORY','durable_profile_requires_legitimate_authenticated_identity'),('F-BOOKING','no_current_Book_Ngay_or_booking_screen_implementation')]:
   record(feature+'-FULL',feature,'FAIL_BEHAVIOR' if feature=='F-BOOKING' else 'BLOCKED_DEPENDENCY',reason)
  record('UI-DESIGN','F-UI','HOLD','final_OTA_design_deferred_by_owner')
  # Independent real generation-provider component check, not a replacement for failed routing/grounding.
  if generation_blocked:
   record('GEN-PROVIDER','F-OPS','NOT_EXERCISED','generation_provider_already_failed_no_alternate_probe')
  elif not (out/'provider.json').exists():
   probe=subprocess.Popen([sys.executable,'-X','utf8',str(HERE/'provider_probe.py'),str(out/'provider.json')],cwd=HERE,
     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:probe.wait(timeout=150)
   except subprocess.TimeoutExpired:
    # Do not kill a transport while it may still own a CLI child. Preserve exact PID for follow-up.
    runtime['provider_probe']={'pid':probe.pid,'cleanup_proven':False};unknown_active=True
    record('GEN-PROVIDER','F-OPS','BLOCKED_PROVIDER','outer_deadline_active_transport_pid_preserved_no_kill')
   if (out/'provider.json').exists():
    p=json.loads((out/'provider.json').read_text(encoding='utf-8'))
    record('GEN-PROVIDER','F-OPS',p['status'],'real_provider_component_not_end_to_end',p)
   elif not unknown_active:record('GEN-PROVIDER','F-OPS','BLOCKED_PROVIDER','provider_process_exited_without_structured_result')
 except Exception as exc:
  record('HARNESS-EXECUTION','HARNESS','EXECUTION_ERROR',type(exc).__name__)
  raise
 finally:
  pending_http=any(isinstance(x.get('observation'),dict) and x['observation'].get('error_type') in ['TimeoutError','socket.timeout'] for x in results)
  if pending_http:unknown_active=True
  for kind,proc in processes.items():
   if kind=='ai' and pending_http and proc.poll() is None:
    runtime[kind]['cleanup']='NOT_PROVEN_request_timeout_owned_PID_preserved';continue
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
   runtime[kind]['cleanup_exit_code']=proc.returncode
  for row in manifest['code_baseline']:assert digest(ROOT/row['path'])==row['sha256'],'product code changed during run'
  persist()
  summary=json.loads((out/'results.json').read_text(encoding='utf-8'))
  harness_error=any(x['status']=='EXECUTION_ERROR' for x in results)
  summary.update(status='HARNESS_ERROR' if harness_error else 'COMPLETED_WITH_GAPS',primary_data_written=False,mocks_used=False,
    cleanup_owned_http_services=not unknown_active,cli_worker_idle_independently_verified=False,public_code_pins_unchanged=True)
  counts={}
  for row in results:counts[row['status']]=counts.get(row['status'],0)+1
  summary['counts']=counts
  (out/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'final':summary['status'],'counts':counts,'out':str(out)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()

"""Execute frozen v1.1 cases on actual Compose HTTP endpoints, no mocks.

Does not manufacture identities/records or replace unavailable prerequisites.
"""
import argparse
import hashlib
from http.client import HTTPConnection
import json
import socket
import time
import uuid
from urllib.parse import urlencode
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SPEC=ROOT/'tests/behavior_specs/chat_v1_1_cases.json'

def http(port,method,path,payload=None,timeout=100):
 start=time.monotonic();connection=HTTPConnection('127.0.0.1',port,timeout=timeout)
 try:
  connection.request(method,path,body=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None,
                     headers={'Content-Type':'application/json'} if payload is not None else {})
  response=connection.getresponse();raw=response.read(2_000_001)
  if len(raw)>2_000_000:raise ValueError('response_too_large')
  try:body=json.loads(raw)
  except ValueError:body={'non_json':True,'bytes':len(raw)}
  # Record only public behavioral fields, never raw headers/config/exceptions.
  keys=['status','intent','sub_intent','action','claims','requests','resolution','planning','booking',
        'handoff','actions','source_evidence_ids','tool_chain','router','provider','memory','usage']
  safe={key:body[key] for key in keys if key in body} if isinstance(body,dict) else {'invalid_shape':True}
  if isinstance(body,dict) and isinstance(body.get('error'),dict):safe['error_code']=body['error'].get('code')
  if isinstance(body,dict) and isinstance(body.get('detail'),dict):safe['detail_code']=body['detail'].get('code')
  if isinstance(body,dict) and 'snapshots' in body:safe['snapshots']=body['snapshots']
  if isinstance(body,dict) and 'source_areas' in body:safe['source_areas']=body['source_areas']
  return {'http_status':response.status,'body':safe,'seconds':round(time.monotonic()-start,3)}
 except Exception as exc:return {'http_status':None,'error_type':type(exc).__name__,'seconds':round(time.monotonic()-start,3)}
 finally:connection.close()

INTENTS={
 'I11-01':('CHITCHAT','LOOKUP'),'I11-02':('CHITCHAT','RECOMMEND'),'I11-03':('CHITCHAT','ROUTE'),
 'I11-04':('PLAN','CREATE'),'I11-05':('PLAN','MODIFY'),'I11-06':('PLAN','MODIFY'),
 'I11-07':('MANAGE_SAVED','SAVE'),'I11-08':('MANAGE_SAVED','LIST'),
 'I11-09':('MANAGE_SAVED','OPEN'),'I11-10':('MANAGE_SAVED','DELETE'),
 'I11-11':('MANAGE_SAVED','OPEN'),'I11-12':('MANAGE_MEMORY','VIEW_PROFILE'),
 'I11-13':('MANAGE_MEMORY','UPDATE_PROFILE'),'I11-14':('MANAGE_MEMORY','DELETE_PROFILE'),
 'I11-15':('MANAGE_MEMORY','CLEAR_SESSION'),'I11-18':('BOOKING',None),
 'I11-19':('BOOKING',None),'I11-20':('BOOKING',None),'I11-23':('CHITCHAT',None),
}

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--ai-port',type=int,default=8002)
 args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
 raw=SPEC.read_bytes();suite=json.loads(raw);run_id='v11-'+uuid.uuid4().hex[:12]
 frozen=ROOT/'docs/contracts/frozen/TVLT-CHAT-v1.1-20261028/manifest.json'
 manifest=json.loads(frozen.read_text(encoding='utf-8'))
 for row in manifest['files']:
  if hashlib.sha256((frozen.parent/row['snapshot']).read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('frozen_contract_changed')
 if hashlib.sha256(raw).hexdigest()!=next(x['sha256'] for x in manifest['files'] if x['source'].endswith('chat_v1_1_cases.json')):raise RuntimeError('case_source_changed')
 (out/'suite-before-run.json').write_bytes(raw)
 result={'run_id':run_id,'started_at':datetime.now(timezone.utc).isoformat(),'contract':suite['contract'],
  'spec_sha256':hashlib.sha256(raw).hexdigest(),'real_http':True,'mocks_used':False,'primary_writes':False,
  'requested_target':f'http://127.0.0.1:{args.ai_port}','provider_switches':0,'request_attempts':0,'cases':[],'preflight':[]}
 def save():
  (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 def row(case,status,reason,observation=None):
  result['cases'].append({'id':case['id'],'status':status,'reason':reason,'expected':case['expected'],
   'preconditions':case['preconditions'],'observation':observation});save()
  print(json.dumps({'id':case['id'],'status':status,'reason':reason},ensure_ascii=False),flush=True)
 health=http(args.ai_port,'GET','/healthz',timeout=5);result['preflight'].append({'id':'AI-LIVENESS',**health})
 if health.get('http_status')!=200:
  for case in suite['cases']:row(case,'BLOCKED_DEPENDENCY','Compose AI HTTP endpoint unavailable')
 else:
  catalog=http(args.ai_port,'GET','/catalog/snapshots',timeout=25)
  result['preflight'].append({'id':'ACTUAL-SOURCE-CATALOG',**catalog})
  graph_ready=catalog.get('http_status')==200 and bool(catalog.get('body',{}).get('snapshots'))
  selected_scope=None
  if graph_ready:
   snapshot=catalog['body']['snapshots'][0]
   selector={k:snapshot[k] for k in ['dataset_namespace','input_sha256'] if k in snapshot}
   if len(selector)==2:
    areas=http(args.ai_port,'GET','/catalog/source_areas?'+urlencode(selector),timeout=25)
    result['preflight'].append({'id':'ACTUAL-SOURCE-AREA',**areas})
    for area in areas.get('body',{}).get('source_areas',[]):
     selection=area.get('selection',{})
     if isinstance(selection,dict) and selection.get('source_area_id'):
      selected_scope={**selector,'source_area_id':selection['source_area_id']};break
  provider_stop=False
  for case in suite['cases']:
   id=case['id']
   if provider_stop:row(case,'NOT_EXERCISED','dependent provider branch stopped after real failure');continue
   if id in ['I11-07','I11-08','I11-09','I11-10','I11-11','I11-13','I11-14','I11-24']:
    row(case,'BLOCKED_AUTH_STORAGE','requires legitimate dedicated authenticated identity and isolated owned storage/records');continue
   if case['preconditions']:
    row(case,'BLOCKED_PRECONDITION','real context/records required; not replaced with invented fixture');continue
   if id not in ['I11-23','I11-12','I11-15','I11-17','I11-16','I11-18','I11-21'] and not graph_ready:
    row(case,'BLOCKED_DEPENDENCY','actual graph source catalog not ready');continue
   payload={'session_id':run_id+'-'+id,'message':case['message'],'memory_enabled':True,'transport_mode':'car'}
   if id=='I11-02':
    if selected_scope is None:
     row(case,'BLOCKED_PRECONDITION','actual source-area selection unavailable');continue
    payload['source_scope']=selected_scope
   obs=http(args.ai_port,'POST','/chat',payload)
   result['request_attempts']+=1
   body=obs.get('body',{});status=body.get('status')
   if not isinstance(obs.get('http_status'),int) or not 200<=obs['http_status']<300 or status in ['failed','unavailable']:
    row(case,'BLOCKED_PROVIDER' if status in ['failed','unavailable'] else 'BLOCKED_DEPENDENCY','real HTTP pipeline failure; no retry/fallback',obs)
    provider_stop=True;continue
   expected=INTENTS.get(id);errors=[];unverified=[]
   if expected:
    if body.get('intent')!=expected[0]:errors.append('main_intent_mismatch')
    observed_sub=body.get('sub_intent') or body.get('action')
    if expected[1] and observed_sub!=expected[1]:unverified.append('sub_intent_trace_not_established')
   if id!='I11-23' and not any(k in body for k in ['claims','requests']):unverified.append('claim_trace_schema_not_established')
   if id in ['I11-16','I11-17','I11-21'] and not any(k in body for k in ['resolution','requests']):unverified.append('request_resolution_trace_schema_not_established')
   # Text alone is not proof of handler gating/grounding/navigation; no broad PASS.
   row(case,'FAIL_BEHAVIOR' if errors else 'NOT_VERIFIED',';'.join(errors+unverified) if errors or unverified else 'response observed; remaining case invariants need source/action/browser evidence',obs)
 result['status']='COMPLETED_WITH_GAPS'
 result['counts']={s:sum(x['status']==s for x in result['cases']) for s in {x['status'] for x in result['cases']}}
 save();print(json.dumps({'final':result['status'],'counts':result['counts'],'out':str(out)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()

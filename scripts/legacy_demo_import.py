"""Restore approved POI payload into the dedicated local legacy graph only."""
import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'legacy/POI_service'), str(ROOT/'legacy/shared_lib'), str(ROOT/'legacy')]
os.environ.update({'POI_DB_SETTINGS_SOURCE':'process_only','MEMGRAPH_HOST':'127.0.0.1',
 'MEMGRAPH_PORT':'17687','MEMGRAPH_USER':'','MEMGRAPH_PASSWORD':'','FIRESTORE_ENABLED':'false'})
logging.disable(logging.CRITICAL)

async def main():
 from app.core.infrastructure.db.database.connector import memgraph_db
 from app.core.infrastructure.db.uow import MemgraphUnitOfWork
 from app.core.services.ingestion import POIIngestionService
 path=ROOT/'data/primary_20261016/graph_ready_v2/prepared_pois.jsonl'
 data=path.read_bytes()
 if hashlib.sha256(data).hexdigest()!='37340a8021ca7e8b37efc1053718c4c87879f95fa9937d8c53e1a0218f080dd1':
  raise RuntimeError('frozen_payload_mismatch')
 rows=[json.loads(line) for line in data.splitlines()]
 if len(rows)!=6367:raise RuntimeError('payload_count_mismatch')
 await memgraph_db.connect()
 try:
  with memgraph_db.driver.session() as session:
   count=session.run('MATCH (n:POI) RETURN count(n) AS c').single()['c']
   if count:raise RuntimeError('demo_graph_not_empty_no_reimport')
   for label in ['POI','Category','Tag']:
    session.run(f'CREATE INDEX ON :{label}(id)').consume()
   session.run('CREATE INDEX ON :POI(source_area_id)').consume()
  service=POIIngestionService(lambda:MemgraphUnitOfWork(memgraph_db))
  accepted=0
  for start in range(0,len(rows),100):
   batch=rows[start:start+100]
   result=service.process_ota_batch(batch)
   payload=result.get('payload',{})
   summary=payload.get('summary',{})
   accepted+=summary.get('accepted',0)
   print(json.dumps({'processed':start+len(batch),'accepted':accepted,'status':payload.get('status')},ensure_ascii=False),flush=True)
   if payload.get('status')!='success' or summary.get('accepted')!=len(batch):
    raise RuntimeError('application_import_failed_stop')
  with memgraph_db.driver.session() as session:
   counts={'pois':session.run('MATCH (n:POI) RETURN count(n) AS c').single()['c'],
    'categories':session.run('MATCH (n:Category) RETURN count(n) AS c').single()['c']}
  (ROOT/'legacy/runtime/import-result.json').write_text(json.dumps(counts),encoding='utf-8')
  print(json.dumps(counts),flush=True)
 finally:memgraph_db.close()

if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as e:
  print(json.dumps({'error_type':type(e).__name__,'status':'stopped'}),flush=True)
  sys.exit(1)

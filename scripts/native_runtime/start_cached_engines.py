"""START154 normal cached-engine start for the demo launcher. No model calls."""
import hashlib, importlib.util, json, subprocess, sys, time, uuid
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'.runtime-native/state/demo-startup'/uuid.uuid4().hex
HERE.mkdir(parents=True,exist_ok=False)
OLD=ROOT/'docs/project/handoffs/CORE-083/parent_restore_and_memory_check.py'
OLD_SHA='7230d0e14fb54679bf4e71237f422b814367afe10d1d813b4faefcf947d1dcbe'
PINS={
 '.runtime-native/download/libatomic1_14.2.0-4ubuntu2~24.04.1_amd64.deb':'fe49cbbc7be753528380c724a8eef5f1e31dffa9221f692c5069048d81c7449d',
 '.runtime-native/download/memgraph_3.13.2-1_amd64.deb':'e9e8ba25c045ca6641df3ef817d88ea4f34210fc7ba804eb617871f5e43f56fa',
 '.runtime-native/graphhopper-11.1/download/graphhopper-web-11.1.jar':'8462f758d9ea49edaded557cec5c687a0a24f004ec371cd4daaeb0534824ea33',
 '.runtime-native/java-21.0.12.1/root/jdk-21.0.12.1+1-jre/bin/java':'999c141a6e620c71aa4230ccb62341a89162f37818753ff006d766bf935dcbe1',
 '.runtime-native/memgraph-3.13.2/root/usr/lib/memgraph/memgraph':'6b6b12836091607219f52fe3a246087024fa6987f31d2325143d101225687277',
 'graphhopper/data/hcmc-latest.osm.pbf':'c2b7057e7a022ff929692205e4219c59640fc67fd90525a82428022b43cf4afb'}
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def write(name,data):
 (HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
def checked(argv,timeout):
 r=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 if r.returncode:raise RuntimeError('approved_command_nonzero_stop')
 return r.stdout
def main():
 result={'task':'START154-demo-cached-engine-start','model_requests':0,'started':[],'status':'checking'}
 try:
  if sha(OLD)!=OLD_SHA:raise RuntimeError('reviewed_helper_source_changed')
  spec=importlib.util.spec_from_file_location('start154_reviewed_path_parser',OLD)
  helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
  for rel,pin in PINS.items():
   if not (ROOT/rel).is_file() or sha(ROOT/rel)!=pin:raise RuntimeError('cached_public_file_missing_or_changed')
  if (ROOT/'.runtime-native/download/memgraph_3.13.2-1_amd64.deb').stat().st_size!=43561700:raise RuntimeError('cached_package_size_mismatch')
  helper.verify_routing_cache_binding() # Exactly two routing fields in RAM; no output/hash.
  for rel in ('.runtime-native/data-edge-properties-v1','.runtime-native/graphhopper-11.1/graph-cache'):
   p=ROOT/rel
   if not p.is_dir() or not any(p.iterdir()):raise RuntimeError('existing_engine_data_missing')
  for rel in ('.runtime-native/state/ownership_token','.runtime-native/state/data-edge-properties-v1.owner'):
   if not (ROOT/rel).is_file():raise RuntimeError('existing_ownership_file_missing')
  preflight='''set -euo pipefail
root=/mnt/e/Project/TVLT_2026
test -x "$root/.runtime-native/memgraph-3.13.2/root/usr/lib/memgraph/memgraph"
test -x "$root/.runtime-native/java-21.0.12.1/root/jdk-21.0.12.1+1-jre/bin/java"
test -f /usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0
test -f "$root/.runtime-native/system-libs/libatomic1/usr/lib/x86_64-linux-gnu/libatomic.so.1"
test -L "$root/.runtime-native/vendor-lib/libpython3.so"
for tool in python3 dpkg-deb curl ss setsid ldd; do command -v "$tool" >/dev/null; done
for port in 17687 18989 18990; do test -z "$(ss -ltnH "sport = :$port")"; done
test "$(df -Pk "$root" | awk 'NR==2 {print $4}')" -ge 614400
printf PREFLIGHT_OK'''
  data=checked(['wsl.exe','-d','Ubuntu','-u','duyan','-e','bash','-lc',preflight],40)
  if data.strip()!=b'PREFLIGHT_OK':raise RuntimeError('wsl_preflight_marker_missing')
  pre={'cached_public_files_verified':len(PINS),'memgraph_package_size_verified':True,'extracted_binaries_and_libraries_present':True,'two_routing_paths_RAM_only':True,'existing_data_cache_nonempty':True,'engine_ports_free':True,'no_download_install_import_rebuild':True}
  write('engine-preflight-approved.json',pre)
  result['preflight']=pre;result['status']='starting'
  write('engine-result-approved.json',result)
  checked(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/native_runtime/native_runtime.ps1'),'-Action','start'],660)
  result['started'].append('Memgraph');write('engine-result-approved.json',result)
  checked(['wsl.exe','-d','Ubuntu','-u','duyan','-e','bash','/mnt/e/Project/TVLT_2026/scripts/native_routing/start_runtime.sh'],660)
  result['started'].append('GraphHopper');write('engine-result-approved.json',result)
  from neo4j import GraphDatabase,Query
  with GraphDatabase.driver('bolt://127.0.0.1:17687',auth=None,connection_timeout=5,connection_acquisition_timeout=5,max_transaction_retry_time=0) as driver:
   with driver.session(default_access_mode='READ') as session:
    result['poi_count']=session.run(Query('MATCH (n:POI) RETURN count(n) AS c',timeout=15)).single()['c']
    result['near_by_count']=session.run(Query('MATCH ()-[r:NEAR_BY]->() RETURN count(r) AS c',timeout=30)).single()['c']
  with urlopen('http://127.0.0.1:18989/info',timeout=10) as response:info=json.load(response)
  result['routing_profiles']=sorted(p['name'] if isinstance(p,dict) else p for p in info.get('profiles',[]))
  if result['poi_count']!=6367 or result['near_by_count']!=3678397 or not {'car','foot'}.issubset(result['routing_profiles']):raise RuntimeError('actual_engine_evidence_mismatch')
  result['status']='engines_ready'
 except BaseException as exc:
  result['status']='stopped';result['error_type']=type(exc).__name__
  result['error_code']=str(exc) if type(exc) is RuntimeError else 'sanitized_exception'
 write('engine-result-approved.json',result)
 print(json.dumps(result,ensure_ascii=False));return 0 if result['status']=='engines_ready' else 1
if __name__=='__main__':raise SystemExit(main())

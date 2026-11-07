"""Run preserved source with shared installed runtime; no secret copy or global changes."""
import argparse
import hashlib
import importlib
import json
import os
import runpy
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SNAP=ROOT/'legacy'
PORTS={'mcp':19201,'ai':19202}
def connected(port):
 with socket.socket() as s:
  s.settimeout(.4)
  return s.connect_ex(('127.0.0.1',port))==0
def verify():
 if not (SNAP/'SNAPSHOT.json').is_file():raise RuntimeError('Legacy snapshot missing')
 manifest=json.loads((SNAP/'SNAPSHOT.json').read_text(encoding='utf-8'))
 for row in manifest['files']:
  p=SNAP/row['path']
  if hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise RuntimeError('Legacy source changed: '+row['path'])
 return len(manifest['files'])
def child(kind):
 service=SNAP/('ai_service' if kind=='ai' else 'POI_service')
 os.chdir(service)
 sys.path[:0]=[str(service),str(SNAP),str(SNAP/'shared_lib')]
 os.environ.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','POI_DB_SETTINGS_SOURCE':'process_only',
  'MEMGRAPH_HOST':'127.0.0.1','MEMGRAPH_PORT':'17687','MEMGRAPH_USER':'','MEMGRAPH_PASSWORD':'',
  'FIRESTORE_ENABLED':'false','GRAPHHOPPER_URL':'http://127.0.0.1:18989/route',
  'GRAPHHOPPER_PROFILES':'car','GRAPHHOPPER_CH_PROFILES':'car'})
 if kind=='mcp':
  os.environ.update({'MCP_HOST':'127.0.0.1','MCP_PORT':str(PORTS[kind])})
  runpy.run_module('app.api.mcp.tools',run_name='__main__')
 else:
  os.environ.update({'MCP_SERVER_URL':'http://127.0.0.1:19201/sse','AI_LLM_PROVIDER':'opencode_cli',
   'AI_CLI_MODEL':'opencode/deepseek-v4.1-flash-free','AI_CLI_PURE':'false','AI_CLI_MAX_ATTEMPTS':'1',
   'JEV_MODEL':'jev-1.13.0','JEV_MIN_CONFIDENCE':'0.69','JEV_MAX_ATTEMPTS':'1'})
  # Reuse existing bounded application credential loaders; never copy, expose or parse secrets here.
  from domains import jev_intent
  from domains.providers import go_credentials
  jev_intent.DEFAULT_ENV_FILE=ROOT/'.env'
  go_credentials.DEFAULT_ENV_PATH=ROOT/'.env'
  go_credentials.PROJECT_ROOT=ROOT
  import main
  # Owner-selected direct AIbox generation. Original TypeSafe Jev router remains.
  sys.path.insert(0,str(ROOT/'scripts'))
  from aibox_adapter import install
  install(main,ROOT)
  import uvicorn
  uvicorn.run(main.app,host='127.0.0.1',port=PORTS[kind],access_log=False,log_level='critical')
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--child',choices=['ai','mcp'])
 parser.add_argument('--check',action='store_true')
 parser.add_argument('-NoBrowser','--no-browser',action='store_true',dest='no_browser')
 parser.add_argument('-NoPause',action='store_true')
 args=parser.parse_args()
 count=verify()
 if args.child:
  child(args.child);return 0
 for package in ['mcp','neo4j','fastapi','uvicorn','httpx','pydantic']:
  importlib.import_module(package)
 missing=[name for name,port in [('Memgraph',17687),('GraphHopper',18989)] if not connected(port)]
 print('[LEGACY] Preserved source verified:',count,'files; shared .venv; separate ports 19201/19202.')
 print('[LEGACY] Credentials use original bounded app loaders and parent .env; no secret copies.')
 if missing:
  print('[LEGACY] Missing real dependencies: '+', '.join(missing)+'. Restore engines before starting. No download/import/rebuild performed.')
  return 3
 if args.check:return 0
 if any(connected(p) for p in PORTS.values()):
  print('[LEGACY] Port 19201/19202 already occupied; no process stopped or adopted.');return 4
 processes=[]
 try:
  for kind,port in PORTS.items():
   proc=subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--child',kind],cwd=SNAP)
   processes.append(proc)
   deadline=time.monotonic()+35
   while time.monotonic()<deadline and proc.poll() is None and not connected(port):time.sleep(.25)
   if proc.poll() is not None or not connected(port):raise RuntimeError(kind+' failed startup')
  with urllib.request.urlopen('http://127.0.0.1:19202/healthz',timeout=5) as response:
   if json.load(response).get('status')!='ok':raise RuntimeError('AI health failed')
  print('[LEGACY] http://127.0.0.1:19202/travel — Ctrl+C to stop owned legacy services.')
  print('[LEGACY] Engine TCP and AI health checked; provider inference still depends on availability.')
  if not args.no_browser:webbrowser.open('http://127.0.0.1:19202/travel')
  while all(p.poll() is None for p in processes):time.sleep(1)
  return 1
 except KeyboardInterrupt:return 0
 finally:
  for proc in processes:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=10)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  print('[LEGACY] Startup failed:',type(exc).__name__);raise SystemExit(2)

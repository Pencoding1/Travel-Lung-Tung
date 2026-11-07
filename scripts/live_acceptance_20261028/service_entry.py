"""Boot actual service code; no dependency injection or mocks."""
import json
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
kind = sys.argv[1]
port = int(sys.argv[2])
service_root = ROOT / {'ai':'ai_service','backend':'backend_service','poi':'POI_service','mcp':'POI_service'}[kind]
os.chdir(service_root)
sys.path[:0] = [str(service_root), str(ROOT), str(ROOT/'shared_lib')]
os.environ.update({'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1',
 'POI_DB_SETTINGS_SOURCE':'process_only','MEMGRAPH_HOST':'127.0.0.1','MEMGRAPH_PORT':'17687',
 'MEMGRAPH_USER':'','MEMGRAPH_PASSWORD':'','FIRESTORE_ENABLED':'false',
 'GRAPHHOPPER_URL':'http://127.0.0.1:18989/route','GRAPHHOPPER_PROFILES':'car,foot',
 'GRAPHHOPPER_CH_PROFILES':'car'})
if kind == 'ai':
 os.environ.update({'MCP_SERVER_URL':'http://127.0.0.1:19111/sse',
  'AI_LLM_PROVIDER':'opencode_cli','AI_CLI_MODEL':'opencode-go/deepseek-v4.1-flash',
  'AI_CLI_EXECUTABLE':'C:/Users/duyan/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe',
  'AI_CLI_PURE':'false','AI_CLI_MAX_ATTEMPTS':'1','AI_CLI_TIMEOUT_SECONDS':'30',
  'JEV_MODEL':'jev-1.13.0','JEV_MIN_CONFIDENCE':'0.69','JEV_MAX_ATTEMPTS':'1'})
if kind == 'backend':
 # Deliberate production default; no invented auth/storage or fake repository.
 os.environ['ITINERARY_STORAGE'] = 'none'
try:
 if kind == 'mcp':
  os.environ.update({'MCP_HOST':'127.0.0.1','MCP_PORT':str(port)})
  runpy.run_module('app.api.mcp.tools',run_name='__main__')
 else:
  import uvicorn
  uvicorn.run('main:app' if kind=='ai' else 'app.main:app',host='127.0.0.1',port=port,
              log_level='critical',access_log=False)
except BaseException as exc:
 print('LIVE-BOOT '+json.dumps({'kind':kind,'error_type':type(exc).__name__,
       'missing_module':exc.name if isinstance(exc,ModuleNotFoundError) else None}),flush=True)
 raise SystemExit(1)

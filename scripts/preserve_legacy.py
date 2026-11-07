"""Copy explicitly scoped current application source; never read/copy secrets."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'legacy'
DIRS=['ai_service','backend_service','POI_service','crawler_service','shared_lib','lib','scripts/native_runtime']
FILES=['START_DEMO.bat','setup.bat','pyproject.toml','uv.lock','docker-compose.yaml','docker-compose.integration.yaml']
EXT={'.py','.html','.js','.css','.toml','.md','.bat','.ps1','.sh','.yaml','.yml','.txt','.lock'}
def allowed(p):
 return (p.suffix.lower() in EXT or p.name=='Dockerfile') and not any(x in p.parts for x in ['__pycache__','.venv','node_modules','.git']) and not p.name.startswith('.env') and p.name not in ['KEY_EXPOSURE_EXCERPT_PRIVATE.txt','credentials.json','auth.json'] and not p.is_symlink()
def main():
 if DEST.exists():raise SystemExit('legacy already exists; refusing overwrite')
 DEST.mkdir()
 rows=[]
 paths=[p for d in DIRS for p in (ROOT/d).rglob('*') if p.is_file() and allowed(p)]
 paths += [ROOT/x for x in FILES if (ROOT/x).is_file()]
 for p in sorted(set(paths)):
  rel=p.relative_to(ROOT);out=DEST/rel;out.parent.mkdir(parents=True,exist_ok=True)
  shutil.copyfile(p,out)
  rows.append({'path':rel.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 (DEST/'SNAPSHOT.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'files':rows,'secrets_copied':False,'shared_dependencies':['parent .venv','external graph/routing','parent credential file via existing bounded application loaders']},indent=2),encoding='utf-8')
 print('Preserved',len(rows),'files in ignored legacy/; source unchanged.')
if __name__=='__main__':main()

"""Own the AI process around the actual v1.1 HTTP runner; no mock runtime."""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def live(port):
 with socket.socket() as s:
  s.settimeout(.3)
  return s.connect_ex(('127.0.0.1',port))==0
def main():
 if live(19112):raise SystemExit('Port19112 occupied; no service adopted or stopped')
 proc=subprocess.Popen([sys.executable,'-X','utf8',str(HERE/'compose_ai_entry.py')],cwd=HERE,
   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 metadata={'kind':'HYBRID_DOCKER_ENGINES_NATIVE_AI_CURRENT_SOURCE','ai_pid':proc.pid,'ai_port':19112,
  'mcp_port':8001,'model':'opencode-go/deepseek-v4.1-flash','router':'jev-1.13.0',
  'ai_production_image_build':'CANCELLED_BY_PARENT_AFTER_LARGE_CUDA_DOWNLOAD_NOT_BUILD_PASS',
  'secret_loader':'existing bounded app loaders; no value inspected/logged',
  'primary_mutations':False,'mock_dependencies':False}
 try:
  deadline=time.monotonic()+20
  while proc.poll() is None and not live(19112) and time.monotonic()<deadline:time.sleep(.2)
  command=[sys.executable,'-X','utf8',str(HERE/'run_compose_v11.py'),'--ai-port','19112','--out',sys.argv[1]]
  code=subprocess.call(command,cwd=HERE)
 finally:
  if proc.poll() is None:
   proc.terminate()
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:proc.kill();proc.wait()
  metadata['ai_parent_exit_code']=proc.returncode
  out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
  (out/'runtime.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(code)
if __name__=='__main__':main()

"""Actual current AI source bridged to Docker MCP; no fake collaborators."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT/'ai_service')
sys.path[:0]=[str(ROOT/'ai_service'),str(ROOT),str(ROOT/'shared_lib')]
os.environ.update({'MCP_SERVER_URL':'http://127.0.0.1:8001/sse',
 'AI_LLM_PROVIDER':'opencode_cli','AI_CLI_MODEL':'opencode-go/deepseek-v4.1-flash',
 'AI_CLI_EXECUTABLE':'C:/Users/duyan/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe',
 'AI_CLI_PURE':'false','AI_CLI_MAX_ATTEMPTS':'1','AI_CLI_TIMEOUT_SECONDS':'30',
 'JEV_MODEL':'jev-1.13.0','JEV_MIN_CONFIDENCE':'0.69','JEV_MAX_ATTEMPTS':'1',
 'PYTHONDONTWRITEBYTECODE':'1'})
import uvicorn
uvicorn.run('main:app',host='127.0.0.1',port=19112,log_level='critical',access_log=False)

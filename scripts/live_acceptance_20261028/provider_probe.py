"""One real production provider call; no fake model, no retry, no raw exports."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ai_service'))
os.environ.update({'AI_LLM_PROVIDER':'opencode_cli','AI_CLI_MODEL':'opencode-go/deepseek-v4.1-flash',
 'AI_CLI_EXECUTABLE':'C:/Users/duyan/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe',
 'AI_CLI_PURE':'false','AI_CLI_MAX_ATTEMPTS':'1','AI_CLI_TIMEOUT_SECONDS':'30'})

async def main():
 started=time.monotonic()
 result={'kind':'REAL_PROVIDER_COMPONENT_NOT_END_TO_END','requested_alias':'opencode-go/deepseek-v4.1-flash','attempt_budget':1}
 try:
  from domains.providers import load_provider_config,OpenCodeCliProvider
  provider=OpenCodeCliProvider(load_provider_config(),cwd=ROOT/'ai_service')
  answer=await asyncio.wait_for(provider.complete({'model':'opencode-go/deepseek-v4.1-flash',
    'messages':[{'role':'user','content':'Chỉ trả lời một câu chào ngắn bằng tiếng Việt. Không dùng công cụ.'}],
    'temperature':0,'max_tokens':64}),timeout=90)
  result.update(status='PASS_TRANSPORT_ONLY',reply=answer.get('choices',[{}])[0].get('message',{}).get('content'),usage=answer.get('usage'))
 except Exception as exc:
  result.update(status='BLOCKED_PROVIDER',error_type=type(exc).__name__,error_code=getattr(exc,'code',None))
 result['elapsed_seconds']=round(time.monotonic()-started,3)
 Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print('LIVE-PROVIDER '+json.dumps({k:result[k] for k in ('status','elapsed_seconds')}),flush=True)

asyncio.run(main())

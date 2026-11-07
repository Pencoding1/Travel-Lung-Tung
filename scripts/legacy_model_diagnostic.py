"""One real model attempt; only allowlisted error classifications leave RAM."""
import asyncio,json,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'legacy/ai_service'))
os.environ.update({'AI_LLM_PROVIDER':'opencode_cli','AI_CLI_MODEL':'opencode-go/deepseek-v4.1-flash','AI_CLI_PURE':'false','AI_CLI_MAX_ATTEMPTS':'1','AI_CLI_TIMEOUT_SECONDS':'30'})
from domains.providers import load_provider_config,OpenCodeCliProvider
from domains.providers import process,go_credentials
go_credentials.PROJECT_ROOT=ROOT
facts=[]
def observed_runner(argv,**kwargs):
 result=process.run_command(argv,**kwargs)
 raw=(result.stdout+b'\n'+result.stderr).decode('utf-8','replace').lower()
 signatures=['unknown option','unknown flag','unrecognized','invalid argument','unauthorized','forbidden','api key','authentication','rate limit','quota','insufficient','model not found','provider not found','agent not found','connection refused','fetch failed','invalid config','error','usage:','session','not supported']
 facts.append({'exit_code':result.exit_code,'timeout':result.timed_out,'matched_signatures':[s for s in signatures if s in raw],
 'option_names':sorted(set(re.findall(r'--[a-z][a-z-]{1,45}',raw)))[:20]})
 return result
async def main():
 provider=OpenCodeCliProvider(load_provider_config(),cwd=ROOT/'legacy/ai_service',runner=observed_runner)
 result={'diagnostic':'single_real_provider_call','facts':facts}
 try:
  answer=await provider.complete({'model':'opencode-go/deepseek-v4.1-flash','messages':[{'role':'user','content':'Reply hello.'}],'temperature':0})
  result['status']='success'
 except Exception as e:result.update(status='failed',error_code=getattr(e,'code',None),error_type=type(e).__name__)
 print(json.dumps(result),flush=True)
 (ROOT/'legacy/runtime/model-diagnostic.json').write_text(json.dumps(result),encoding='utf-8')
asyncio.run(main())

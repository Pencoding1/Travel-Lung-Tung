"""Offline transport boundary QA, not live behavior acceptance."""
import asyncio,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('aibox_adapter',ROOT/'scripts/aibox_adapter.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def payload():return {'model':m.MODEL,'messages':[{'role':'user','content':'hello'}]}

class KeyAndPayload(unittest.TestCase):
 def test_blank_process_never_falls_back(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'.env').write_text('AIBOX_API=synthetic-file-key')
   with self.assertRaisesRegex(m.AdapterError,'aibox_credential_invalid'):m.load_key(root,{'AIBOX_API':''})
 def test_invalid_files_sanitized(self):
  for content in ['AIBOX_API=one\nAIBOX_API=two','AIBOX_API','AIBOX_API="unclosed','OTHER=synthetic','AIBOX_API='+('x'*70000)]:
   with self.subTest(case=content[:20]),tempfile.TemporaryDirectory() as folder:
    root=Path(folder);(root/'.env').write_text(content)
    with self.assertRaises(m.AdapterError) as raised:m.load_key(root,{})
    self.assertNotIn(content,str(raised.exception))
 def test_named_key_bom_quotes(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'.env').write_text('\ufeffOTHER=unrelated\nexport AIBOX_API="synthetic-key"',encoding='utf-8')
   self.assertEqual(m.load_key(root,{}),'synthetic-key')
 def test_invalid_controls_before_io(self):
  for change in [{'stream':True},{'model':'other'},{'temperature':float('nan')},{'top_p':True},{'unexpected':1}]:
   with self.subTest(control=next(iter(change))),self.assertRaises(m.AdapterError):m.prepare({**payload(),**change})
 def test_token_cap_and_prompt_bound(self):
  data=m.prepare({**payload(),'max_completion_tokens':123})
  self.assertEqual(data['max_tokens'],123);self.assertNotIn('max_completion_tokens',data)
  with self.assertRaisesRegex(m.AdapterError,'aibox_prompt_too_large'):m.prepare({'messages':[{'role':'user','content':'x'*(m.MAX_PROMPT+1)}]})
 def test_tool_followup_message_normalization_and_safe_diagnostics(self):
  tc={'id':'c1','type':'function','function':{'name':'explore_pois','arguments':'{}'}}
  raw={'model':m.MODEL,'messages':[{'role':'user','content':'bánh mì'},{'role':'assistant','tool_calls':[tc]},{'role':'tool','tool_call_id':'c1','name':'explore_pois','content':'{}'}]}
  norm=m.prepare(raw)
  self.assertIn('content',norm['messages'][1]);self.assertIsNone(norm['messages'][1]['content'])
  self.assertNotIn('name',norm['messages'][2])
  diag=m.extract_safe_error_diagnostics(400,b'{"error":{"type":"invalid_request_error","param":"messages[1].content","message":"secret prompt"}}')
  self.assertEqual(diag['error_category'],'bad_request_schema')
  self.assertEqual(diag['safe_error_type'],'invalid_request_error')
  self.assertEqual(diag['safe_error_param'],'messages[1].content')
  self.assertNotIn('secret prompt',str(diag))

class HTTPBoundaries(unittest.IsolatedAsyncioTestCase):
 async def test_sanitized_http_errors_no_redirect_no_retry(self):
  for status,expected in [(401,'aibox_authentication_failed'),(403,'aibox_forbidden'),(429,'aibox_quota_or_rate_limit'),(302,'aibox_http_error')]:
   requests=[]
   def serve(request):
    requests.append(request);return httpx.Response(status,text='private provider detail',headers={'location':'https://other.invalid/'})
   with self.subTest(status=status),patch.object(m,'load_key',return_value='synthetic-key'):
    adapter=m.AiboxAdapter(Path('.'),transport=httpx.MockTransport(serve))
    with self.assertRaises(m.AdapterError) as raised:await adapter.complete(payload())
    self.assertEqual(raised.exception.code,expected);self.assertEqual(raised.exception.attempts,1)
    self.assertEqual(len(requests),1);self.assertEqual(str(requests[0].url),m.ENDPOINT)
    self.assertNotIn('private',str(raised.exception));self.assertNotIn('synthetic-key',repr(adapter))
 async def test_tool_calls_observed_identity_unknown_usage(self):
  call={'id':'call-1','type':'function','function':{'name':'explore_pois','arguments':'{}'}}
  def serve(request):return httpx.Response(200,json={'model':'returned-model','choices':[{'message':{'role':'assistant','content':None,'tool_calls':[call]}}]})
  with patch.object(m,'load_key',return_value='synthetic-key'):data=await m.AiboxAdapter(Path('.'),transport=httpx.MockTransport(serve)).complete(payload())
  self.assertEqual(data['choices'][0]['message']['tool_calls'],[call]);self.assertEqual(data['_provider']['observed_model'],'returned-model')
  self.assertEqual(data['usage'],{'prompt_tokens':None,'completion_tokens':None,'total_tokens':None})
 async def test_malformed_oversize_and_invalid_schema(self):
  for kind in ['malformed','oversize','wrong-role','invalid-usage']:
   def serve(request):
    if kind=='malformed':return httpx.Response(200,content=b'{broken')
    if kind=='oversize':return httpx.Response(200,content=b'x'*(m.MAX_BYTES+1))
    data={'choices':[{'message':{'role':'user' if kind=='wrong-role' else 'assistant','content':'hello'}}]}
    if kind=='invalid-usage':data['usage']={'total_tokens':-1}
    return httpx.Response(200,json=data)
   with self.subTest(kind=kind),patch.object(m,'load_key',return_value='synthetic-key'),self.assertRaises(m.AdapterError):await m.AiboxAdapter(Path('.'),transport=httpx.MockTransport(serve)).complete(payload())
 async def test_drip_feed_total_deadline(self):
  class Drip(httpx.AsyncByteStream):
   async def __aiter__(self):
    while True:
     yield b' '
     await asyncio.sleep(.01)
  def serve(request):return httpx.Response(200,stream=Drip())
  with patch.object(m,'load_key',return_value='synthetic-key'),patch.object(m,'REQUEST_DEADLINE',.04):
   with self.assertRaisesRegex(m.AdapterError,'aibox_timeout'):await m.AiboxAdapter(Path('.'),transport=httpx.MockTransport(serve)).complete(payload())

if __name__=='__main__':unittest.main()

from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from datetime import datetime,timezone
import hashlib,json
root=Path('data/expansion_20261015/raw')
query='[out:json][timeout:25][maxsize:16777216];nwr["tourism"="museum"](10.77,106.68,10.79,106.70);out center 30;'
jobs=[('wikidata-Q703871.json','https://www.wikidata.org/wiki/Special:EntityData/Q703871.json','CC0-1.0'),('wikidata-Q933384.json','https://www.wikidata.org/wiki/Special:EntityData/Q933384.json','CC0-1.0'),('osm-museums.json','https://overpass-api.de/api/interpreter?'+urlencode({'data':query}),'ODbL-1.0')]
manifest=[]
for name,url,license_id in jobs:
    target=root/name
    if target.exists(): raise RuntimeError('Refusing to overwrite existing raw file '+name)
    row={'file':name,'source_url':url,'license':license_id,'retrieved_at':datetime.now(timezone.utc).isoformat(),'synthetic':False}
    try:
        req=Request(url,headers={'User-Agent':'TVLT-Academic-Research/0.1 (bounded one-time POI sample)','Accept':'application/json'})
        with urlopen(req,timeout=40) as response:
            raw=response.read(5_000_001)
            if len(raw)>5_000_000: raise ValueError('Response exceeds5MB cap')
            parsed=json.loads(raw)
            row['http_status']=response.status
            row['sha256']=hashlib.sha256(raw).hexdigest()
            row['bytes']=len(raw)
            row['entities']=len(parsed.get('entities',parsed.get('elements',[])))
            row['collection_status']='success'
            if parsed.get('remark'): row['server_remark']=parsed['remark']
            target.write_bytes(raw)
    except Exception as exc:
        row['collection_status']='failed'; row['error_type']=type(exc).__name__; row['error']=str(exc)
    manifest.append(row)
    print(name,row['collection_status'],row.get('entities'),row.get('error',''))
(root.parent/'fetch_manifest.json').write_text(json.dumps({'dataset':'expansion_20261015','original_thesis_dataset':False,'query':query,'requests':manifest},ensure_ascii=False,indent=2),encoding='utf-8')

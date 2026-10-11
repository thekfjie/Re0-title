"""Compile pinned OpenCC data for the small browser/Python title converter."""
from pathlib import Path
import hashlib,json
import httpx

ROOT=Path(__file__).resolve().parents[1]
COMMIT='8cf737a4e193db27d675b2ce9867d84aace33745'
FILES=['STCharacters.txt','STPhrases.txt','JPShinjitaiCharacters.txt','CJK_Compatibility_Ideographs.txt']

def entries(text):
    for line in text.splitlines():
        if line and not line.startswith('#') and '\t' in line:
            key,values=line.split('\t',1)
            yield key,values.split()

def main():
    folder=ROOT/'assets/conversion';folder.mkdir(parents=True,exist_ok=True)
    sources={};records=[]
    with httpx.Client(timeout=60,follow_redirects=True) as client:
        for name in FILES+['LICENSE']:
            source=f'https://raw.githubusercontent.com/BYVoid/OpenCC/{COMMIT}/'+('LICENSE' if name=='LICENSE' else 'data/dictionary/'+name)
            response=client.get(source);response.raise_for_status();data=response.content
            (folder/name).write_bytes(data);sources[name]=data.decode()
            records.append({'file':name,'source':source,'sha256':hashlib.sha256(data).hexdigest()})
    traditional={k:v[0] for name in ['STCharacters.txt','STPhrases.txt'] for k,v in entries(sources[name])}
    japanese={}
    for key,values in entries(sources['JPShinjitaiCharacters.txt']):
        for old in values:japanese.setdefault(old,key)
    # Self mappings in the upstream compatibility entries take precedence.
    for key,values in entries(sources['JPShinjitaiCharacters.txt']):
        if key in values:japanese[key]=key
    compatibility={k:v[0] for k,v in entries(sources['CJK_Compatibility_Ideographs.txt'])}
    def compact(d):return {k:v for k,v in d.items() if k!=v}
    # Identity phrases (皇后, 干涉…) are essential guards against character fallbacks.
    payload={'version':1,'source_commit':COMMIT,'license':'Apache-2.0','traditional':traditional,'japanese':compact(japanese),'compatibility':compact(compatibility)}
    (folder/'kanji.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    (folder/'manifest.json').write_text(json.dumps({'source_commit':COMMIT,'sources':records,'pipeline':'Compatibility normalization → longest phrase / STCharacters → reverse JPShinjitaiCharacters. Not sentence translation or full OpenCC runtime.'},ensure_ascii=False,indent=2))
    print(json.dumps({'traditional_entries':len(payload['traditional']),'japanese_entries':len(payload['japanese']),'size_bytes':(folder/'kanji.json').stat().st_size}))

if __name__=='__main__':main()

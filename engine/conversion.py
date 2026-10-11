from pathlib import Path
from functools import lru_cache
import json

def replace_longest(text,mapping):
    maximum=max(map(len,mapping),default=1);out=[];offset=0
    while offset<len(text):
        for size in range(min(maximum,len(text)-offset),0,-1):
            part=text[offset:offset+size]
            if part in mapping:
                out.append(mapping[part]);offset+=size;break
        else:out.append(text[offset]);offset+=1
    return ''.join(out)

@lru_cache(maxsize=1)
def dictionary():
    return json.loads((Path(__file__).resolve().parents[1]/'assets/conversion/kanji.json').read_text())

def convert_kanji(text):
    data=dictionary()
    normalized=replace_longest(text,data['compatibility'])
    traditional=replace_longest(normalized,data['traditional'])
    converted=replace_longest(traditional,data['japanese'])
    return {'source_text':text,'text':converted,'changed':converted!=text,'method':'opencc-derived-kanji-v1','source_commit':data['source_commit']}

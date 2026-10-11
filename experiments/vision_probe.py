"""Three bounded blind-ID Critic experiments. Does not alter A or B Benchmark."""
from pathlib import Path
from io import BytesIO
import json,random
from PIL import Image
from llm.critic import rank_candidates
ROOT=Path(__file__).resolve().parents[1]
def image_bytes(path):
    im=Image.open(path).convert('RGB');im.thumbnail((640,360));b=BytesIO();im.save(b,format='PNG');return b.getvalue()
def main():
    data=json.loads((ROOT/'experiments/live-benchmark/results.json').read_text());records=[]
    for case in data['cases']:
        if case['id'] not in ('b03','b06','b09'):continue
        items=[(mode,i,l) for mode in ('A','B') for i,l in enumerate(case['modes'][mode]['candidates'])];random.Random(42).shuffle(items)
        mapping={str(i):{'mode':mode,'index':index+1,'image':l['image'],'family':l['family']} for i,(mode,index,l) in enumerate(items)}
        candidates=[(str(i),image_bytes(ROOT/'experiments/live-benchmark'/l['image'])) for i,(_,_,l) in enumerate(items)]
        try:
            result=rank_candidates([image_bytes(ROOT/'experiments/live-benchmark'/case['reference_image'])],candidates)
            records.append({'case':case['id'],'mapping':mapping,**result});print(case['id'],'critic top',mapping[result['ranking'][0]['candidate_id']],'ms',result['latency_ms'],flush=True)
        except Exception as e:records.append({'case':case['id'],'error':str(e)});print(case['id'],'critic error',str(e),flush=True)
    (ROOT/'experiments/vision_probe.json').write_text(json.dumps({'seed':42,'purpose':'exploratory critic selection; not independent human quality evidence','auto_enabled':False,'records':records},ensure_ascii=False,indent=2))
if __name__=='__main__':main()

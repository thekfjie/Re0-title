from copy import deepcopy
from pathlib import Path
import json,time
from engine.layout import load_config,LayoutEngine
from engine.text import JapaneseAnalyzer
from engine.fonts import FontFace
from engine.renderer import Renderer
ROOT=Path(__file__).resolve().parents[1]

def main():
    config=load_config();fonts={'kanji':FontFace(ROOT/'.research-fonts/noto-sans-jp-black.ttf'),'kana':FontFace(ROOT/'.research-fonts/ShipporiMincho-SemiBold.ttf')};analyzer=JapaneseAnalyzer(config['rules']);cases=json.loads((ROOT/'experiments/benchmark_cases.json').read_text());out=ROOT/'experiments/ablations';out.mkdir(exist_ok=True);rows=[]
    settings=[('balanced',True,True),('kanji_anchor',True,True),('semantic_nouns',True,True),('balanced',False,True),('balanced',True,False)]
    for case in cases:
        if case['id'] not in ('b03','b12','b14','b16'):continue
        for index,(heuristic,optical,anneal) in enumerate(settings):
            cfg=deepcopy(config);cfg['rules']['style']['optical_kerning']=optical;tokens=analyzer.analyze(case['text'],heuristic);start=time.perf_counter();layouts=LayoutEngine(fonts,cfg).generate(case['text'],tokens,seed=42,count=4,anneal=anneal);elapsed=(time.perf_counter()-start)*1000
            row={'id':case['id'],'heuristic':heuristic,'optical':optical,'anneal':anneal,'engine_latency_ms':round(elapsed,2),'best_score':max(l.score for l in layouts),'score_terms':[l.terms for l in layouts]};rows.append(row)
            best=max(layouts,key=lambda l:l.score);(out/f'{case["id"]}-{index}.png').write_bytes(Renderer().png(best))
    (out/'results.json').write_text(json.dumps({'claim_limit':'Internal scores do not establish aesthetic superiority. Four-text exploratory ablation, same fonts/seed.','runs':rows},ensure_ascii=False,indent=2));print('Ablation runs:',len(rows))

if __name__=='__main__':main()

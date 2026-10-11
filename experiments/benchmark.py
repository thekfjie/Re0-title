from pathlib import Path
import json,time,argparse,statistics,html
from PIL import Image
from engine.fonts import FontFace
from engine.layout import LayoutEngine,load_config
from engine.text import JapaneseAnalyzer
from engine.renderer import Renderer
from llm.planner import validate_plan,SemanticPlanner

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kanji',default=str(ROOT/'.research-fonts/noto-sans-jp-black.ttf'));parser.add_argument('--kana',default=str(ROOT/'.research-fonts/ShipporiMincho-SemiBold.ttf'));parser.add_argument('--live-llm',action='store_true');parser.add_argument('--seed',type=int,default=42);parser.add_argument('--out',default=str(ROOT/'experiments/benchmark'));args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    config=load_config();fonts={'kanji':FontFace(args.kanji),'kana':FontFace(args.kana)};analyzer=JapaneseAnalyzer(config['rules']);renderer=Renderer()
    cases=json.loads((ROOT/'experiments/benchmark_cases.json').read_text());plans=json.loads((ROOT/'experiments/session_plans.json').read_text())['plans'];dataset=json.loads((ROOT/'references/dataset.json').read_text());references={r['id']:r for r in dataset['samples']};rows=[]
    for case in cases:
        record={**case,'modes':{}};folder=out/case['id'];folder.mkdir(exist_ok=True)
        if case['reference_id']:
            ref=references[case['reference_id']];bbox=ref['measurements']['title_ink_bbox'];im=Image.open(ROOT/'references/originals'/ref['file']);im=im.crop((bbox[0]-30,bbox[1]-30,bbox[2]+30,bbox[3]+30));im.thumbnail((700,500));im.save(folder/'reference.jpg');record['reference_image']=case['id']+'/reference.jpg'
        try:
            tokens=analyzer.analyze(case['text'])
            plan=SemanticPlanner().plan(case['text'],tokens,json.loads((ROOT/'analysis/family_summary.json').read_text())) if args.live_llm else plans[case['id']]
            for mode in ('A','B'):
                start=time.perf_counter();active=validate_plan(case['text'],plan) if mode=='B' else tokens
                layouts=LayoutEngine(fonts,config).generate(case['text'],active,seed=args.seed,count=6,plan=plan if mode=='B' else None)
                elapsed=(time.perf_counter()-start)*1000
                candidates=[]
                for i,l in enumerate(layouts):
                    stem=f'{mode}-{i+1}';(folder/(stem+'.svg')).write_text(renderer.svg(l));(folder/(stem+'.png')).write_bytes(renderer.png(l));r=l.record();r['image']=case['id']+'/'+stem+'.png';r['svg']=case['id']+'/'+stem+'.svg';candidates.append(r)
                record['modes'][mode]={'engine_latency_ms':round(elapsed,2),'planner_latency_ms':plan.get('api_latency_ms') if mode=='B' else 0,'planner_usage':plan.get('usage') if mode=='B' else None,'candidates':candidates,'planner_provenance':plan.get('provenance') if mode=='B' else 'no_foundation_model'}
            record['semantic_plan']=plan
            print(case['id'],case['text'],{m:round(r['engine_latency_ms']) for m,r in record['modes'].items()},flush=True)
        except Exception as e:
            record['error']=str(e);print(case['id'],'ERROR',e,flush=True)
        rows.append(record)
    result={'seed':args.seed,'fonts':{k:v.metadata for k,v in fonts.items()},'live_llm':args.live_llm,'claim_limit':'Scores are internal diagnostics, not aesthetic ratings. Frozen B excludes API latency and cost. No independent human preference data.','cases':rows}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    summary={'cases':len(rows),'errors':sum('error' in r for r in rows),'candidate_count':sum(len(m['candidates']) for r in rows for m in r['modes'].values()),'live_llm':args.live_llm,'modes':{}}
    for mode in ('A','B'):
        valid=[r['modes'][mode] for r in rows if mode in r['modes']];ls=[l for r in valid for l in r['candidates']]
        summary['modes'][mode]={'engine_latency_median_ms':statistics.median(r['engine_latency_ms'] for r in valid),'score_mean':statistics.mean(l['score'] for l in ls),'collision_max':max(l['score_terms']['collision'] for l in ls),'overflow_max':max(l['score_terms']['overflow_penalty'] for l in ls),'kinsoku_max':max(l['score_terms']['kinsoku_penalty'] for l in ls),'families':sorted(set(l['family'] for l in ls))}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));write_html(out,rows,result);print(json.dumps(summary,indent=2))

def write_html(out,rows,result):
    page=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Title Lab · A/B Benchmark</title><style>body{font:15px system-ui;background:#09090b;color:#fafafa;margin:30px auto;max-width:1400px;padding:0 20px}img{width:100%;background:#000;object-fit:contain;max-height:300px}.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px}.cands{display:grid;grid-template-columns:1fr 1fr;gap:10px}a{color:#fafafa}p{color:#a1a1aa}section{margin:40px 0;padding-top:20px;border-top:1px solid #27272a}small{display:block;color:#a1a1aa}button,select{padding:8px;background:#18181b;color:#fafafa;border:1px solid #3f3f46;border-radius:6px}@media(max-width:800px){.row{grid-template-columns:1fr}}</style><h1>同字体 · 同文本 · 同 seed</h1><p>20 个固定标题 × 两套语义方案 × 6 个候选。A 完全无大模型；B 使用会话模型生成并冻结的语义 JSON。B 未调用在线 API；未测 API 延迟、成本、独立审美评分。内部 Score 仅是约束诊断。所有候选均展示。</p><button id="blind">隐藏方案标签</button> <button id="export">导出偏好记录</button> <a href="results.json">完整参数 JSON</a>']
    for r in rows:
        page.append(f'<section><h2>{r["id"]} · {html.escape(r["text"])}</h2><p>{r["category"]} · {r["split"]}</p>')
        if r.get('error'):page.append(html.escape(r['error'])+'</section>');continue
        ref=f'<img src="{r["reference_image"]}" alt="原始标题参考">' if r.get('reference_image') else '<p>未见过的文本，无原始参考。</p>'
        page.append('<div class="row"><div><h3>Reference</h3>'+ref+'</div>')
        for mode in ('A','B'):
            page.append(f'<div><h3 class="label" data-mode="{mode}">{mode}</h3><small>引擎 {r["modes"][mode]["engine_latency_ms"]:.0f} ms；六张</small><div class="cands">')
            for i,l in enumerate(r['modes'][mode]['candidates']):page.append(f'<a href="{l["svg"]}"><img loading="lazy" src="{l["image"]}" alt="{mode} 候选 {i+1}"><small>{l["family"]} · score {l["score"]:.3f}</small></a>')
            page.append('</div></div>')
        page.append(f'</div><p>偏好：<select data-case="{r["id"]}"><option value="">未评价</option><option>A</option><option>B</option><option>相当</option><option>都不满意</option></select></p></section>')
    page.append('''<script>let blind=false;document.querySelector('#blind').onclick=()=>{blind=!blind;document.querySelectorAll('.label').forEach(e=>e.textContent=blind?(e.dataset.mode==='A'?'方案 X':'方案 Y'):e.dataset.mode)};const votes=JSON.parse(localStorage.getItem('title-benchmark-votes')||'{}');document.querySelectorAll('select').forEach(s=>{s.value=votes[s.dataset.case]||'';s.onchange=()=>{votes[s.dataset.case]=s.value;localStorage.setItem('title-benchmark-votes',JSON.stringify(votes))}});document.querySelector('#export').onclick=()=>{let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({timestamp:new Date().toISOString(),votes,blind},null,2)],{type:'application/json'}));a.download='preferences.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}</script></html>''')
    (out/'index.html').write_text(''.join(page))

if __name__=='__main__':main()

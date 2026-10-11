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
    parser=argparse.ArgumentParser();parser.add_argument('--kanji',default=str(ROOT/'assets/open-fonts/noto-sans-jp-black.ttf'));parser.add_argument('--kana',default=str(ROOT/'assets/open-fonts/shippori-mincho-semibold.ttf'));parser.add_argument('--live-llm',action='store_true');parser.add_argument('--replay-plans');parser.add_argument('--seed',type=int,default=42);parser.add_argument('--out',default=str(ROOT/'experiments/benchmark'));args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    config=load_config();fonts={'kanji':FontFace(args.kanji),'kana':FontFace(args.kana)};analyzer=JapaneseAnalyzer(config['rules']);renderer=Renderer()
    cases=json.loads((ROOT/'experiments/benchmark_cases.json').read_text());plans=json.loads((ROOT/'experiments/session_plans.json').read_text())['plans'];dataset=json.loads((ROOT/'references/dataset.json').read_text());references={r['id']:r for r in dataset['samples']};rows=[]
    if args.replay_plans:plans={c['id']:c['semantic_plan'] for c in json.loads(Path(args.replay_plans).read_text())['cases']}
    live_provenance=args.live_llm or bool(args.replay_plans)
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
    result={'seed':args.seed,'fonts':{k:v.metadata for k,v in fonts.items()},'live_llm':live_provenance,'live_api_calls_this_run':len(cases) if args.live_llm else 0,'plan_source':'replayed_live' if args.replay_plans else 'live' if args.live_llm else 'frozen_session','claim_limit':'Scores are internal diagnostics, not aesthetic ratings. Frozen B excludes API latency and cost. No independent human preference data.','cases':rows}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    summary={'cases':len(rows),'errors':sum('error' in r for r in rows),'candidate_count':sum(len(m['candidates']) for r in rows for m in r['modes'].values()),'live_llm':live_provenance,'live_api_calls_this_run':len(cases) if args.live_llm else 0,'plan_source':'replayed_live' if args.replay_plans else 'live' if args.live_llm else 'frozen_session','modes':{}}
    for mode in ('A','B'):
        valid=[r['modes'][mode] for r in rows if mode in r['modes']];ls=[l for r in valid for l in r['candidates']]
        summary['modes'][mode]={'engine_latency_median_ms':statistics.median(r['engine_latency_ms'] for r in valid),'score_mean':statistics.mean(l['score'] for l in ls),'collision_max':max(l['score_terms']['collision'] for l in ls),'overflow_max':max(l['score_terms']['overflow_penalty'] for l in ls),'kinsoku_max':max(l['score_terms']['kinsoku_penalty'] for l in ls),'families':sorted(set(l['family'] for l in ls))}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));write_html(out,rows,result);print(json.dumps(summary,indent=2))

def write_html(out,rows,result):
    page=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>A / B 对照</title><style>
*{box-sizing:border-box}body{font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:#fafafa;color:#18181b;margin:0}header{height:76px;background:#fff;border-bottom:1px solid #e4e4e7;padding:0 44px;display:flex;align-items:center;justify-content:space-between}header>a{font-size:18px;font-weight:650}header nav{display:flex;gap:28px;font-size:13px}a{color:inherit;text-decoration:none}main{max-width:1500px;margin:0 auto;padding:36px 44px}h1{font-size:24px;margin:0 0 18px;font-weight:600}h2{font-size:18px;font-weight:600;margin:0 0 24px}h3{font-size:14px;font-weight:600;margin:0 0 16px}p{line-height:1.7;margin:12px 0}.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:22px}button,select{font:inherit;padding:9px 12px;color:#18181b;background:#fff;border:1px solid #d4d4d8;border-radius:6px;cursor:pointer}button:hover{background:#f4f4f5}button:focus-visible,a:focus-visible,select:focus-visible{outline:2px solid #a1a1aa;outline-offset:3px}.toolbar>a{font-size:12px;margin-left:4px}.toolbar label{display:flex;gap:7px;align-items:center;font-size:12px}input{accent-color:#18181b}section{margin:40px 0 0;padding-top:30px;border-top:1px solid #e4e4e7}.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:24px;align-items:start}.cands{display:grid;grid-template-columns:1fr 1fr;gap:12px}.cands>a{border:1px solid #e4e4e7;border-radius:7px;overflow:hidden;background:#fff;display:block}.cands>a:hover{border-color:#71717a}img{display:block;width:100%;background:#000;object-fit:contain;aspect-ratio:16/9;border-radius:7px}.cands img{border-radius:0}.candidate-number{display:block;padding:8px 10px;font-size:12px;font-weight:600}.diagnostics{display:none;color:#52525b;font-size:11px;padding:8px 10px;font-weight:400}.show-diagnostics .diagnostics{display:block}.vote{display:flex;gap:12px;align-items:center;margin-top:24px}.row>div:first-child>img{border:1px solid #e4e4e7}.no-reference{border:1px dashed #d4d4d8;border-radius:7px;aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:#52525b}.blind .diagnostics{display:none!important}@media(max-width:1000px){header{padding:0 24px}main{padding:28px 24px}.row{grid-template-columns:1fr 1fr}.row>div:first-child{grid-column:1/-1;max-width:480px}}@media(max-width:600px){header{height:66px;padding:0 20px}header>a{font-size:16px}header nav{gap:16px;font-size:12px}main{padding:24px 20px}.row{gap:16px}h3{font-size:12px}.cands{grid-template-columns:1fr}.toolbar{gap:10px}h2{line-height:1.6}section{margin-top:30px;padding-top:24px}}
</style><header><a href="/">日文标题排版</a><nav><a href="/">生成器</a><a href="/research.html">研究记录</a></nav></header><main><h1>A / B 对照</h1><p>20 条标题 · 每方案 6 张 · 同字体、文本与 Seed</p><div class="toolbar"><button id="blind">隐藏方案标签</button><button id="export">导出偏好记录</button><label><input id="diagnostics" type="checkbox">布局诊断</label><a href="results.json">参数 JSON</a></div>''']
    for r in rows:
        page.append(f'<section><h2>{r["id"]} · {html.escape(r["text"])}</h2>')
        if r.get('error'):page.append(html.escape(r['error'])+'</section>');continue
        ref=f'<img src="{r["reference_image"]}" alt="原始标题参考">' if r.get('reference_image') else '<div class="no-reference">新增文本 · 无参考图</div>'
        page.append('<div class="row"><div><h3>参考图</h3>'+ref+'</div>')
        for mode in ('A','B'):
            label='A · 传统算法' if mode=='A' else 'B · LLM 语义'
            page.append(f'<div class="scheme" data-mode="{mode}"><h3 class="label" data-mode="{mode}">{label}</h3><small class="diagnostics">引擎 {r["modes"][mode]["engine_latency_ms"]:.0f} ms</small><div class="cands">')
            for i,l in enumerate(r['modes'][mode]['candidates']):page.append(f'<a href="{l["svg"]}"><img loading="lazy" src="{l["image"]}" alt="候选 {i+1}"><span class="candidate-number">{i+1:02d}</span><small class="diagnostics">{l["family"]} · score {l["score"]:.3f}</small></a>')
            page.append('</div></div>')
        page.append(f'</div><label class="vote">偏好<select data-case="{r["id"]}"><option value="">未评价</option><option value="A">A</option><option value="B">B</option><option>相当</option><option>都不满意</option></select></label></section>')
    page.append('''</main><script>let blind=false;document.querySelector('#diagnostics').onchange=e=>document.body.classList.toggle('show-diagnostics',e.target.checked);document.querySelector('#blind').onclick=()=>{blind=!blind;document.body.classList.toggle('blind',blind);document.querySelector('#blind').textContent=blind?'显示方案标签':'隐藏方案标签';document.querySelectorAll('.label').forEach(e=>e.textContent=blind?(e.dataset.mode==='A'?'方案 X':'方案 Y'):(e.dataset.mode==='A'?'A · 传统算法':'B · LLM 语义'));document.querySelectorAll('option[value="A"]').forEach(e=>e.textContent=blind?'方案 X':'A');document.querySelectorAll('option[value="B"]').forEach(e=>e.textContent=blind?'方案 Y':'B')};let votes={};try{votes=JSON.parse(localStorage.getItem('title-benchmark-votes')||'{}')}catch{}document.querySelectorAll('select').forEach(s=>{s.value=votes[s.dataset.case]||'';s.onchange=()=>{votes[s.dataset.case]=s.value;localStorage.setItem('title-benchmark-votes',JSON.stringify(votes))}});document.querySelector('#export').onclick=()=>{let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({timestamp:new Date().toISOString(),votes,blind},null,2)],{type:'application/json'}));a.download='preferences.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}</script></html>''')
    note='<p>B 语义计划：真实 API · '+html.escape(rows[0]['semantic_plan'].get('model','未知'))+'</p>' if result['live_llm'] else '<p>B 语义计划：固定计划 · 未调用在线 API</p>'
    document=''.join(page).replace('<div class="toolbar">',note+'<div class="toolbar">',1)
    (out/'index.html').write_text(document)

if __name__=='__main__':main()

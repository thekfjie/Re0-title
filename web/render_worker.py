"""Runs in an isolated, bounded subprocess. Task fonts are deleted by parent."""
from pathlib import Path
import json,sys,resource,time

def main():
    resource.setrlimit(resource.RLIMIT_CPU,(45,45))
    resource.setrlimit(resource.RLIMIT_AS,(1536*1024*1024,1536*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
    from engine.fonts import FontFace
    from engine.text import JapaneseAnalyzer
    from engine.layout import LayoutEngine,load_config
    from engine.renderer import Renderer
    from llm.planner import validate_plan
    job=Path(sys.argv[1]);args=json.loads((job/'input.json').read_text());start=time.perf_counter()
    fonts={k:FontFace(job/p) for k,p in args['font_paths'].items()};config=load_config()
    plan=args.get('plan')
    tokens=validate_plan(args['text'],plan) if plan else JapaneseAnalyzer(config['rules']).analyze(args['text'],args.get('heuristic'))
    layouts=LayoutEngine(fonts,config).generate(args['text'],tokens,args['seed'],args['count'],args['width'],args['height'],args['palette'],plan,anneal=args.get('anneal',True))
    renderer=Renderer();results=[]
    for i,l in enumerate(layouts):
        stem=f'candidate-{i+1}';(job/(stem+'.svg')).write_text(renderer.svg(l,args.get('transparent',False)))
        (job/(stem+'.png')).write_bytes(renderer.png(l,args.get('transparent',False)))
        record=l.record();record['id']=stem;results.append(record)
    (job/'results.json').write_text(json.dumps({'candidates':results,'engine_latency_ms':round((time.perf_counter()-start)*1000,2)},ensure_ascii=False))

if __name__=='__main__':main()

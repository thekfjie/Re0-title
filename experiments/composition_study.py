"""Paired ablation: existing layout versus glyph relationship composition.

Same fonts/text/seed/shaping/scoring for both arms. Reference annotations are
used only after generation. New texts have no reconstruction target.
"""
from pathlib import Path
from copy import deepcopy
from io import BytesIO
import argparse, hashlib, json, statistics, time
from PIL import Image, ImageDraw, ImageFont
from engine.fonts import FontFace
from engine.layout import LayoutEngine, load_config
from engine.text import JapaneseAnalyzer
from engine.renderer import Renderer
from experiments.reference_comparison import compare_record, geometry_from_layout

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDS = ['s002', 's005', 's006', 's014', 's024', 's030', 's033', 's035', 's038', 's039', 's048', 's052', 's060', 's064', 's077', 's079']
UNSEEN = ['記憶の海で、名前を呼ぶ', '最後の灯りと、最初の約束', '誰も知らない明日', '君の声はまだ消えない']


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');args=parser.parse_args()
    out=ROOT/'experiments/composition-study';out.mkdir(exist_ok=True)
    config=load_config();fonts={k:FontFace(ROOT/'assets/open-fonts'/f) for k,f in [('kanji','noto-sans-jp-black.ttf'),('kana','shippori-mincho-semibold.ttf')]}
    analyzer=JapaneseAnalyzer(config['rules']);renderer=Renderer()
    samples=json.loads((ROOT/'references/dataset.json').read_text())['samples']
    # Use the revised 98-unit review, including corrected repeated spans.
    colors={s['id']:{'accent_units':s['units']} for s in json.loads((ROOT/'analysis/color_position_study.json').read_text())['cases']}
    fine={s['sample_id']:s for s in json.loads((ROOT/'analysis/fine_annotations.json').read_text())['samples']}
    rows=[s for s in samples if args.all or s['id'] in DEFAULT_IDS]+[{'id':f'u{i+1:02}', 'text':text} for i,text in enumerate(UNSEEN)]
    cases=[]
    for sample in rows:
        case={'id':sample['id'],'text':sample['text'],'reference':sample['id'].startswith('s'),'arms':{}}
        folder=out/case['id'];folder.mkdir(exist_ok=True)
        tokens=analyzer.analyze(case['text']);theme='day' if sample.get('measurements',{}).get('config',{}).get('background')=='white' else 'night'
        for name,enabled in [('previous',False),('composition',True)]:
            arm=deepcopy(config);arm['rules']['composition']['enabled']=enabled
            start=time.perf_counter();layouts=LayoutEngine(fonts,arm).generate(case['text'],tokens,seed=42,count=6,canvas_theme=theme)
            result={'latency_ms':round((time.perf_counter()-start)*1000,2),'candidates':[]}
            for i,l in enumerate(layouts):
                stem=f'{name}-{i+1}';(folder/(stem+'.png')).write_bytes(renderer.png(l));(folder/(stem+'.svg')).write_text(renderer.svg(l))
                record=l.record();record['comparison_geometry']=geometry_from_layout(l)
                if case['reference']:record['comparison']=compare_record(record,sample,colors[case['id']],fine.get(case['id']))
                record.update(image=f'{case["id"]}/{stem}.png',svg=f'{case["id"]}/{stem}.svg')
                result['candidates'].append(record)
            case['arms'][name]=result
        cases.append(case);print(case['id'],case['text'],flush=True)
    def metrics(name):
        candidates=[c['arms'][name]['candidates'][0] for c in cases if c['reference'] and c['id']!='s069']
        geom=[c['comparison']['geometry'] for c in candidates if c['comparison']['geometry']]
        height=[c['comparison']['fine_height']['ink_height_mean_absolute_log_error'] for c in candidates if c['comparison']['fine_height']]
        all_candidates=[l for c in cases for l in c['arms'][name]['candidates']]
        return {'exact_breaks':sum(c['comparison']['exact_break_match'] for c in candidates),'count_match':sum(c['comparison']['line_count_error']==0 for c in candidates),
                'mean_accent_jaccard':statistics.mean(c['comparison']['accent_position_jaccard'] for c in candidates),
                'median_aspect_log_error':statistics.median(g['aspect_log_error'] for g in geom),
                'mean_fine_ink_height_log_error':statistics.mean(height),
                'max_collision':max(l['score_terms']['collision'] for l in all_candidates),
                'overflow_count':sum(bool(l['score_terms']['overflow_penalty']) for l in all_candidates),
                'kinsoku_count':sum(bool(l['score_terms']['kinsoku_penalty']) for l in all_candidates),
                'text_integrity_failures':sum(''.join(l['lines'])!=c['text'] or ''.join(g['text'] for g in l['glyphs'])!=''.join(ch for ch in c['text'] if not ch.isspace()) for c in cases for l in c['arms'][name]['candidates']),
                'latency_median_ms':statistics.median(c['arms'][name]['latency_ms'] for c in cases)}
    result={'seed':42,'target_annotations_passed_to_engine':False,'story_context_passed_to_engine':False,'sample_set':'development references plus unscored new texts',
            'fonts':{k:f.metadata['sha256'] for k,f in fonts.items()},'config':config,'arm_parameters':{'previous':{'composition.enabled':False},'composition':{'composition.enabled':True}},'summary':{name:metrics(name) for name in ['previous','composition']},'cases':cases}
    review_path=ROOT/'analysis/color_position_study.json'
    result['color_annotation']={'path':'analysis/color_position_study.json','sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),'unit_count':98}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'summary.json').write_text(json.dumps(result['summary'],indent=2))
    # Browser index retains all candidates without megabytes of glyph paths.
    compact={k:v for k,v in result.items() if k not in ('config','cases')}
    compact['cases']=[{k:v for k,v in c.items() if k!='arms'} | {'arms':{name:{'latency_ms':arm['latency_ms'],'candidates':[{k:l[k] for k in ('image','svg','family','lines','score','comparison_geometry')} | {'comparison':l.get('comparison'), 'composition':l['metadata'].get('composition')} for l in arm['candidates']]} for name,arm in c['arms'].items()}} for c in cases]
    (out/'index.json').write_text(json.dumps(compact,ensure_ascii=False))
    font=ImageFont.truetype(str(ROOT/'assets/open-fonts/noto-sans-jp-black.ttf'),17)
    for block in range(0,len(cases),8):
        subset=cases[block:block+8];sheet=Image.new('RGB',(1440,len(subset)*225),'#fafafa');draw=ImageDraw.Draw(sheet)
        for i,c in enumerate(subset):
            y=i*225;draw.text((12,y+6),c['id']+' '+c['text'],font=font,fill='#18181b')
            paths=[ROOT/'experiments/reference-benchmark'/c['id']/'reference.jpg',out/c['arms']['previous']['candidates'][0]['image'],out/c['arms']['composition']['candidates'][0]['image'],out/c['arms']['composition']['candidates'][1]['image']]
            for col,path in enumerate(paths):
                if path.exists():
                    im=Image.open(path).convert('RGB');im.thumbnail((350,190));sheet.paste(im,(col*360+5,y+28))
                draw.text((col*360+5,y+205),['Reference','Previous default','New default','New candidate 2'][col],font=font,fill='#52525b')
        sheet.save(out/f'contact-{block//8+1}.jpg',quality=92)
    print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':run()

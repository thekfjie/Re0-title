"""Run A on all reference texts, then compare output with independent annotations.

Reference lines, accent offsets, family and image metrics are never passed to A.
This is a development-sample diagnostic, not a held-out aesthetic evaluation.
"""
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import argparse, hashlib, json, math, statistics, time
import numpy as np
import yaml
from engine.fonts import FontFace
from engine.layout import LayoutEngine, load_config
from engine.text import JapaneseAnalyzer, NO_START, NO_END, script
from engine.renderer import Renderer, raster_metrics, scaled_mask

ROOT=Path(__file__).resolve().parents[1]


def jaccard(a,b):
    return len(a&b)/len(a|b) if a|b else 1.0


def glyph_positions(glyphs):
    return {i:g for g in glyphs for i in range(g['source_start'],g['source_end'])}


def ink_aspect(layout,resolution=240):
    factor=resolution/layout.width;canvas=np.zeros((round(layout.height*factor),resolution),bool)
    for g in layout.glyphs:
        mask=scaled_mask(g,factor);x=round(g.x*factor);y=round(g.y*factor)
        x0=max(0,x);y0=max(0,y);x1=min(resolution,x+mask.shape[1]);y1=min(canvas.shape[0],y+mask.shape[0])
        if x1>x0 and y1>y0:canvas[y0:y1,x0:x1]|=mask[y0-y:y1-y,x0-x:x1-x]
    ys,xs=np.nonzero(canvas)
    return (xs.max()-xs.min()+1)/(ys.max()-ys.min()+1) if len(xs) else None


def geometry_from_layout(layout,resolution=240):
    metrics=raster_metrics(layout,resolution)
    return {'aspect_ratio':float(ink_aspect(layout,resolution)),'box_fill':metrics['box_fill'],'ink_fill':metrics['ink_fill'],'centroid':metrics['centroid']}


def compare_record(record,reference,color_review,fine=None):
    cfg=reference['measurements']['config'];eligible=cfg['eligible_primary_black']
    fg=record['metadata']['resolved_palette']['foreground'].lower()
    accents={p for g in record['glyphs'] if g['color'].lower()!=fg for p in range(g['source_start'],g['source_end'])}
    observed={p for u in color_review['accent_units'] for p in range(u['start'],u['end'])}
    geometry=None
    if eligible:
        measured=reference['measurements'];g=record['comparison_geometry'];rc=measured['binary_ink_centroid_normalized']
        geometry={'aspect_log_error':abs(math.log(g['aspect_ratio']/measured['title_bbox_aspect_ratio'])),
                  'box_fill_absolute_error':abs(g['box_fill']-measured['bbox_area_fraction_of_canvas']),
                  'ink_fill_absolute_error':abs(g['ink_fill']-(1-measured['canvas_whitespace_ratio'])),
                  'centroid_distance':math.hypot(g['centroid'][0]-rc[0],g['centroid'][1]-rc[1])}
    height=None
    if fine:
        by_position=glyph_positions(record['glyphs']);kanji=[g['height'] for g in record['glyphs'] if any(script(c)=='kanji' for c in g['text'])]
        if kanji:
            median=statistics.median(kanji);errors=[]
            for unit in fine['units']:
                if unit['unit_kind']!='character':continue
                g=by_position.get(unit['char_span'][0])
                if g:errors.append(abs(math.log((g['height']/median)/unit['ink_height_relative_to_median_kanji'])))
            if errors:height={'ink_height_mean_absolute_log_error':statistics.mean(errors),'measured_character_count':len(errors)}
    return {'line_count_error':abs(len(record['lines'])-len(reference['observed_lines'])),
            'exact_break_match':record['lines']==reference['observed_lines'],
            'family_match':record['family']==reference['layout_family'],
            'accent_position_jaccard':jaccard(accents,observed),'generated_accent_positions':sorted(accents),
            'reference_accent_positions':sorted(observed),'geometry':geometry,'fine_height':height}


def select_diagnostic(candidates):
    # A transparent lexicographic choice AFTER rendering. It is not the default winner.
    def key(c):
        x=c['comparison'];g=x['geometry'] or {}
        return (not x['exact_break_match'],x['line_count_error'],-x['accent_position_jaccard'],g.get('aspect_log_error',0),c['index'])
    return min(candidates,key=key)['index']


def summary(cases):
    valid=[c for c in cases if c['status']=='ok'];comparable=[c for c in valid if c['comparison_eligible']]
    reliable=[c for c in comparable if c['pixel_geometry_eligible']]
    def metrics(selected):
        selected=[c for c in selected if c is not None]
        return {'line_count_match_count':sum(c['comparison']['line_count_error']==0 for c in selected),
                'exact_break_match_count':sum(c['comparison']['exact_break_match'] for c in selected),
                'family_match_count':sum(c['comparison']['family_match'] for c in selected),
                'mean_accent_position_jaccard':statistics.mean(c['comparison']['accent_position_jaccard'] for c in selected) if selected else None}
    first=[c['candidates'][0] for c in comparable];picked=[c['candidates'][c['diagnostic_candidate']] for c in comparable]
    geo={k:statistics.median(c['candidates'][0]['comparison']['geometry'][k] for c in reliable) for k in ['aspect_log_error','box_fill_absolute_error','ink_fill_absolute_error','centroid_distance']}
    fine=[c for c in first if c['comparison']['fine_height']]
    all_candidates=[x for c in valid for x in c['candidates']]
    return {'sample_count':len(cases),'generated_sample_count':len(valid),'failed_sample_count':sum(c['status']=='error' for c in cases),
            'candidate_count':len(all_candidates),'comparison_sample_count':len(comparable),'pixel_geometry_sample_count':len(reliable),
            'fine_height_sample_count':len(fine),'default_candidate':metrics(first),'diagnostic_candidate':metrics(picked),
            'six_candidate_coverage':{'line_count_match_count':sum(any(x['comparison']['line_count_error']==0 for x in c['candidates']) for c in comparable),
                'exact_break_match_count':sum(any(x['comparison']['exact_break_match'] for x in c['candidates']) for c in comparable),
                'family_match_count':sum(any(x['comparison']['family_match'] for x in c['candidates']) for c in comparable),
                'mean_best_accent_position_jaccard':statistics.mean(max(x['comparison']['accent_position_jaccard'] for x in c['candidates']) for c in comparable)},
            'default_geometry_medians':geo,'default_fine_height_mean_log_error':statistics.mean(c['comparison']['fine_height']['ink_height_mean_absolute_log_error'] for c in fine),
            'text_integrity_failures':sum(not c['text_integrity'] for c in all_candidates),
            'kinsoku_failures':sum(bool(c['score_terms']['kinsoku_penalty']) for c in all_candidates),
            'overflow_failures':sum(bool(c['score_terms']['overflow_penalty']) for c in all_candidates),
            'maximum_ink_collision':max(c['score_terms']['collision'] for c in all_candidates),
            'engine_latency_median_ms':statistics.median(c['engine_latency_ms'] for c in valid),
            'first_line_count_mismatches':[c['id'] for c in comparable if c['candidates'][0]['comparison']['line_count_error']],
            'first_accent_zero_overlap':[c['id'] for c in comparable if c['candidates'][0]['comparison']['accent_position_jaccard']==0],
            'claim_limit':'First candidate is the engine default. Diagnostic candidate uses reference annotations after generation. Per-metric coverage may come from different candidates; no aesthetic score or held-out claim.'}


def crop_reference(s,folder,size):
    source=Image.open(ROOT/'references/originals'/s['file']).convert('RGB');cfg=s['measurements']['config'];a,b,c,d=cfg['canvas']
    raw=source.crop((a,b,c,d));raw.resize(size,Image.Resampling.LANCZOS).save(folder/'source.jpg',quality=88)
    clean=Image.new('RGB',(c-a,d-b),'white' if cfg['background']=='white' else 'black')
    x0,y0,x1,y1=cfg['clip'];x0=max(a,x0);y0=max(b,y0);x1=min(c,x1);y1=min(d,y1)
    clean.paste(source.crop((x0,y0,x1,y1)),(x0-a,y0-b))
    painter=ImageDraw.Draw(clean)
    for x0,y0,x1,y1 in cfg.get('exclude_rectangles',[]):painter.rectangle((x0-a,y0-b,x1-a-1,y1-b-1),fill='white' if cfg['background']=='white' else 'black')
    clean.resize(size,Image.Resampling.LANCZOS).save(folder/'reference.jpg',quality=90)


def write_contact_sheets(out,cases):
    qa=ROOT/'analysis/full-reference-contact-sheets';qa.mkdir(exist_ok=True)
    font=ImageFont.truetype(str(ROOT/'assets/open-fonts/noto-sans-jp-black.ttf'),18)
    for block in range(0,len(cases),12):
        subset=cases[block:block+12];sheet=Image.new('RGB',(1440,len(subset)*150),'#fafafa');draw=ImageDraw.Draw(sheet)
        for i,c in enumerate(subset):
            y=i*150;draw.text((10,y+8),c['id']+' '+c['text'],font=font,fill='#18181b')
            for col,path in enumerate([c['reference_image'],c['candidates'][0]['image'] if c['candidates'] else None,c['candidates'][c['diagnostic_candidate']]['image'] if c['candidates'] else None]):
                if path:
                    image=Image.open(out/path);image.thumbnail((400,112));sheet.paste(image,(140+col*425,y+33))
            draw.text((10,y+55),'REF / A1 /',font=font,fill='#52525b');draw.text((10,y+80),'DIAGNOSTIC',font=font,fill='#52525b')
        sheet.save(qa/f'{block//12+1}.jpg',quality=88)


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='experiments/reference-benchmark');args=parser.parse_args();out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    evaluation=yaml.safe_load((ROOT/'config/reference_evaluation.yaml').read_text());config=load_config();renderer=Renderer()
    fonts={role:FontFace(ROOT/'assets/open-fonts'/evaluation[f'{role}_font']) for role in ('kanji','kana')};engine=LayoutEngine(fonts,config);analyzer=JapaneseAnalyzer(config['rules'])
    source=json.loads((ROOT/'references/dataset.json').read_text())['samples'];colors={c['id']:c for c in json.loads((ROOT/'analysis/color_reference_review.json').read_text())['samples']};fine={s['sample_id']:s for s in json.loads((ROOT/'analysis/fine_annotations.json').read_text())['samples']};cases=[]
    for s in source:
        folder=out/s['id'];folder.mkdir(exist_ok=True);crop_reference(s,folder,(evaluation['width'],evaluation['height']))
        cfg=s['measurements']['config'];theme='day' if cfg['background']=='white' else 'night';case={'id':s['id'],'text':s['text'],'observed_lines':s['observed_lines'],'observed_family':s['layout_family'],'background':s['background'],'canvas_theme':theme,'transcription_confidence':s['transcription_confidence'],'flags':cfg['flags'],'comparison_eligible':s['id'] not in evaluation['excluded_transcription_ids'],'pixel_geometry_eligible':cfg['eligible_primary_black'],'reference_image':s['id']+'/reference.jpg','source_image':s['id']+'/source.jpg','reference_accent_units':colors[s['id']]['accent_units'],'candidates':[]}
        try:
            begin=time.perf_counter();tokens=analyzer.analyze(s['text'])
            # Only input text, public engine config, fonts, seed and canvas theme.
            layouts=engine.generate(s['text'],tokens,seed=evaluation['seed'],count=evaluation['count'],width=evaluation['width'],height=evaluation['height'],palette=evaluation['palette'],canvas_theme=theme,color_mode=evaluation['color_mode'])
            case['engine_latency_ms']=round((time.perf_counter()-begin)*1000,2)
            for i,l in enumerate(layouts):
                stem=f'A-{i+1}';(folder/(stem+'.svg')).write_text(renderer.svg(l));(folder/(stem+'.png')).write_bytes(renderer.png(l));record=l.record();record.update(index=i,image=s['id']+'/'+stem+'.png',svg=s['id']+'/'+stem+'.svg',text_integrity=''.join(l.lines)==s['text'] and ''.join(g.text for g in l.glyphs)==''.join(c for c in s['text'] if not c.isspace()),comparison_geometry=geometry_from_layout(l,evaluation['mask_resolution']))
                record['comparison']=compare_record(record,s,colors[s['id']],fine.get(s['id']));case['candidates'].append(record)
            case['diagnostic_candidate']=select_diagnostic(case['candidates']);case['status']='ok'
            print(s['id'],s['text'],case['engine_latency_ms'],'ms',flush=True)
        except Exception as error:case.update(status='error',error=str(error),diagnostic_candidate=None);print(s['id'],'ERROR',error,flush=True)
        cases.append(case)
    result={'version':1,'algorithm':'A classic beam + anneal','llm_api_calls':0,'evaluation_config':evaluation,'engine_config_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),'fonts':{k:v.metadata for k,v in fonts.items()},'generation_reference_inputs':['text','canvas_theme'],'target_annotations_passed_to_engine':False,'dataset_split':'development_reference_reconstruction; not held-out','cases':cases}
    result_summary=summary(cases);result['summary']=result_summary
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(out/'summary.json').write_text(json.dumps(result_summary,ensure_ascii=False,indent=2))
    catalog=[{k:c[k] for k in ['id','text','observed_lines','observed_family','canvas_theme','transcription_confidence','flags','reference_image','source_image','comparison_eligible','pixel_geometry_eligible']} for c in cases]
    (ROOT/'references/catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2));(out/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2))
    # The interactive page loads a compact index; full glyph records download on demand.
    index={**result,'cases':[{**{k:v for k,v in c.items() if k!='candidates'},'candidates':[{k:x[k] for k in ['index','image','svg','family','lines','score','comparison']} for x in c['candidates']]} for c in cases]}
    (out/'index.json').write_text(json.dumps(index,ensure_ascii=False))
    write_contact_sheets(out,cases);print(json.dumps(result_summary,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

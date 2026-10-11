"""Measure variation and colour safety without using the model as an aesthetic judge."""
from pathlib import Path
import json,math,collections
from engine.layout import LayoutEngine,load_config
from engine.fonts import FontFace
from engine.text import JapaneseAnalyzer
from engine.renderer import Renderer
from engine.design import resolve_palette,contrast

ROOT=Path(__file__).resolve().parents[1]
TEXTS=['鎖の音','待ちかねた再会','命の価値','聖域の終わりと、崩壊の始まり']
SEEDS=[42,43,77]

def seed_changes(rows):
    values=[]
    for row in rows:
        base=row['runs'][0]['candidates']
        for run in row['runs'][1:]:
            for candidate in base:
                peer=next((c for c in run['candidates'] if c['family']==candidate['family'] and c['lines']==candidate['lines']),None)
                if not peer or len(peer['glyphs'])!=len(candidate['glyphs']):continue
                n=len(peer['glyphs']);rms=math.sqrt(sum(((a['x']-b['x'])/1200)**2+((a['y']-b['y'])/675)**2 for a,b in zip(candidate['glyphs'],peer['glyphs']))/n)
                values.append({'text':row['text'],'seed':run['seed'],'family':candidate['family'],'normalized_position_rms':rms,'color_pattern_changed':candidate['colors']!=peer['colors'],'relative_ink_fill_change':abs(peer['ink_fill']-candidate['ink_fill'])/max(candidate['ink_fill'],.001)})
    return {'matched_candidates':len(values),'median_position_rms':sorted(v['normalized_position_rms'] for v in values)[len(values)//2] if values else 0,'median_relative_ink_fill_change':sorted(v['relative_ink_fill_change'] for v in values)[len(values)//2] if values else 0,'color_pattern_changed':sum(v['color_pattern_changed'] for v in values),'pairs':values}

def main():
    folder=ROOT/'analysis/seed-color-audit';folder.mkdir(parents=True,exist_ok=True)
    cfg=load_config();fonts={'kanji':FontFace(ROOT/'assets/open-fonts/noto-sans-jp-black.ttf'),'kana':FontFace(ROOT/'assets/open-fonts/shippori-mincho-semibold.ttf')};analyzer=JapaneseAnalyzer(cfg['rules']);renderer=Renderer();rows=[];distribution=collections.Counter()
    for index,text in enumerate(TEXTS):
        runs=[];tokens=analyzer.analyze(text)
        for seed in SEEDS:
            candidates=LayoutEngine(fonts,cfg).generate(text,tokens,seed=seed,count=6)
            runs.append({'seed':seed,'candidates':[{'family':l.family,'lines':l.lines,'ink_fill':l.terms['ink_fill'],'colors':[g.color for g in l.glyphs],'glyphs':[{'x':g.x,'y':g.y,'size':g.size} for g in l.glyphs],'color_decisions':l.metadata['color_decisions'],'variation_profile':l.metadata['variation_profile']} for l in candidates]})
            for l in candidates:distribution[l.terms['accent_color_count']]+=1
            (folder/f'case-{index+1}-seed-{seed}.svg').write_text(renderer.svg(candidates[0]))
            (folder/f'case-{index+1}-seed-{seed}.png').write_bytes(renderer.png(candidates[0]))
        rows.append({'text':text,'runs':runs})
    palette_checks=[];render_checks=[]
    for theme in ['night','day']:
        for palette in cfg['colors']['palettes']:
            p=resolve_palette(cfg['colors'],palette,theme)
            palette_checks.append({'theme':theme,'palette':palette,'foreground_contrast':contrast(p['foreground'],p['background']),'accent_contrasts':[contrast(c,p['background']) for c in p['accents']]})
            layouts=LayoutEngine(fonts,cfg).generate(TEXTS[-1],analyzer.analyze(TEXTS[-1]),count=4,canvas_theme=theme,palette=palette,color_mode='dual')
            for l in layouts:
                assert l.terms['low_contrast_penalty']==0 and l.terms['overflow_penalty']==0 and l.terms['kinsoku_penalty']==0
                render_checks.append({'theme':theme,'palette':palette,'family':l.family,'min_contrast':l.terms['min_color_contrast'],'color_count':l.terms['accent_color_count'],'collisions':l.terms['collision'],'color_decisions':l.metadata['color_decisions']})
    before_path=ROOT/'analysis/seed_color_before.json';before=json.loads(before_path.read_text()) if before_path.exists() else None
    result={'reference_color_counts':{'0':19,'1':37,'2':2,'4':1},'new_sampled_color_counts':dict(distribution),'before_seed_changes':seed_changes(before) if before else None,'after_seed_changes':seed_changes(rows),'runs':rows,'palette_checks':palette_checks,'render_checks':render_checks,'limitations':'Position/ink/contrast diagnostics are not an independent aesthetic score. Matched-family comparisons exclude changed breaks. Colored-area score uses glyph bounding-box areas, not exact chromatic ink mass.'}
    (ROOT/'analysis/seed_color_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'before':{k:v for k,v in result['before_seed_changes'].items() if k!='pairs'} if before else None,'after':{k:v for k,v in result['after_seed_changes'].items() if k!='pairs'},'colors':dict(distribution),'render_checks':len(render_checks)},ensure_ascii=False))

if __name__=='__main__':main()

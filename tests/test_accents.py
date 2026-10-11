import json
from pathlib import Path
import pytest
from engine.accent import select_accents, validate_color_settings
from engine.layout import load_config, LayoutEngine
from engine.text import JapaneseAnalyzer, Token
from engine.fonts import FontFace
from engine.renderer import Renderer

ROOT=Path(__file__).resolve().parents[1]

def test_repeated_chinese_and_japanese_particles_are_not_automatic_anchors():
    rules=load_config()['rules']
    for text in ['聖域の終わりと、崩壊の始まり','圣域的终结与崩坏的开始']:
        tokens=JapaneseAnalyzer(rules).analyze(text)
        for variant in range(3):
            choices=select_accents(tokens,variant,2,rules,{'emphasis_relation':['の','的']})
            assert choices
            assert all(tokens[i].text[j] not in 'の的' for i,j in choices)

def test_bridge_is_a_short_composition_exception_not_high_semantic_importance():
    rules=load_config()['rules'];tokens=JapaneseAnalyzer(rules).analyze('命の価値')
    choice=select_accents(tokens,1,1,rules)
    assert [(tokens[i].text[j],d['reason']) for (i,j),d in choice.items()]==[('の','short_visual_bridge')]
    assert tokens[1].importance==rules['heuristics']['pos']['particle']

def test_repeated_planner_word_colours_only_one_occurrence_and_keeps_budget():
    rules=load_config()['rules'];tokens=JapaneseAnalyzer(rules).analyze('再会と再会')
    choice=select_accents(tokens,0,1,rules,{'emphasis_relation':['再会']})
    assert len(choice)==1 and next(iter(choice))[0]==0

def test_custom_palette_and_span_validation_reject_injection_and_invalid_ranges():
    assert validate_color_settings('約束',{'foreground':'#FFFFFF','accents':['#22C55E']},[{'start':1,'end':2,'color':'#123ABC'}])[1][0]['color']=='#123abc'
    for colors,spans in [({'accents':[]},[]),({'foreground':'url(x)'},[]),(None,[{'start':0,'end':3,'color':'#ffffff'}]),(None,[{'start':True,'end':2,'color':'#ffffff'}])]:
        with pytest.raises(ValueError):validate_color_settings('約束',colors,spans)

def test_manual_colour_targets_one_occurrence_and_transparent_png_has_alpha():
    cfg=load_config();text='聖域の終わりと崩壊の始まり';tokens=JapaneseAnalyzer(cfg['rules']).analyze(text)
    fonts={k:FontFace(ROOT/'assets/open-fonts'/file) for k,file in [('kanji','noto-sans-jp-black.ttf'),('kana','shippori-mincho-semibold.ttf')]}
    first=text.index('の');second=text.rindex('の')
    layouts=LayoutEngine(fonts,cfg).generate(text,tokens,count=4,anneal=False,custom_colors={'accents':['#22c55e','#f97316','#06b6d4']},color_overrides=[{'start':first,'end':first+1,'color':'#123456'}])
    from PIL import Image
    from io import BytesIO
    for l in layouts:
        assert next(g for g in l.glyphs if g.source_start==first).color=='#123456'
        assert next(g for g in l.glyphs if g.source_start==second).color!='#123456'
        assert l.metadata['color_warnings'] # Manual low contrast is retained with feedback.
        assert 'data-start=' in Renderer().svg(l,True) and '<rect' not in Renderer().svg(l,True)
        image=Image.open(BytesIO(Renderer().png(l,True))).convert('RGBA')
        assert image.getpixel((0,0))[3]==0 and image.getextrema()[3][1]>0

def test_all_references_have_occurrence_specific_color_review():
    data=json.loads((ROOT/'analysis/color_reference_review.json').read_text())
    assert len(data['samples'])==82
    for sample in data['samples']:
        for unit in sample['accent_units']:assert sample['text'][unit['start']:unit['end']]==unit['text']

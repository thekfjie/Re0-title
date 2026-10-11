from pathlib import Path
import statistics
import pytest
from engine.fonts import FontFace
from engine.layout import LayoutEngine, load_config
from engine.text import JapaneseAnalyzer, script

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def setup():
    config=load_config();config['rules']['composition']['enabled']=True
    fonts={k:FontFace(ROOT/'assets/open-fonts'/f) for k,f in [('kanji','noto-sans-jp-black.ttf'),('kana','shippori-mincho-semibold.ttf')]}
    return config,fonts


@pytest.mark.parametrize('text',['リリアナ・マスカレード','ゴージャス・タイガー','聖域の始まりと、崩壊の始まり','君の声はまだ消えない'])
def test_composition_preserves_text_and_checks_ink_constraints(setup,text):
    config,fonts=setup;tokens=JapaneseAnalyzer(config['rules']).analyze(text)
    layouts=LayoutEngine(fonts,config).generate(text,tokens,seed=42,count=6)
    for l in layouts:
        assert ''.join(l.lines)==text
        assert ''.join(g.text for g in l.glyphs)==text
        assert l.terms['overflow_penalty']==0 and l.terms['kinsoku_penalty']==0
        assert l.terms['collision']<=config['rules']['hard_constraints']['max_ink_overlap']
        assert l.metadata['composition']['uses_story_context'] is False
        widths=[g.width for g in l.glyphs if script(g.text[0])=='katakana' and g.text!='ー']
        if widths:
            assert all(g.width<statistics.median(widths)*1.7 for g in l.glyphs if g.text=='ー')


def test_visual_bridge_does_not_promote_particle_importance(setup):
    config,fonts=setup;text='命の価値';tokens=JapaneseAnalyzer(config['rules']).analyze(text)
    layouts=LayoutEngine(fonts,config).generate(text,tokens,seed=42,count=6,anneal=False)
    assert any(g.color_reason=='visual_bridge' for l in layouts for g in l.glyphs)
    assert next(t for t in tokens if t.text=='の').importance==config['rules']['heuristics']['pos']['particle']


def test_repeated_function_words_and_manual_occurrence_override(setup):
    config,fonts=setup;text='聖域の始まりと、崩壊の始まり';tokens=JapaneseAnalyzer(config['rules']).analyze(text)
    first=text.index('の');last=text.rindex('の')
    for mode in ['auto','none']:
        layouts=LayoutEngine(fonts,config).generate(text,tokens,count=4,anneal=False,color_mode=mode,color_overrides=[{'start':first,'end':first+1,'color':'#123456'}])
        for l in layouts:
            foreground=l.metadata['resolved_palette']['foreground']
            assert next(g for g in l.glyphs if g.source_start==first).color=='#123456'
            assert next(g for g in l.glyphs if g.source_start==last).color==foreground
            if mode=='none':assert all(g.color==foreground for g in l.glyphs if g.source_start!=first)

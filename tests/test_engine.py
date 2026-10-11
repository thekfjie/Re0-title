from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
import pytest
from engine.fonts import FontFace,UploadFontProvider
from engine.layout import load_config,LayoutEngine
from engine.text import JapaneseAnalyzer,NO_START,NO_END
from engine.renderer import Renderer
from llm.planner import validate_plan

ROOT=Path(__file__).resolve().parents[1]
FONT=ROOT/'.research-fonts/noto-sans-jp-black.ttf'
KANA=ROOT/'.research-fonts/ShipporiMincho-SemiBold.ttf'

@pytest.fixture(scope='module')
def fonts():
    if not FONT.exists():pytest.skip('Pass local research fonts to run rendering integration tests')
    return {'kanji':FontFace(FONT),'kana':FontFace(KANA)}

def test_font_owner_and_ttl(tmp_path):
    if not FONT.exists():pytest.skip('research font unavailable')
    p=UploadFontProvider(tmp_path,ttl=30);r=p.register(FONT.read_bytes(), '../../evil.ttf','owner-A')
    assert p.resolve(r['font_id'],'owner-A').parent==p._owner('owner-A')
    with pytest.raises(ValueError):p.resolve(r['font_id'],'owner-B')
    with pytest.raises(ValueError):p.resolve('../'+r['font_id'],'owner-A')
    import os,time
    file=p.resolve(r['font_id'],'owner-A');os.utime(file,(time.time()-31,time.time()-31));p.cleanup();assert not file.exists()

def test_strict_plan_preserves_input():
    text='待ちかねた再会';plans=json.loads((ROOT/'experiments/session_plans.json').read_text())['plans'];plan=plans['b03'];assert ''.join(t.text for t in validate_plan(text,plan))==text
    changed={**plan,'tokens':[dict(t) for t in plan['tokens']]};changed['tokens'][0]['text']='持'
    with pytest.raises(ValueError):validate_plan(text,changed)
    changed={**plan,'x':123}
    with pytest.raises(ValueError):validate_plan(text,changed)

def test_shaping_ligatures_and_ink_metrics(fonts):
    f=fonts['kanji'];glyphs=f.shape('office');assert len(glyphs)<=6
    assert all(g.advance>0 for g in glyphs)
    k=f.shape('の')[0];assert k.bounds[2]>k.bounds[0] and k.mask.any()
    assert f.missing('聖域の終わり')==[]

@pytest.mark.parametrize('text',['聖域の終わりと、崩壊の始まり','「最後の約束」は、まだ終わらない。','第7章 ZEROからの再出発'])
def test_layout_reading_order_safe_bounds_and_seed(fonts,text):
    config=load_config();tokens=JapaneseAnalyzer(config['rules']).analyze(text)
    a=LayoutEngine(fonts,config).generate(text,tokens,seed=77,count=4)
    b=LayoutEngine(fonts,config).generate(text,tokens,seed=77,count=4)
    assert [Renderer().svg(l) for l in a]==[Renderer().svg(l) for l in b]
    for l in a:
        assert ''.join(l.lines)==text
        assert all(s[0] not in NO_START and s[-1] not in NO_END for s in l.lines)
        assert all(g.x>=0 and g.y>=0 and g.x+g.width<=l.width+.001 and g.y+g.height<=l.height+.001 for g in l.glyphs)
        root=ET.fromstring(Renderer().svg(l));assert len(root.findall('{http://www.w3.org/2000/svg}path'))>0
        assert root.find('{http://www.w3.org/2000/svg}text') is None
        assert Renderer().png(l).startswith(b'\x89PNG')

def test_missing_glyph_rejected(fonts):
    config=load_config();t=JapaneseAnalyzer(config['rules']).analyze('星と🚀')
    with pytest.raises(ValueError,match='缺字'):LayoutEngine(fonts,config).generate('星と🚀',t)

import pytest
from engine.conversion import convert_kanji
from engine.design import contrast,resolve_palette,variation_profile
from engine.layout import load_config
from llm.planner import validate_translation

@pytest.mark.parametrize('source,target',[
    ('圣域的终结与崩坏的开始','聖域的終結与崩壊的開始'),
    ('繁體國家與愛情','繁体国家与愛情'),
    ('头发发展干杯皇后','頭髪発展乾杯皇后'),
    ('聖域の終わりと、崩壊の始まり','聖域の終わりと、崩壊の始まり'),
    ('皇后の約束 ZERO 第7章','皇后の約束 ZERO 第7章'),
])
def test_conversion_preserves_grammar_and_existing_japanese(source,target):
    result=convert_kanji(source)
    assert result['source_text']==source and result['text']==target
    assert convert_kanji(target)['text']==target

def test_theme_palettes_are_readable_and_use_separate_day_accents():
    cfg=load_config()
    for theme in ['day','night']:
        for name in cfg['colors']['palettes']:
            palette=resolve_palette(cfg['colors'],name,theme)
            assert contrast(palette['foreground'],palette['background'])>=4.5
            assert all(contrast(color,palette['background'])>=3 for color in palette['accents'])
    assert resolve_palette(cfg['colors'],'night','day')['accents']!=resolve_palette(cfg['colors'],'night','night')['accents']

def test_seed_design_profile_is_repeatable_and_changes_composition():
    rules=load_config()['rules'];a=variation_profile(42,rules);b=variation_profile(77,rules)
    assert a==variation_profile(42,rules)
    assert a['row_direction']!=b['row_direction']
    assert abs(a['fill']-b['fill'])>.1
    assert abs(a['baseline_scale']-b['baseline_scale'])>.3

def test_translation_rejects_coordinates_multiline_and_oversized_output():
    assert validate_translation({'japanese_text':'聖域の終わりと、崩壊の始まり'})
    for payload in [{'japanese_text':'約束','x':1},{'japanese_text':'a\nb'},{'japanese_text':'終'*81},{'japanese_text':''}]:
        with pytest.raises(ValueError):validate_translation(payload)

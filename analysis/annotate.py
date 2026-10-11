"""Human transcription, not OCR. Unknown geometric quantities remain null.
Run after measure_references.py. Every source file has an annotation.
"""
from pathlib import Path
import json, re, collections

ROOT = Path(__file__).resolve().parents[1]
# ID order is chronological filename order. | denotes an observed line break.
ROWS = [
('始まりの終わりと|終わりの始まり','offset_stack','始','black'),
('再会の魔女','interwoven','魔','black'),
('ゼロから始まる|異世界生活','offset_stack','異','black'),
('ロズワール邸の|団欒','offset_stack','団','black'),
('約束した朝は遠く','interwoven','束','black'),
('鎖の音','compact_anchor','鎖','black'),
('ナツキ・スバルの|リスタート','offset_stack','リ','black'),
('泣いて泣き喚いて|泣き止んだから','offset_stack','泣','black'),
('勇気の意味','interwoven','意','black'),
('鬼がかったやり方','interwoven','や','black'),
('レム','compact_anchor','ム','black'),
('再来の王都','interwoven','再','black'),
('自称騎士|ナツキ・スバル','offset_stack','ス','black'),
('絶望という病','interwoven','病','black'),
('狂気の外側','interwoven','狂','black'),
('豚の欲望','interwoven','欲','black'),
('醜態の|果てに','offset_stack','醜','black'),
('ゼロから','compact_anchor','ロ','black'),
('白鯨攻略戦','wide_block','白','black'),
('ヴィルヘルム・|ヴァン・アストレア','offset_stack','ヴ','black'),
('絶望に抗う|賭け','offset_stack','賭','black'),
('怠惰一閃','wide_block','閃','black'),
('悪辣なる怠惰','interwoven','怠','black'),
('自称騎士と|最優の騎士','offset_stack','騎','black'),
('ただそれだけの物語','interwoven','物語','white'),
('Memory Snow','wide_block','','glow'),
('氷結の絆','compact_anchor','結','decorated'),
('それぞれの誓い','interwoven','誓','black'),
('次なる場所','interwoven','次','white'),
('待ちかねた再会','interwoven','待再','black'),
('親子','compact_anchor','子','decorated_white'),
('踏み出した一歩','interwoven','出','black'),
('少女の福音','interwoven','の','black'),
('ユージン','compact_anchor','ユ','black'),
('命の価値','interwoven','の','black'),
('らぶらぶ|らぶらぶ|らぶらぶゆー','offset_stack','らぶ','black'),
('地獄なら知っている','interwoven','獄知','black'),
('死の味','compact_anchor','の味','black'),
('魔女たちの|茶会','offset_stack','女たの茶会','black'),
('泣きたくなる音','interwoven','音','black'),
('STRAIGHT BET','wide_block','B','black'),
('オットー・スーウェン','interwoven','オ','black'),
('信じる理由','interwoven','理','gradient'),
('クウェインの石は|一人じゃ上がらない','offset_stack','一人','black'),
('記憶の旅路','interwoven','記','black'),
('平家星の|笑った日','offset_stack','星','black'),
('エリオール大森林の|永久凍土','offset_stack','永久凍土','black'),
('聖域の|始まりと、|崩壊の|始まり','alternating_steps','聖り壊ま','black'),
('咆哮の再会','interwoven','哮','black'),
('水面に映る幸せ','interwoven','幸','reflection'),
('血と臓物まで|愛して','offset_stack','血臓物','black'),
('俺を選べ','compact_anchor','選','black'),
('月下出鱈目なステップ','interwoven','月鱈ス','gradient'),
('劇場型悪意','wide_block','劇場型','decorated'),
('氷炎の結末','interwoven','氷の','black'),
('ゴージャス・|タイガー','offset_stack','ガー','black'),
('都市庁舎奪還作戦','wide_block','奪還','black'),
('濁流','compact_anchor','濁流','texture'),
('騎士の条件','interwoven','騎','black'),
('最も新しい英雄と|最も古い英雄','offset_stack','新英','white'),
('いつか好きになる人','interwoven','好','black'),
('混戦都市','wide_block','','decorated'),
('強欲攻略戦','wide_block','攻略','black'),
('リリアナ・|マスカレード','offset_stack','リ','glow'),
('レグルス・コルニアス','wide_block','','white'),
('戦士の称賛','interwoven','戦','black'),
('テレシア|ヴァン・アストレア','offset_stack','ヴァン','black'),
('醜悪なる|晩餐会','offset_stack','餐','black'),
('■■なる|晩餐会','offset_stack','餐','white_masked'),
('プリステラ攻防戦|リザルト','offset_stack','','decorated_white'),
('君を連れ出す理由','interwoven','君','black'),
('ゴージャス・|タイガー・|リローデッド','offset_stack','ガー','black'),
('砂時間を越えろ','interwoven','','black'),
('監視塔の番人','interwoven','番','black'),
('白い|星空の|アステリズム','offset_stack','','glow'),
('棒振り','compact_anchor','棒','black'),
('ユリウス・|ユークリウス','offset_stack','ウ','white'),
('コンビニを出ると、|そこは不思議の世界でした','offset_stack','コンビニ','black'),
('オマエハ|ダレダ','offset_stack','オマエハダレダ','black'),
('殺人は|癖になる','alternating_steps','殺癖','black'),
('残骸','compact_anchor','残骸','texture'),
('Re:ゼロから始まる|異世界生活','offset_stack','Re:','white'),
]

def script(c):
    if '\u4e00' <= c <= '\u9fff' or c in '々〆': return 'kanji'
    if '\u3040' <= c <= '\u309f': return 'hiragana'
    if '\u30a0' <= c <= '\u30ff' or c == 'ー': return 'katakana'
    if c.isdigit(): return 'number'
    if c.isascii() and c.isalpha(): return 'latin'
    if c.isspace(): return 'space'
    return 'punctuation'

def main():
    files=sorted((ROOT/'references/originals').glob('*.jpg'))
    assert len(files)==len(ROWS)==82
    path=ROOT/'analysis/measurements.json'
    measurements=json.loads(path.read_text()) if path.exists() else []
    if isinstance(measurements,dict):measurements=measurements.get('samples',[])
    by_id={m.get('id',m.get('sample_id',f"s{m.get('index',0):03d}")):m for m in measurements}
    fine_path=ROOT/'analysis/fine_annotations.json'
    fine={r['sample_id']:r for r in json.loads(fine_path.read_text())['samples']} if fine_path.exists() else {}
    records=[]
    from sudachipy import dictionary,tokenizer
    tok=dictionary.Dictionary().tokenizer()
    for i,(file,(line,family,accent,background)) in enumerate(zip(files,ROWS),1):
        text=line.replace('|',''); lines=line.split('|')
        counts=dict(collections.Counter(script(c) for c in text))
        tokens=[]
        for m in tok.tokenize(text,tokenizer.Tokenizer.SplitMode.B):
            tokens.append({'text':m.surface(),'pos':list(m.part_of_speech()),'role':'particle' if m.part_of_speech()[0]=='助詞' else 'punctuation' if m.part_of_speech()[0]=='補助記号' else 'content','relative_size':None,'color':None,'bbox':None})
        records.append({'id':f's{i:03d}','file':file.name,'text':text,'observed_lines':lines,'character_count':len(text),'script_counts':counts,'punctuation':[c for c in text if script(c)=='punctuation'],'line_count':len(lines),'line_lengths':[len(s) for s in lines],'layout_family':family,'background':background,'scale_regime_observation':'early_large' if i<=24 else 'later_smaller','accent_characters_observed':accent,'tokens':tokens,'measurements':by_id.get(f's{i:03d}'),'transcription_confidence':'low' if i==69 else 'medium' if i in (36,53,58,65,80) else 'high','font_mixing':'visual_hypothesis' if counts.get('hiragana',0) else 'undetermined','glyph_size_ratio':None,'glyph_spacing':None,'scale_x':None,'scale_y':None,'rotation': 'visible' if i==81 else 'not_observed','overlap':'undetermined','notes':'标题文本由 contact sheet 人工转写；bbox、角色、字距需细标。#69 遮挡用 ■ 表示未知字，不恢复猜测。中文翻译不是副标题。'})
    for r in records:
        if r['id'] in fine:r['fine_annotation']=fine[r['id']]
    (ROOT/'references/dataset.json').write_text(json.dumps({'schema_version':1,'annotation_method':'manual_visual + SudachiB + image_measurements + selected_ink_unit_annotations','samples':records},ensure_ascii=False,indent=2))
    summary=collections.Counter(r['layout_family'] for r in records)
    (ROOT/'analysis/family_summary.json').write_text(json.dumps(dict(summary),indent=2))
    print(summary)

if __name__=='__main__':main()

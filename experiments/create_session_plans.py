"""Frozen semantic JSON written by the session assistant, not a live API run.
These inputs/outputs are inspectable research artifacts; no fabricated usage.
"""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
CASES=[
('b01','鎖の音','s006','short','compact_anchor',[('鎖','keyword',.96),('の','particle',.10),('音','concept',.78)],['鎖']),
('b02','レム','s011','katakana_short','compact_anchor',[('レム','keyword',1.)],['ム']),
('b03','待ちかねた再会','s030','mixed','interwoven',[('待','keyword',.9),('ちかねた','modifier',.30),('再会','concept',1.)],['待','再']),
('b04','絶望という病','s014','mixed','interwoven',[('絶望','concept',.84),('という','connector',.22),('病','keyword',1.)],['病']),
('b05','白鯨攻略戦','s019','all_kanji','wide_block',[('白鯨','keyword',.94),('攻略戦','noun',.78)],['白']),
('b06','命の価値','s035','colored_particle','interwoven',[('命','keyword',.94),('の','particle',.13),('価値','concept',.86)],['の']),
('b07','ナツキ・スバルのリスタート','s007','katakana','offset_stack',[('ナツキ','noun',.80),('・','punctuation',.02),('スバル','noun',.86),('の','particle',.09),('リスタート','concept',1.)],['リ']),
('b08','ヴィルヘルム・ヴァン・アストレア','s020','long_name','offset_stack',[('ヴィルヘルム','noun',.83),('・','punctuation',.02),('ヴァン','noun',.88),('・','punctuation',.02),('アストレア','noun',.78)],['ヴァン']),
('b09','聖域の始まりと、崩壊の始まり','s048','punctuation_repeat','alternating_steps',[('聖域','keyword',.95),('の','particle',.10),('始まり','concept',.70),('と','connector',.13),('、','punctuation',.02),('崩壊','keyword',1.),('の','particle',.10),('始まり','concept',.70)],['聖','壊']),
('b10','氷炎の結末','s055','contrast','interwoven',[('氷','keyword',.98),('炎','keyword',.98),('の','particle',.1),('結末','concept',.85)],['氷','の']),
('b11','最も新しい英雄と最も古い英雄','s060','parallel','offset_stack',[('最も','modifier',.35),('新しい','modifier',.82),('英雄','keyword',.96),('と','connector',.13),('最も','modifier',.35),('古い','modifier',.82),('英雄','keyword',.96)],['新','古']),
('b12','コンビニを出ると、そこは不思議の世界でした','s078','long','offset_stack',[('コンビニ','noun',.83),('を','particle',.1),('出る','verb',.59),('と','connector',.1),('、','punctuation',.02),('そこ','other',.35),('は','particle',.1),('不思議','concept',.85),('の','particle',.1),('世界','keyword',.99),('でした','other',.22)],['コンビニ','世界']),
('b13','オマエハダレダ','s079','katakana_question','offset_stack',[('オマエハ','other',.68),('ダレダ','concept',1.)],['ダレダ']),
('b14','聖域の終わりと、崩壊の始まり',None,'unseen_requested','offset_stack',[('聖域','keyword',.92),('の','particle',.1),('終わり','concept',.82),('と','connector',.13),('、','punctuation',.02),('崩壊','keyword',1.),('の','particle',.1),('始まり','concept',.82)],['終','始']),
('b15','記憶を失った星の旅人',None,'unseen_medium','interwoven',[('記憶','concept',.83),('を','particle',.1),('失った','verb',.58),('星','keyword',.97),('の','particle',.1),('旅人','noun',.88)],['星']),
('b16','「最後の約束」は、まだ終わらない。',None,'unseen_quotes','offset_stack',[('「','punctuation',.02),('最後','modifier',.68),('の','particle',.1),('約束','keyword',1.),('」','punctuation',.02),('は','particle',.1),('、','punctuation',.02),('まだ','modifier',.38),('終わらない','verb',.88),('。','punctuation',.02)],['約','終']),
('b17','第7章 ZEROからの再出発',None,'unseen_latin_number','interwoven',[('第7章','noun',.57),(' ','other',.05),('ZERO','keyword',.86),('から','connector',.19),('の','particle',.1),('再出発','concept',1.)],['再']),
('b18','いつか、またここで',None,'unseen_hiragana','interwoven',[('いつか','modifier',.62),('、','punctuation',.02),('また','modifier',.50),('ここ','concept',.85),('で','particle',.1)],['ここ']),
('b19','夜明けと黄昏、出会いと別れ',None,'unseen_parallel','offset_stack',[('夜明け','concept',.88),('と','connector',.1),('黄昏','concept',.88),('、','punctuation',.02),('出会い','concept',.88),('と','connector',.1),('別れ','concept',.88)],['夜','黄']),
('b20','超電脳都市ネオ・トーキョー',None,'unseen_kanji_katakana','offset_stack',[('超電脳都市','noun',.89),('ネオ','modifier',.59),('・','punctuation',.02),('トーキョー','keyword',1.)],['電','トー']),
]

def main():
    cases=[];plans={}
    for id,text,reference,category,family,items,emphasis in CASES:
        assert ''.join(s for s,_,_ in items)==text
        cases.append({'id':id,'text':text,'reference_id':reference,'category':category,'split':'reference_evaluation' if reference else 'unseen_text'})
        plans[id]={'tokens':[{'text':s,'semantic_role':r,'importance':v,'visual_role':'primary' if v>=.8 else 'connector' if r in ('particle','connector') else 'secondary'} for s,r,v in items],'suggested_layout_family':family,'emphasis_relation':emphasis,'provenance':'session_assistant_frozen_semantics_v1'}
    (ROOT/'experiments/benchmark_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
    (ROOT/'experiments/session_plans.json').write_text(json.dumps({'provenance':'Produced by the coding assistant in this session, frozen before comparison; not a live API result. Model identity/usage/cost/latency not measured.','plans':plans},ensure_ascii=False,indent=2))

if __name__=='__main__':main()

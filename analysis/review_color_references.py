"""Reproducible summary of a manual review of all 82 supplied title screenshots.

Offsets refer to Unicode scalar occurrences, not every copy of a spelling.
Colours are visual labels from contact sheets, not sampled exact source RGB.
"""
from pathlib import Path
from collections import Counter
import json

ROOT = Path(__file__).resolve().parents[1]
# text, occurrence (zero based), observed appearance, visual function.
REVIEW = {
1:[('始',0,'grey-violet','repeated_contrast')],2:[('魔',0,'yellow','content_anchor')],3:[('異',0,'red','content_anchor')],4:[('団',0,'blue','word_internal')],5:[('束',0,'blue','word_internal')],6:[('鎖',0,'pink','content_anchor')],7:[('リ',0,'yellow','katakana_fragment')],8:[('泣',2,'grey-violet','repeated_contrast')],9:[('意',0,'blue','word_internal')],10:[('や',0,'pink','kana_fragment')],11:[('ム',0,'blue','katakana_fragment')],12:[('再',0,'yellow','word_internal')],13:[('ス',0,'grey','katakana_fragment')],14:[('病',0,'blue','content_anchor')],15:[('狂',0,'green','word_internal')],16:[('欲',0,'violet','word_internal')],17:[('醜',0,'grey','word_internal')],18:[('ロ',0,'blue','katakana_fragment')],19:[('白',0,'green','word_internal')],20:[('ヴ',1,'grey','katakana_fragment')],21:[('賭',0,'violet','content_anchor')],22:[('閃',0,'pink','content_anchor')],23:[('怠',0,'beige','word_internal')],24:[('騎',0,'grey','repeated_contrast'),('騎',1,'violet','repeated_contrast')],25:[('物語',0,'dark-grey','word_group')],26:[],27:[('結',0,'violet','word_internal')],28:[('誓',0,'blue','content_anchor')],29:[('次',0,'light-grey','content_anchor')],30:[('待',0,'blue','paired_anchor'),('再',0,'pink','paired_anchor')],31:[('子',0,'brown','content_anchor')],32:[('出',0,'grey','word_internal')],33:[('の',0,'yellow','grammatical_bridge')],34:[('ユ',0,'grey','katakana_fragment')],35:[('の',0,'red','grammatical_bridge')],36:[('らぶらぶ',0,'dark-grey','repeated_contrast'),('らぶらぶ',1,'grey','repeated_contrast'),('らぶらぶゆー',0,'light-violet-grey','repeated_contrast')],37:[('獄',0,'grey','word_internal'),('知',0,'orange','content_anchor')],38:[('の',0,'red','grammatical_bridge'),('味',0,'grey-violet','content_anchor')],39:[('女',0,'green','word_internal'),('た',0,'yellow','kana_fragment'),('の',0,'pink','grammatical_bridge'),('茶',0,'violet','content_anchor'),('会',0,'grey','word_internal')],40:[('音',0,'grey-gradient','content_anchor')],41:[('B',0,'blue','latin_fragment')],42:[('オ',0,'grey','katakana_fragment')],43:[('理',0,'grey','word_internal')],44:[('一人',0,'yellow','word_group')],45:[('記',0,'grey-violet','word_internal')],46:[('星',0,'green','content_anchor')],47:[('永久凍土',0,'grey-violet','word_group')],48:[('聖',0,'pink','paired_anchor'),('り',0,'pink','kana_fragment'),('壊',0,'pink','word_internal'),('ま',1,'pink','kana_fragment')],49:[('哮',0,'yellow','word_internal')],50:[('幸',0,'grey-violet','content_anchor')],51:[('血',0,'dark-grey','word_group'),('臓物',0,'dark-grey','word_group')],52:[('選',0,'yellow','content_anchor')],53:[('月',0,'yellow','word_internal'),('鱈',0,'violet','word_internal'),('ス',0,'orange','katakana_fragment')],54:[('劇場型',0,'dark-grey','word_group')],55:[('氷',0,'grey-violet','word_internal'),('の',0,'violet','grammatical_bridge')],56:[('ガー',0,'yellow','katakana_fragment')],57:[('奪還',0,'grey','word_group')],58:[('濁流',0,'grey-blue-texture','uniform')],59:[('騎',0,'violet','word_internal')],60:[('新',0,'grey','paired_anchor'),('英',1,'red','repeated_contrast')],61:[('好',0,'grey-violet','content_anchor')],62:[],63:[('攻略',0,'grey','word_group')],64:[('リ',1,'orange','katakana_fragment')],65:[],66:[('戦',0,'blue','word_internal')],67:[('ヴァン',0,'red','katakana_fragment')],68:[('餐',0,'yellow','word_internal')],69:[('餐',0,'blue','word_internal')],70:[],71:[('君',0,'blue','content_anchor')],72:[('ガー',0,'yellow','katakana_fragment')],73:[],74:[('番',0,'orange','word_internal')],75:[],76:[('棒',0,'red','content_anchor')],77:[('ウ',0,'violet','katakana_fragment')],78:[('コンビニ',0,'grey-violet','word_group')],79:[('オマエハ',0,'grey-violet','word_group'),('ダレダ',0,'dark-grey','word_group')],80:[('殺',0,'grey-violet','paired_anchor'),('癖',0,'grey-violet','paired_anchor')],81:[('残骸',0,'red-texture','uniform')],82:[('Re:',0,'grey-violet','latin_fragment')]
}

def run():
    source=json.loads((ROOT/'references/dataset.json').read_text())['samples'];samples=[]
    for n,s in enumerate(source,1):
        units=[]
        for word,occurrence,color,role in REVIEW[n]:
            start=-1
            for _ in range(occurrence+1):start=s['text'].find(word,start+1)
            if start<0:raise ValueError((n,word,occurrence))
            units.append({'text':word,'start':start,'end':start+len(word),'occurrence':occurrence,'observed_color_label':color,'visual_role':role,'exact_rgb':None,'confidence':'visual_approximate'})
        samples.append({'id':s['id'],'text':s['text'],'background':s['background'],'reviewed':True,'accent_units':units,'no_local_color_observed':not units,'limitations':'Video frame/JPEG, grey versus chromatic is not an exact pixel label; decorations and Chinese subtitles excluded.'})
    role_counts=Counter(u['visual_role'] for s in samples for u in s['accent_units'])
    summary={'sample_count':len(samples),'unit_count':sum(len(s['accent_units']) for s in samples),'role_counts':dict(role_counts),'grammatical_bridge_samples':[s['id'] for s in samples if any(u['visual_role']=='grammatical_bridge' for u in s['accent_units'])],'no_local_color_samples':[s['id'] for s in samples if s['no_local_color_observed']],'method':'manual visual review of all seven contact sheets; occurrence correction; no OCR/VLM in the generation path','not_inferred':['designer intent','hue from word meaning','exact original RGB','font identity']}
    (ROOT/'analysis/color_reference_review.json').write_text(json.dumps({'version':1,'summary':summary,'samples':samples},ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':run()

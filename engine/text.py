from dataclasses import dataclass, asdict
from collections import Counter
import unicodedata
from sudachipy import dictionary, tokenizer

NO_START = set('、。，．・：；？！!?)]｝〕〉》」』】〙〗〟’”ー々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ')
NO_END = set('([{｛〔〈《「『【〘〖〝‘“')
PUNCT = set('、。，．・：；？！!?…‥「」『』（）()[]【】—')

def script(c):
    if '\u4e00' <= c <= '\u9fff' or c in '々〆': return 'kanji'
    if '\u3040' <= c <= '\u309f': return 'hiragana'
    if '\u30a0' <= c <= '\u30ff' or c == 'ー': return 'katakana'
    if c.isdigit(): return 'number'
    if c.isascii() and c.isalpha(): return 'latin'
    if c.isspace(): return 'space'
    return 'punctuation'

@dataclass
class Token:
    text: str
    role: str
    importance: float
    start: int
    pos: str = ''
    visual_role: str = 'secondary'

    def dict(self): return asdict(self)

class JapaneseAnalyzer:
    def __init__(self, config):
        self.tokenizer = dictionary.Dictionary().tokenizer()
        self.config = config

    def analyze(self, text, variant=None):
        if not text or len(text)>80 or any(unicodedata.category(c)=='Cc' and c not in '\n\t' for c in text):
            raise ValueError('文本须为 1–80 字符且不能包含控制字符')
        cfg=self.config['heuristics']; result=[]; index=0
        surfaces=self.tokenizer.tokenize(text, tokenizer.Tokenizer.SplitMode.B)
        counts=Counter(m.surface() for m in surfaces)
        for m in surfaces:
            s=m.surface(); pos=m.part_of_speech()[0]
            role={'名詞':'noun','動詞':'verb','形容詞':'modifier','形状詞':'modifier','副詞':'modifier','助詞':'particle','接続詞':'connector','補助記号':'punctuation','空白':'other'}.get(pos,'other')
            ratio=sum(script(c)=='kanji' for c in s)/max(len(s),1)
            value=cfg['pos'][role]+cfg['kanji_bonus']*ratio+min(len(s),4)*cfg['length_bonus']
            if counts[s]>1 and role not in ('particle','punctuation'):value+=cfg['repeated_bonus']
            if index==0 or index+len(s)==len(text):value+=cfg['edge_bonus']
            active=variant or cfg['variant']
            if active=='kanji_anchor':value+=.12*ratio
            if active=='semantic_nouns':value+=.12 if role=='noun' else -.05*ratio
            if role in ('particle','punctuation'):value=cfg['pos'][role]
            value=max(.02,min(1.,value))
            result.append(Token(s,role,value,index,pos,'primary' if value>=cfg['primary_threshold'] else 'connector' if role in ('particle','connector') else 'secondary'))
            index+=len(s)
        if ''.join(t.text for t in result)!=text:raise ValueError('分词未完整覆盖原文')
        return result

def legal_break(left,right):
    return bool(left and right) and left[-1] not in NO_END and right[0] not in NO_START

def break_penalty(tokens, index):
    if index==len(tokens):return 0.
    right=tokens[index]; left=tokens[index-1]
    if not legal_break(left.text,right.text):return float('inf')
    # Affix/particle must remain attached; punctuation after a clause favors a break.
    if right.role in ('particle','punctuation'):return float('inf')
    if left.text[-1] in '、。？！!?':return 0.
    if left.role in ('connector','particle'):return .1
    return .5

"""Colour anchors are occurrence-specific visual decisions, separate from type size."""
import re
from engine.text import script


def select_accents(tokens, variant, limit, rules, plan=None):
    cfg = rules['accent_selection']
    functional = set(cfg['functional_words'])
    blocked = set(cfg['protected_characters'])
    chars = []
    start = 0
    for i, t in enumerate(tokens):
        for j, c in enumerate(t.text):
            chars.append({'i': i, 'j': j, 'c': c, 'start': start + j, 't': t})
        start += len(t.text)
    if not limit:
        return {}
    text = ''.join(t.text for t in tokens)
    emphasis = set()
    for word in (plan or {}).get('emphasis_relation', []):
        if not word or word in functional or all(c in blocked for c in word):
            continue
        # A repeated spelling is not an instruction to colour every occurrence.
        at = text.find(word)
        if at >= 0:
            emphasis.update(range(at, at + len(word)))
    content = []
    for i, t in enumerate(tokens):
        if t.role in ('particle', 'connector', 'punctuation') or t.text in functional:
            continue
        part = [x for x in chars if x['i'] == i and script(x['c']) not in ('punctuation', 'space') and x['c'] not in blocked]
        if not part:
            continue
        strong = [x for x in part if script(x['c']) in ('kanji', 'katakana', 'latin', 'number')]
        pool = strong or part
        marked = [x for x in pool if x['start'] in emphasis]
        if marked:
            pool = marked
        x = dict(pool[-1] if variant == 1 else pool[0])
        weights = cfg['weights']
        value = weights['importance'] * t.importance
        value += weights['content_role'] if t.role in ('noun', 'keyword', 'concept', 'verb') else 0
        value += weights['display_script'] if strong else 0
        value += weights['planner'] if marked else 0
        value += weights['contrast_concept'] if any(w in t.text for w in cfg['contrast_concepts']) else 0
        value += weights['edge'] if i in (0, len(tokens) - 1) else 0
        x.update(score=value, reason='planner_anchor' if marked else 'content_anchor')
        content.append(x)
    content.sort(key=lambda x: (-x['score'], x['start']))
    selected = []
    # A small red/yellow の is supported in short AのB references, not every clause.
    bridges = [x for x in chars if x['c'] == 'の' and x['t'].text == 'の']
    if variant == 1 and len(text) <= cfg['bridge_max_chars'] and len(bridges) == 1 and len(content) == 2:
        bridge = bridges[0]
        if 0 < bridge['start'] < len(text) - 1:
            selected.append({**bridge, 'score': cfg['bridge_visual_score'], 'reason': 'short_visual_bridge'})
    for x in content:
        if len(selected) >= limit:
            break
        if any(x['t'].text == y['t'].text or abs(x['start'] - y['start']) < cfg['min_anchor_distance'] for y in selected):
            continue
        selected.append(x)
    # Single-token kana/katakana titles can use a second distinct edge in dual mode.
    if len(selected) < limit and len(content) == 1:
        first = selected[0] if selected else content[0]
        part = [x for x in chars if x['i'] == first['i'] and script(x['c']) not in ('punctuation', 'space') and x['c'] not in blocked]
        alternatives = [x for x in part if abs(x['start'] - first['start']) >= cfg['min_anchor_distance']]
        if alternatives:
            selected.append({**alternatives[-1], 'score': first['score'], 'reason': 'word_edge_contrast'})
    return {(x['i'], x['j']): {'rank': rank, 'reason': x['reason'], 'salience': min(1., x['score'])} for rank, x in enumerate(selected[:limit])}


def validate_color_settings(text, custom_colors=None, overrides=None):
    def color(value):
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('颜色须为 #RRGGBB')
        return value.lower()
    custom = None
    if custom_colors is not None:
        if not isinstance(custom_colors, dict) or set(custom_colors) - {'foreground', 'accents'}:
            raise ValueError('自定义配色格式无效')
        custom = {}
        if 'foreground' in custom_colors:
            custom['foreground'] = color(custom_colors['foreground'])
        if 'accents' in custom_colors:
            accents = custom_colors['accents']
            if not isinstance(accents, list) or not 1 <= len(accents) <= 8:
                raise ValueError('自定义强调色须为 1–8 种')
            custom['accents'] = [color(c) for c in accents]
    overrides = overrides or []
    if not isinstance(overrides, list) or len(overrides) > 80:
        raise ValueError('局部颜色数量超限')
    clean = []
    for item in overrides:
        if not isinstance(item, dict) or set(item) != {'start', 'end', 'color'}:
            raise ValueError('局部颜色格式无效')
        a, b = item['start'], item['end']
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text):
            raise ValueError('局部颜色范围须对应排版文本')
        clean.append({'start': a, 'end': b, 'color': color(item['color'])})
    return custom, clean

"""Occurrence-aware visual composition, independent of story or reference IDs.

Glyph heights refer to ink, not em squares. Repacking uses the renderer's
silhouettes; ordering stays fixed even when adjacent bounding boxes interlock.
"""
from collections import Counter
from engine.text import script
from engine.renderer import optical_x, scaled_mask


FUNCTIONAL = {'particle', 'connector', 'punctuation'}


def compose(glyphs, tokens, family, variant, rules, profile, palette, color_mode,
            budget, overrides=(), plan=None):
    cfg = rules.get('composition', {})
    if not cfg.get('enabled'):
        return None
    rows = [[g for g in glyphs if g.row == r] for r in sorted({g.row for g in glyphs})]
    selected = []
    # A line is a set of related blocks, rather than one shared baseline.
    for row in rows:
        content = [g for g in row if g.role not in FUNCTIONAL and
                   script(g.text[0]) in ('kanji', 'katakana', 'number') and
                   g.width / max(g.height, 1) < cfg['elongated_aspect_threshold']]
        can_compose = content and family != 'wide_block' and not any(
            script(g.text[0]) == 'latin' for g in row)
        peak = None
        if content:
            # Three readings of the same words: opening, closing, or a pair.
            token_ids = list(dict.fromkeys(g.token for g in content))
            primary_token = token_ids[-1] if variant == 1 else max(
                token_ids, key=lambda i: (tokens[i].importance, -i))
            block = [g for g in content if g.token == primary_token]
            peak = block[0]
            selected.append(peak)
        if not can_compose:
            continue
        row_height = cfg['peak_ink_height'] * profile['anchor_scale']
        secondary = None
        if variant == 2 and len(content) >= cfg['paired_min_content']:
            secondary = max(content, key=lambda g: abs(g.source_start - peak.source_start))
        token_ids = list(dict.fromkeys(g.token for g in row))
        for g in row:
            kind = script(g.text[0])
            local = g.source_start - tokens[g.token].start
            if g is peak:
                height, role = row_height, 'peak'
            elif g is secondary:
                height, role = row_height * cfg['secondary_peak_ratio'], 'counter_anchor'
            elif kind == 'punctuation':
                height, role = cfg['punctuation_ink_height'], 'punctuation'
            elif kind == 'hiragana':
                height = (cfg['particle_ink_height'] if g.role in FUNCTIONAL else
                          cfg['kana_ink_heights'][local % len(cfg['kana_ink_heights'])])
                height *= profile['kana_scale']
                role = 'bridge' if g.role in FUNCTIONAL else 'floating_kana'
            else:
                height = cfg['body_ink_height'] * cfg['body_height_pattern'][local % len(cfg['body_height_pattern'])]
                role = 'body'
            if g.width / max(g.height, 1) >= cfg['elongated_aspect_threshold']:
                # Long marks retain their em-scale geometry, not the ink
                # height of a square kanji. Otherwise ー becomes a huge bar.
                height = cfg['body_ink_height'] * cfg['elongated_width_ratio'] * g.height / g.width
                role = 'elongated_mark'
            factor = height / g.height
            g.size *= factor; g.width *= factor; g.height = height
            g.composition_role = role
            if role == 'punctuation':
                g.y = row_height - height * cfg['punctuation_baseline_ratio']
            elif kind == 'hiragana':
                phase = (local + variant) % len(cfg['kana_centers'])
                g.y = row_height * cfg['kana_centers'][phase] - height / 2
            elif role == 'elongated_mark':
                g.y = row_height * cfg['elongated_center'] - height / 2
            else:
                # Block-level offsets keep related characters together.
                phase = token_ids.index(g.token) % len(cfg['block_bottom_offsets'])
                bottom = cfg['block_bottom_offsets'][phase] * row_height
                g.y = row_height - height + bottom
        row[0].x = 0
        for a, b in zip(row, row[1:]):
            b.x = optical_x(a, b, cfg['pair_gap'], cfg['pair_min_distance'])
        center = (min(g.x for g in row) + max(g.x + g.width for g in row)) / 2
        fcfg = rules['families'][family]
        pattern = fcfg.get('row_offset_pattern', [0])
        offset = (pattern[row[0].row % len(pattern)] * rules['style']['font_size_base'] *
                  fcfg['offset'] * 3.5 * profile['row_offset_scale'] * profile['row_direction'])
        for g in row:
            g.x += offset - center

    # Tuck a following line into empty ink space. Box overlap is allowed; ink
    # overlap is forbidden here and checked again by the engine after fitting.
    placed = []
    tucks = []
    masks = {}
    for row in rows:
        top = min(g.y for g in row)
        gap = cfg['row_gap'] if placed else 0
        target = max((g.y + g.height for g in placed), default=0) + gap
        shift = target - top
        for g in row:
            g.y += shift
        tuck = 0
        if placed and family != 'wide_block':
            maximum = min(max(g.height for g in row), max(g.height for g in placed)) * cfg['max_row_tuck']
            for step in range(1, cfg['tuck_steps'] + 1):
                delta = maximum * step / cfg['tuck_steps']
                if _rows_touch(placed, row, delta, cfg['row_min_distance'], masks):
                    break
                tuck = delta
            for g in row:
                g.y -= tuck
        tucks.append(tuck); placed.extend(row)

    # Color follows a visual relation. Importance is a weak tie breaker rather
    # than a request to paint every occurrence of the most important word.
    accents = [c for c in dict.fromkeys(palette['accents']) if c != palette['foreground']]
    for g in glyphs:
        g.color = palette['foreground']; g.color_reason = 'base_foreground'; g.color_salience = 0
    decisions = []
    if budget and accents:
        counts = Counter(t.text for t in tokens)
        bridges = [g for g in glyphs if g.text == 'の' and counts['の'] == 1]
        bridge_ids = {id(g) for g in bridges}
        eligible = [g for g in glyphs if g.role not in FUNCTIONAL and
                    not any(c in rules['accent_selection']['protected_characters'] for c in g.text) and
                    script(g.text[0]) != 'punctuation']
        emphasis = set((plan or {}).get('emphasis_relation', []))
        if variant == 1 and len(''.join(t.text for t in tokens)) <= rules['accent_selection']['bridge_max_chars'] and bridges and len(eligible) >= 2:
            pool = bridges + eligible
        else:
            pool = eligible
        max_height = max((g.height for g in glyphs), default=1)
        def key(g):
            planner = any(word in tokens[g.token].text for word in emphasis)
            if id(g) in bridge_ids and variant == 1:
                visual = 1.3
            elif variant == 0:
                # A smaller chromatic counterpoint can balance a white peak.
                visual = 1 - abs(g.height / max_height - cfg['counterpoint_height_ratio'])
            else:
                visual = g.height / max_height
            edge = abs((g.source_start + .5) / max(len(''.join(t.text for t in tokens)), 1) - .5)
            return visual + cfg['color_importance_weight'] * g.importance + cfg['color_edge_weight'] * edge + cfg['planner_color_weight'] * planner
        ranked = sorted(pool, key=lambda g: (-key(g), g.source_start))
        used_tokens = set()
        for g in ranked:
            if len(decisions) >= budget:
                break
            if tokens[g.token].text in used_tokens or any(abs(g.source_start - d.source_start) < rules['accent_selection']['min_anchor_distance'] for d in decisions):
                continue
            g.color = accents[(len(decisions) + variant + profile['accent_rotation']) % len(accents)]
            g.color_reason = ('visual_bridge' if id(g) in bridge_ids else 'visual_counterpoint' if variant == 0 else 'visual_peak')
            g.color_salience = min(1, key(g) / 1.3)
            used_tokens.add(tokens[g.token].text); decisions.append(g)
    for g in glyphs:
        for override in overrides:
            if g.source_start < override['end'] and g.source_end > override['start']:
                g.color = override['color']; g.color_reason = 'manual_override'; g.color_salience = 1
    return {'version': 1, 'strategy': cfg['strategies'][variant],
            'peak_positions': [g.source_start for g in selected], 'row_tucks': tucks,
            'uses_story_context': False}


def _rows_touch(above, below, dy, clearance, masks):
    for a in above:
        for b in below:
            if a.x + a.width + 1 < b.x or b.x + b.width + 1 < a.x:
                continue
            if id(a) not in masks:masks[id(a)] = scaled_mask(a)
            if id(b) not in masks:masks[id(b)] = scaled_mask(b)
            am, bm = masks[id(a)], masks[id(b)]
            ax0, ay0, bx0, by0 = round(a.x), round(a.y), round(b.x), round(b.y-dy)
            x0 = max(ax0, bx0); x1 = min(ax0 + am.shape[1], bx0 + bm.shape[1])
            y0 = max(ay0, by0); y1 = min(ay0 + am.shape[0] + round(clearance), by0 + bm.shape[0])
            if x1 <= x0 or y1 <= y0:
                continue
            # Extend upper ink down by the requested clearance; never confuse
            # a blank bounding-box corner with a collision.
            for shift in range(round(clearance) + 1):
                ay, by = y0 - ay0 - shift, y0 - by0
                ax, bx = x0 - ax0, x0 - bx0
                start = max(-ay, -by, 0); end = min(y1-y0, am.shape[0]-ay, bm.shape[0]-by)
                if end > start and (am[ay+start:ay+end, ax:ax+x1-x0] & bm[by+start:by+end, bx:bx+x1-x0]).any():
                    return True
    return False

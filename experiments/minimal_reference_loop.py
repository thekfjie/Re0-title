"""Sixteen-title reference-transfer experiment; no model API or new renderer.

Run --prepare, --ranker, --benchmark, or --text. The benchmark's ranker and
retrieval bank both exclude the query title. Original geometry is read only by
the annotation builder, corruption experiment and post-generation evaluator.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import html
import json
import math
import random
import shutil
import statistics
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.optimize import minimize
from scipy.special import expit
import yaml

from engine.fonts import FontFace
from engine.layout import LayoutEngine, load_config
from engine.renderer import Layout, PlacedGlyph, Renderer, optical_x, raster_metrics, scaled_mask
from engine.text import JapaneseAnalyzer, NO_START, NO_END, script

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'experiments/minimal-reference-loop'
PARTICLES = {'の', 'と', 'は', 'が', 'を', 'に', 'へ', 'も', 'で', 'から', 'まで'}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))


def digest(data):
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def provenance(data, fonts, cfg, model=None):
    return {'annotation_sha256': digest(data), 'configuration_sha256': digest(cfg),
            'generator_source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
            'fonts': {role: face.metadata for role, face in fonts.items()},
            'model_sha256': digest(model.data) if model else None, 'seed': cfg['seed']}


def settings():
    return yaml.safe_load((ROOT / 'config/minimal_reference_loop.yaml').read_text())


def kind(text):
    types = Counter(script(c) for c in text if not c.isspace())
    if text in PARTICLES:
        return 'particle'
    if types and set(types) == {'punctuation'}:
        return 'punctuation'
    if types and set(types) <= {'hiragana', 'punctuation'}:
        return 'kana'
    if types and set(types) == {'kanji'}:
        return 'kanji'
    if types and set(types) <= {'katakana', 'punctuation'}:
        return 'katakana'
    return 'mixed'


def color_role(color):
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)])
    if rgb.max() - rgb.min() > 38:
        return 'accent'
    return 'base' if rgb.mean() >= 220 else 'muted'


def luminance(color):
    c = np.array([int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    c = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    return float(c @ np.array([.2126, .7152, .0722]))


def core_color(image, box, label):
    x0, y0, x1, y1 = [int(v) for v in box]
    a = np.asarray(image)[y0:y1, x0:x1].astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    spread = a.max(2) - a.min(2)
    label = label.lower()
    if 'blue' in label:
        mask = (b - r > 25) & (b - g > 5)
    elif 'pink' in label:
        mask = (r - g > 30) & (b - g > 12)
    elif 'red' in label:
        mask = (r - g > 40) & (r - b > 40)
    elif 'yellow' in label:
        mask = (r > 160) & (g > 120) & (r - b > 30)
    elif any(s in label for s in ('grey', 'gray', 'violet')):
        mask = (a.min(2) > 30) & (a.max(2) < 230) & (spread < 60)
    else:
        mask = (a.min(2) > 215) & (spread < 35)
    pixels = a[mask]
    fallback = {'white': '#fdfdfd', 'grey-violet': '#867689', 'dark-grey': '#666666'}
    if not len(pixels):
        return fallback.get(label, '#fdfdfd')
    median = np.median(pixels, axis=0).round().astype(int)
    return '#' + ''.join(f'{v:02x}' for v in median)


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def normalize(box, canvas):
    a, b, c, d = canvas
    return [(box[0] - a) / (c - a), (box[1] - b) / (d - b),
            (box[2] - a) / (c - a), (box[3] - b) / (d - b)]


def attach(groups):
    for i, g in enumerate(groups):
        candidates = [(abs(i - j), j) for j, other in enumerate(groups)
                      if other['row'] == g['row'] and other['kind'] in ('kanji', 'katakana', 'mixed')]
        g['attachment'] = min(candidates)[1] if candidates and g['kind'] in ('kana', 'particle', 'punctuation') else None


def prepare_annotations(out):
    cfg = settings()
    sources = {s['id']: s for s in read(ROOT / 'references/dataset.json')['samples']}
    colors = {s['id']: s for s in read(ROOT / 'analysis/color_position_study.json')['cases']}
    manual = read(ROOT / 'references/minimal_annotation_source.json')
    qa = out / 'annotations'
    qa.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(ROOT / 'assets/open-fonts/noto-sans-jp-black.ttf'), 32)
    titles = []
    for src in manual['samples']:
        s = sources[src['id']]
        image = Image.open(ROOT / 'references/originals' / s['file']).convert('RGB')
        canvas = s['measurements']['config']['canvas']
        position = 0
        groups = []
        units = src['units']
        for i, text in enumerate(src['visual_groups']):
            end = position + len(text)
            inside = [u for u in units if position <= u['start'] and u['end'] <= end]
            assert ''.join(u['text'] for u in inside) == text
            assert len({u['row'] for u in inside}) == 1
            box = union([u['bbox'] for u in inside])
            glyphs = []
            for p, char in enumerate(text, position):
                unit = next(u for u in inside if u['start'] <= p < u['end'])
                color_unit = next((u for u in colors[src['id']]['units'] if u['start'] <= p < u['end']), None)
                label = color_unit['observed_color_label'] if color_unit else 'white'
                paint = core_color(image, unit['bbox'], label)
                glyphs.append({'text': char, 'start': p, 'end': p + 1, 'script': script(char),
                               'ink_bbox': normalize(unit['bbox'], canvas) if len(unit['text']) == 1 else None,
                               'bbox_basis': unit['bbox_basis'] if len(unit['text']) == 1 else 'unresolved_within_visual_group',
                               'edge_error_px': unit['edge_error_px'] if len(unit['text']) == 1 else None,
                               'color': paint, 'color_role': color_role(paint), 'observed_color_label': label,
                               'font_size': None, 'font_family': None})
            groups.append({'id': f'g{i:02}', 'text': text, 'start': position, 'end': end,
                           'kind': kind(text), 'row': inside[0]['row'], 'ink_bbox': normalize(box, canvas),
                           'observed_bbox_px': box, 'glyphs': glyphs, 'confidence': 'visually_reviewed',
                           'edge_error_px': max(u['edge_error_px'] for u in inside)})
            position = end
        assert position == len(src['text'])
        attach(groups)
        title = {'id': src['id'], 'text': src['text'], 'groups': groups,
                 'canvas': {'width': cfg['canvas']['width'], 'height': cfg['canvas']['height']},
                 'observed_lines': s['observed_lines'], 'background': '#000000',
                 'source_file': s['file'], 'source_canvas': canvas,
                 'annotation_method': 'manual visual grouping + assigned CV components + corrected touching boundaries',
                 'unknown_glyph_bboxes': sum(g['ink_bbox'] is None for group in groups for g in group['glyphs'])}
        titles.append(title)
        d = ImageDraw.Draw(image)
        for group in groups:
            box = group['observed_bbox_px']
            d.rectangle(box, outline='#34d399', width=4)
            d.text((box[0] + 6, box[1] - 36), group['id'] + ' ' + group['text'], font=font,
                   fill='#fbbf24', stroke_width=2, stroke_fill='black')
        image.crop(canvas).resize((1200, 675)).save(qa / (src['id'] + '.jpg'), quality=95)
    data = {'version': 1, 'schema': 'Title -> Visual Groups -> Glyphs',
            'coordinates': 'normalized XYXY relative to video canvas; half-open original pixel boxes also retained',
            'font_warning': 'ink geometry and approximate visible RGB only; unknown font identity and point sizes',
            'source_sha256': digest(manual), 'titles': titles}
    write(ROOT / 'references/minimal_visual_groups.json', data)
    return data


def pixels(title):
    w, h = title['canvas']['width'], title['canvas']['height']
    return [np.array(g['ink_bbox']) * np.array([w, h, w, h]) for g in title['groups']]


def feature_values(title):
    """Font-independent relational features; no title/string identity or target error."""
    groups = title['groups']
    boxes = pixels(title)
    widths = np.array([max(b[2] - b[0], 1) for b in boxes])
    heights = np.array([max(b[3] - b[1], 1) for b in boxes])
    base = max(float(np.median(heights)), 1)
    body = [h for h, g in zip(heights, groups) if g['kind'] in ('kanji', 'katakana', 'mixed')]
    body_base = max(float(np.median(body)) if body else base, 1)
    connectors = [h / body_base for h, g in zip(heights, groups) if g['kind'] in ('kana', 'particle')]
    punctuation = [h / body_base for h, g in zip(heights, groups) if g['kind'] == 'punctuation']
    b = union(boxes)
    w, h = title['canvas']['width'], title['canvas']['height']
    area = widths * heights
    cx = sum((x[0] + x[2]) / 2 * a for x, a in zip(boxes, area)) / sum(area) / w
    cy = sum((x[1] + x[3]) / 2 * a for x, a in zip(boxes, area)) / sum(area) / h
    rows = sorted({g['row'] for g in groups})
    gaps, offsets, overlaps, row_aspects, row_lengths = [], [], [], [], []
    for row in rows:
        indices = [i for i, g in enumerate(groups) if g['row'] == row]
        rb = union([boxes[i] for i in indices])
        row_aspects.append((rb[2] - rb[0]) / max(rb[3] - rb[1], 1))
        row_lengths.append(rb[2] - rb[0])
        for a, c in zip(indices, indices[1:]):
            gaps.append((boxes[c][0] - boxes[a][2]) / body_base)
            offsets.append(abs((boxes[c][1] + boxes[c][3]) / 2 - (boxes[a][1] + boxes[a][3]) / 2) / body_base)
    for i, a in enumerate(boxes):
        for j, c in enumerate(boxes[i + 1:], i + 1):
            intersection = max(0, min(a[2], c[2]) - max(a[0], c[0])) * max(0, min(a[3], c[3]) - max(a[1], c[1]))
            overlaps.append(intersection / max(min(area[i], area[j]), 1))
    dependencies = []
    for i, g in enumerate(groups):
        parent = g.get('attachment')
        if parent is not None and parent < len(boxes):
            a, c = boxes[parent], boxes[i]
            dx = max(0, a[0] - c[2], c[0] - a[2])
            dy = max(0, a[1] - c[3], c[1] - a[3])
            dependencies.append(math.hypot(dx, dy) / body_base)
    glyphs = [v for g in groups for v in g['glyphs']]
    roles = Counter(color_role(g['color']) for g in glyphs)
    chromatic = [g for g in glyphs if color_role(g['color']) == 'accent']
    low_contrast = [max(0, 1.5 - (luminance(g['color']) + .05) / .05) for g in glyphs]
    colors = {g['color'] for g in glyphs if color_role(g['color']) == 'accent'}
    colored_group_area = sum(a * sum(color_role(v['color']) == 'accent' for v in g['glyphs']) / max(len(g['glyphs']), 1)
                             for g, a in zip(groups, area)) / sum(area)
    color_runs = sum(a['color'] != c['color'] for a, c in zip(glyphs, glyphs[1:])) / max(len(glyphs) - 1, 1)
    pair_heights = [abs(math.log(heights[i + 1] / heights[i])) for i in range(len(groups) - 1)]
    bad_breaks = sum(title['text'][g['start']:g['end']][:1] in NO_START for g in groups
                     if not any(o['row'] == g['row'] and o['start'] < g['start'] for o in groups))
    isolated = sum(all(g['kind'] in ('particle', 'punctuation') for g in groups if g['row'] == row) for row in rows)
    overflow = sum(max(0, -x[0]) + max(0, -x[1]) + max(0, x[2] - w) + max(0, x[3] - h) for x in boxes) / body_base
    def avg(a): return float(np.mean(a)) if len(a) else 0.
    def mx(a): return float(max(a)) if len(a) else 0.
    logratio = np.log(heights / body_base)
    features = {
        'center_distance_sq': (cx - .5) ** 2 + (cy - .5) ** 2,
        'box_fill': (b[2] - b[0]) * (b[3] - b[1]) / (w * h),
        'aspect_per_character': math.log(max((b[2] - b[0]) / max(b[3] - b[1], 1) * len(rows) / max(len(glyphs), 1), .01)),
        'height_log_mean': avg(logratio), 'height_log_std': float(np.std(logratio)),
        'height_log_min': float(logratio.min()), 'height_log_max': float(logratio.max()),
        'height_ratio_pair_mean': avg(pair_heights), 'height_ratio_pair_max': mx(pair_heights),
        'connector_height_mean': avg(connectors), 'connector_height_max': mx(connectors),
        'connector_over_body': avg([max(0, v - 1) for v in connectors]),
        'punctuation_height': avg(punctuation),
        'gap_mean': avg(gaps), 'gap_std': float(np.std(gaps)) if gaps else 0,
        'gap_large': avg([max(0, v - .25) for v in gaps]),
        'gap_deep_overlap': avg([max(0, -v - .20) for v in gaps]),
        'vertical_pair_mean': avg(offsets), 'vertical_pair_max': mx(offsets),
        'dependency_gap_mean': avg(dependencies), 'dependency_gap_max': mx(dependencies),
        'bbox_overlap_mean': avg(overlaps), 'bbox_overlap_max': mx(overlaps),
        'row_width_cv': float(np.std(row_lengths) / max(np.mean(row_lengths), 1)),
        'row_aspect_mean': avg([math.log(max(v, .01)) for v in row_aspects]),
        'accent_fraction': len(chromatic) / max(len(glyphs), 1),
        'accent_area_fraction': colored_group_area,
        'accent_palette_count': len(colors), 'color_transition_fraction': color_runs,
        'muted_fraction': roles['muted'] / max(len(glyphs), 1),
        'accent_height_mean': avg([heights[i] / body_base for i, g in enumerate(groups)
                                   if any(color_role(v['color']) == 'accent' for v in g['glyphs'])]),
        'white_peak_fraction': sum(a for g, a, gh in zip(groups, area, heights)
                                  if gh >= body_base and any(color_role(v['color']) == 'base' for v in g['glyphs'])) / sum(area),
        'low_contrast': avg(low_contrast), 'overflow': overflow,
        'kinsoku': float(bad_breaks), 'isolated_function_line': float(isolated),
    }
    return features


def corrupt(original, corruption, ordinal, cfg, rng):
    t = deepcopy(original)
    gs = t['groups']
    mag = cfg['negatives']['magnitudes'][ordinal % len(cfg['negatives']['magnitudes'])]
    indices = list(range(len(gs)))
    selected = rng.choice(indices)
    b = gs[selected]['ink_bbox']
    def scale(i, sx=1., sy=1.):
        g = gs[i]; a = g['ink_bbox']; cx = (a[0] + a[2]) / 2; cy = (a[1] + a[3]) / 2
        transform(g, sx, sy, cx * (1 - sx), cy * (1 - sy))
    if corruption == 'size':
        scale(selected, math.exp(mag * (-1 if ordinal % 2 else 1)), math.exp(mag * (-1 if ordinal % 2 else 1)))
    elif corruption == 'position':
        transform(gs[selected], 1, 1, rng.uniform(-mag, mag) * (b[2] - b[0]), rng.uniform(-mag, mag) * (b[3] - b[1]))
    elif corruption == 'connector_up':
        candidates = [i for i, g in enumerate(gs) if g['kind'] in ('kana', 'particle', 'punctuation')]
        scale(rng.choice(candidates or indices), 1 + mag * 2, 1 + mag * 2)
    elif corruption == 'anchor_down':
        candidates = [i for i, g in enumerate(gs) if g['kind'] in ('kanji', 'katakana', 'mixed')]
        target = max(candidates or indices, key=lambda i: gs[i]['ink_bbox'][3] - gs[i]['ink_bbox'][1])
        scale(target, math.exp(-mag * 1.5), math.exp(-mag * 1.5))
    elif corruption == 'color':
        palette = ['#00ff80', '#ff00ff', '#ffcc00', '#00ffff', '#ff4000', '#80ff00']
        glyphs = [v for g in gs for v in g['glyphs']]
        if ordinal % 5 == 0:
            chosen = rng.choice(glyphs); chosen['color'] = '#080808'
        elif ordinal % 5 == 1:
            for i, g in enumerate(glyphs): g['color'] = palette[i % len(palette)]
        elif ordinal % 5 == 2:
            for g in glyphs: g['color'] = palette[ordinal % len(palette)]
        elif ordinal % 5 == 3:
            for i, g in enumerate(glyphs): g['color'] = palette[(i + ordinal) % len(palette)] if i % 2 else '#080808'
        else:
            for g in gs:
                if g['kind'] in ('kana', 'particle'):
                    for v in g['glyphs']: v['color'] = palette[ordinal % len(palette)]
            if not any(g['kind'] in ('kana', 'particle') for g in gs):
                for i, v in enumerate(glyphs): v['color'] = palette[i % len(palette)]
    elif corruption == 'spacing':
        shift = mag * (-1 if ordinal % 2 else 1) * (b[2] - b[0])
        for g in gs:
            if g['row'] == gs[selected]['row'] and g['start'] > gs[selected]['start']:
                transform(g, 1, 1, shift, 0)
        if selected == len(gs) - 1: transform(gs[selected], 1, 1, shift, 0)
    elif corruption == 'line_break':
        index = rng.randrange(1, len(gs)) if len(gs) > 1 else 0
        previous_row = gs[index]['row']
        for i, g in enumerate(gs):
            if i >= index and g['row'] == previous_row:
                g['row'] += 1
                transform(g, 1, 1, -.12, .12 + mag * .1)
            elif i > index and g['row'] > previous_row:
                g['row'] += 1
    else:
        sx = math.exp(mag * (-1 if ordinal % 2 else 1)); sy = 1 / sx
        for g in gs: transform(g, sx, sy, .5 * (1 - sx), .5 * (1 - sy))
    t['corruption'] = {'type': corruption, 'ordinal': ordinal, 'magnitude': mag}
    return t


def transform(g, sx, sy, dx, dy):
    for obj in [g] + g['glyphs']:
        b = obj.get('ink_bbox')
        if b is not None:
            obj['ink_bbox'] = [b[0] * sx + dx, b[1] * sy + dy, b[2] * sx + dx, b[3] * sy + dy]


class Ranker:
    def __init__(self, data):
        self.data = data

    def vector(self, title):
        f = feature_values(title)
        raw = np.array([f[k] for k in self.data['features']], dtype=float)
        z = np.clip((raw - self.data['mean']) / self.data['scale'], -8, 8)
        return np.r_[z, z * z]

    def energy(self, title):
        return float(self.vector(title) @ np.array(self.data['weights']))

    @classmethod
    def fit(cls, pairs, cfg, excluded, cache=None):
        names = list(feature_values(pairs[0][0]))
        def vector(title):
            if cache is not None and id(title) in cache: return cache[id(title)]
            f = feature_values(title)
            return [f[k] for k in names]
        positives = np.array([vector(p[0]) for p in pairs])
        negatives = np.array([vector(p[1]) for p in pairs])
        full = np.vstack([positives, negatives])
        mu = full.mean(0); std = full.std(0); std[std < 1e-6] = 1
        def expand(x):
            z = np.clip((x - mu) / std, -8, 8)
            return np.c_[z, z * z]
        delta = expand(positives) - expand(negatives)
        regularization = cfg['ranker']['l2']
        def objective(weights):
            logits = delta @ weights
            loss = float(np.logaddexp(0, -logits).mean() + regularization * (weights @ weights) / 2)
            grad = -(delta.T @ expit(-logits)) / len(delta) + regularization * weights
            return loss, grad
        result = minimize(objective, np.zeros(delta.shape[1]), jac=True, method='L-BFGS-B',
                          options={'maxiter': cfg['ranker']['max_iterations']})
        if not result.success: raise RuntimeError('ranker fit did not converge: ' + result.message)
        return cls({'version': 1, 'algorithm': 'regularized_pairwise_logistic',
                    'features': names, 'expansion': 'z + z squared; train-only normalization',
                    'mean': mu.tolist(), 'scale': std.tolist(), 'weights': result.x.tolist(),
                    'training_titles': sorted({p[0]['id'] for p in pairs}), 'excluded_titles': sorted(excluded),
                    'training_pair_count': len(pairs), 'l2': regularization,
                    'loss': float(result.fun), 'iterations': int(result.nit)})


def get_fonts(args=None):
    cfg = settings()
    return {role: FontFace(Path(getattr(args, role, None) or ROOT / 'assets/open-fonts' / filename))
            for role, filename in cfg['fonts'].items()}


def shape_group(group, fonts):
    runs = []
    for c in group['text']:
        face = 'kana' if script(c) == 'hiragana' else 'kanji'
        if runs and runs[-1][0] == face: runs[-1] = (face, runs[-1][1] + c, runs[-1][2])
        else: runs.append((face, c, sum(len(r[1]) for r in runs)))
    shaped = []
    for key, text, start in runs:
        face = fonts[key]
        missing = face.missing(text)
        if missing: raise ValueError('字体缺字：' + ''.join(missing))
        for sh in face.shape(text): shaped.append((key, face, sh, start + sh.cluster))
    return shaped


def redraw(title, fonts):
    """Replay measured group geometry with the same outline Renderer as legacy.

    Known glyph boxes remain measured. Unresolved kana use font shaping inside
    the measured group; that inferred replay never overwrites annotations.
    """
    width, height = title['canvas']['width'], title['canvas']['height']
    glyphs = []
    for i, group in enumerate(title['groups']):
        box = np.array(group['ink_bbox']) * [width, height, width, height]
        entries = shape_group(group, fonts)
        natural = []; previous = None
        for key, face, sh, offset in entries:
            x0, y0, x1, y1 = sh.bounds
            if x1 <= x0 or y1 <= y0: continue
            size = 100.
            g = PlacedGlyph(sh.text, i, group['kind'], .5, key, sh.gid, sh.path, sh.bounds, face.upem,
                            0., 100. - y1 * size / face.upem, (x1 - x0) * size / face.upem,
                            (y1 - y0) * size / face.upem, size, 1., 1., '#ffffff', group['row'],
                            sh.advance, sh.bearing, face.metrics['ascender'], face.metrics['descender'], mask=sh.mask)
            g.source_start = group['start'] + offset; g.source_end = g.source_start + len(sh.text)
            g.x = optical_x(previous, g, 1.5, 1.5) if previous else 0.
            natural.append(g); previous = g
        if not natural: continue
        nb = [min(g.x for g in natural), min(g.y for g in natural),
              max(g.x + g.width for g in natural), max(g.y + g.height for g in natural)]
        sx, sy = (box[2] - box[0]) / max(nb[2] - nb[0], 1), (box[3] - box[1]) / max(nb[3] - nb[1], 1)
        for g in natural:
            observed = next(v for v in group['glyphs'] if v['start'] <= g.source_start < v['end'])
            if observed.get('ink_bbox') is not None and g.source_end - g.source_start == 1:
                target = np.array(observed['ink_bbox']) * [width, height, width, height]
                x0, y0, x1, y1 = g.bounds
                new_size = (target[3] - target[1]) * g.upem / (y1 - y0)
                g.x, g.y = float(target[0]), float(target[1]); g.width, g.height = float(target[2] - target[0]), float(target[3] - target[1])
                g.size = new_size; g.scale_x = g.width / ((x1 - x0) * new_size / g.upem)
            else:
                g.x = box[0] + (g.x - nb[0]) * sx; g.y = box[1] + (g.y - nb[1]) * sy
                g.width *= sx; g.height *= sy; g.size *= sy; g.scale_x *= sx / sy
            g.color = observed['color']; g.color_reason = 'reference_visual_slot'
            g.composition_role = group['id']; glyphs.append(g)
    return Layout(title['text'], 'reference_transfer', glyphs, width, height, title['background'], 42,
                  lines=[''.join(g['text'] for g in title['groups'] if g['row'] == row) for row in sorted({g['row'] for g in title['groups']})],
                  metadata={'groups': deepcopy(title['groups']), 'annotation_replay': True})


def hard_check(layout, cfg):
    gs = layout.glyphs
    if not gs: return {'valid': False, 'reason': 'empty'}
    metrics = raster_metrics(layout, cfg['search']['mask_resolution'])
    overflow = any(g.x < -.01 or g.y < -.01 or g.x + g.width > layout.width + .01 or g.y + g.height > layout.height + .01 for g in gs)
    mx, my = layout.width * cfg['canvas']['margin'], layout.height * cfg['canvas']['margin']
    safe_margin = layout.metadata.get('annotation_replay', False) or all(
        g.x >= mx - .01 and g.y >= my - .01 and g.x + g.width <= layout.width - mx + .01
        and g.y + g.height <= layout.height - my + .01 for g in gs)
    kinsoku = any(line and (line[0] in NO_START or line[-1] in NO_END) for line in layout.lines)
    integrity = ''.join(layout.lines) == layout.text and ''.join(g.text for g in gs) == ''.join(c for c in layout.text if not c.isspace())
    readable = all((luminance(g.color) + .05) / .05 >= cfg['search']['min_visible_contrast'] for g in gs)
    valid = integrity and readable and safe_margin and not overflow and not kinsoku and metrics['collision'] <= cfg['search']['max_ink_overlap']
    return {'valid': bool(valid), 'integrity': bool(integrity), 'readable': bool(readable), 'safe_margin': bool(safe_margin),
            'overflow': bool(overflow), 'kinsoku': bool(kinsoku), **metrics}


def train_rankers(data, fonts, out):
    cfg = settings(); titles = data['titles']; all_pairs = []; manifest = []; records = []
    for title in titles:
        for category in cfg['negatives']['types']:
            for ordinal in range(cfg['negatives']['per_type']):
                seed = cfg['seed'] + int(title['id'][1:]) * 1000 + cfg['negatives']['types'].index(category) * 20 + ordinal
                negative = corrupt(title, category, ordinal, cfg, random.Random(seed))
                check = hard_check(redraw(negative, fonts), cfg)
                all_pairs.append((title, negative))
                manifest.append({'title': title['id'], 'type': category, 'ordinal': ordinal, 'seed': seed,
                                 'legal_ink_constraints': check['valid'], 'hard_check': check,
                                 'positive_id': title['id'], 'negative': negative})
    write(out / 'negatives.json', {'annotation_sha256': digest(data), 'seed': cfg['seed'], 'pairs': manifest})
    names = list(feature_values(titles[0]))
    cache = {}
    for pair in all_pairs:
        for t in pair:
            if id(t) not in cache:
                f = feature_values(t); cache[id(t)] = [f[k] for k in names]
    folds = out / 'ranker-folds'; folds.mkdir(parents=True, exist_ok=True)
    for title in titles:
        training = [p for p in all_pairs if p[0]['id'] != title['id']]
        model = Ranker.fit(training, cfg, [title['id']], cache)
        write(folds / (title['id'] + '.json'), model.data)
        for pair, item in zip(all_pairs, manifest):
            if pair[0]['id'] != title['id']: continue
            delta = model.energy(pair[0]) - model.energy(pair[1])
            records.append({'title': title['id'], 'type': item['type'], 'ordinal': item['ordinal'],
                            'legal': item['legal_ink_constraints'], 'difference': delta,
                            'probability_original': float(expit(delta)), 'correct': delta > 0})
    def accuracy(items): return statistics.mean(r['correct'] for r in items) if items else None
    per_title = {t['id']: accuracy([r for r in records if r['title'] == t['id']]) for t in titles}
    per_type = {c: accuracy([r for r in records if r['type'] == c]) for c in cfg['negatives']['types']}
    legal = [r for r in records if r['legal']]
    rng = np.random.default_rng(cfg['seed']); a = np.array(list(per_title.values()))
    bootstrap = rng.choice(a, size=(cfg['ranker']['bootstrap_samples'], len(a)), replace=True).mean(1)
    ci = np.quantile(bootstrap, [.025, .975]).tolist()
    passed = statistics.mean(per_title.values()) >= cfg['ranker']['gate_accuracy'] and bool(legal) and accuracy(legal) >= cfg['ranker']['gate_legal_accuracy'] and min(per_type.values()) >= cfg['ranker']['gate_type_accuracy'] and ci[0] > .5
    report = {'protocol': 'leave-one-title-out; all corruptions of query excluded; train-only normalization',
              'title_count': len(titles), 'pair_count': len(records), 'macro_accuracy': statistics.mean(per_title.values()),
              'legal_pair_count': len(legal), 'legal_accuracy': accuracy(legal), 'per_type': per_type,
              'per_type_legal': {c: accuracy([r for r in legal if r['type'] == c]) for c in per_type},
              'per_title': per_title, 'title_bootstrap_95ci': ci, 'gate_passed': passed,
              'thresholds': {k: v for k, v in cfg['ranker'].items() if k.startswith('gate')}, 'records': records}
    write(out / 'ranker-evaluation.json', report)
    full = Ranker.fit(all_pairs, cfg, [], cache)
    full.data.update(annotation_sha256=digest(data), configuration_sha256=digest(cfg), evaluation_gate_passed=passed)
    write(out / 'ranker.json', full.data)
    print(json.dumps({k: v for k, v in report.items() if k not in ('records', 'per_title')}, ensure_ascii=False, indent=2), flush=True)
    return report


def groupings(text, analyzer, cfg):
    tokens = analyzer.analyze(text)
    outputs = []
    for variant in range(cfg['retrieval']['mapping_variants']):
        raw = []
        for token in tokens:
            cursor = token.start
            runs = []
            for c in token.text:
                k = script(c)
                if runs and runs[-1][0] == k: runs[-1] = (k, runs[-1][1] + c)
                else: runs.append((k, c))
            for k, run in runs:
                if k in ('kanji', 'katakana') and len(run) > 1 and variant in (1, 3):
                    pieces = list(run) if variant == 1 else [run[:-1], run[-1]]
                else: pieces = [run]
                for piece in pieces:
                    raw.append({'text': piece, 'start': cursor, 'end': cursor + len(piece), 'kind': kind(piece), 'pos': token.pos})
                    cursor += len(piece)
        combined = []
        for g in raw:
            if combined and (g['kind'] == 'punctuation' and g['text'][0] in NO_START or
                             variant in (0, 2) and g['kind'] in ('kana', 'particle') and combined[-1]['kind'] == 'kana'):
                combined[-1]['text'] += g['text']; combined[-1]['end'] = g['end']; combined[-1]['kind'] = kind(combined[-1]['text'])
            else: combined.append(g)
        for i, g in enumerate(combined): g['id'] = f'g{i:02}'; g['row'] = 0
        attach(combined)
        assert ''.join(g['text'] for g in combined) == text
        outputs.append({'id': 'query', 'text': text, 'groups': combined,
                        'canvas': {'width': cfg['canvas']['width'], 'height': cfg['canvas']['height']}, 'variant': variant})
    return outputs


def sequence_distance(a, b):
    n, m = len(a), len(b)
    table = np.zeros((n + 1, m + 1)); table[:, 0] = np.arange(n + 1); table[0, :] = np.arange(m + 1)
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            mismatch = 0 if x == y else .25 if {x, y} <= {'kana', 'particle', 'punctuation'} or {x, y} <= {'kanji', 'mixed'} else .5 if {x, y} <= {'kanji', 'katakana'} else 1.
            table[i, j] = min(table[i - 1, j] + 1, table[i, j - 1] + 1, table[i - 1, j - 1] + mismatch)
    return float(table[n, m] / max(n, m, 1))


def structural_descriptor(title):
    text = title['text']; groups = title['groups']; counts = Counter(script(c) for c in text)
    repeats = Counter(g['text'] for g in groups)
    return {'sequence': [g['kind'] for g in groups], 'count': len(groups),
            'scripts': [counts[k] / max(len(text), 1) for k in ('kanji', 'hiragana', 'katakana', 'latin', 'number')],
            'repetition': sum(v - 1 for v in repeats.values()) / max(len(groups), 1),
            'punctuation': counts['punctuation'] / max(len(text), 1)}


def retrieval_distance(query, reference, cfg):
    a, b = structural_descriptor(query), structural_descriptor(reference)
    ratio = abs(math.log(a['count'] / b['count']))
    components = {'sequence': sequence_distance(a['sequence'], b['sequence']), 'count': ratio / (1 + ratio),
                  'scripts': sum(abs(x - y) for x, y in zip(a['scripts'], b['scripts'])) / 2,
                  'repetition': abs(a['repetition'] - b['repetition']), 'punctuation': abs(a['punctuation'] - b['punctuation'])}
    return sum(cfg['retrieval']['weights'][k] * v for k, v in components.items())


def align_groups(query, reference):
    q, r = query['groups'], reference['groups']; n, m = len(q), len(r)
    table = {(0, 0): (0., [])}
    for i in range(n + 1):
        for j in range(m + 1):
            state = table.get((i, j))
            if state is None: continue
            for nq, nr in ((1, 1), (1, 2), (2, 1), (1, 3), (3, 1)):
                if i + nq > n or j + nr > m: continue
                qr, rr = q[i:i + nq], r[j:j + nr]
                if len({g['row'] for g in rr}) > 1: continue
                cost = sequence_distance([g['kind'] for g in qr], [g['kind'] for g in rr])
                cost += .12 * abs(math.log(sum(len(g['text']) for g in qr) / sum(len(g['text']) for g in rr)))
                cost += .10 * (nq + nr - 2)
                new = (state[0] + cost, state[1] + [(list(range(i, i + nq)), list(range(j, j + nr)))])
                key = (i + nq, j + nr)
                if key not in table or new[0] < table[key][0]: table[key] = new
    return table.get((n, m))


def source_slots(query, reference, alignment, fonts):
    """Monotonic mapping with proportional subdivision using real glyph widths."""
    mapped = []
    for qids, rids in alignment:
        sources = [reference['groups'][i] for i in rids]
        source_box = union([g['ink_bbox'] for g in sources])
        source_glyphs = [v for g in sources for v in g['glyphs']]
        accent_owners = {}
        for si, source in enumerate(source_glyphs):
            if color_role(source['color']) != 'accent': continue
            nominal = min(len(qids) - 1, int((si + .5) / len(source_glyphs) * len(qids)))
            compatible = [k for k, qi in enumerate(qids) if any(script(c) == source['script'] for c in query['groups'][qi]['text'])]
            accent_owners[source['start']] = min(compatible or list(range(len(qids))), key=lambda k: abs(k - nominal))
        widths = []
        for qi in qids:
            g = query['groups'][qi]
            widths.append(sum(max(sh.bounds[2] - sh.bounds[0], sh.advance * .7) / f.upem for _, f, sh, _ in shape_group(g, fonts)))
        cursor = source_box[0]
        total_width = sum(widths)
        for k, qi in enumerate(qids):
            frac = widths[k] / max(total_width, .01)
            box = [cursor, source_box[1], cursor + (source_box[2] - source_box[0]) * frac, source_box[3]]
            cursor = box[2]
            begin = round(k * len(source_glyphs) / len(qids)); end = max(begin + 1, round((k + 1) * len(source_glyphs) / len(qids)))
            subset = deepcopy(source_glyphs[begin:end] or source_glyphs[-1:])
            # Geometry can be shared when a source group is split. A local
            # color occurrence has exactly one owner, never one copy per child.
            for source in subset:
                if color_role(source['color']) == 'accent' and accent_owners.get(source['start']) != k:
                    source['color'] = '#fdfdfd'
            for source in source_glyphs:
                if accent_owners.get(source['start']) == k and not any(v['start'] == source['start'] for v in subset):
                    subset.append(deepcopy(source))
            mapped.append({**deepcopy(query['groups'][qi]), 'row': sources[0]['row'], 'ink_bbox': box,
                           'source_box': source_box, 'source_glyphs': deepcopy(subset),
                           'reference_groups': [g['id'] for g in sources]})
    mapped.sort(key=lambda g: g['start'])
    return mapped


def adapt_group(group, fonts, width, height, cfg):
    box = np.array(group['ink_bbox']) * [width, height, width, height]
    sb = np.array(group['source_box']) * [width, height, width, height]
    target_h = box[3] - box[1]; source_h = max(sb[3] - sb[1], 1)
    source_glyphs = group['source_glyphs']
    entries = shape_group(group, fonts)
    natural_top = max((sh.bounds[3] / face.upem for _, face, sh, _ in entries), default=1.)
    natural_bottom = min((sh.bounds[1] / face.upem for _, face, sh, _ in entries), default=0.)
    natural_extent = max(natural_top - natural_bottom, .01)
    natural = []
    for ordinal, (key, face, sh, offset) in enumerate(entries):
        x0, y0, x1, y1 = sh.bounds
        if x1 <= x0 or y1 <= y0: continue
        matches = [g for g in source_glyphs if g['script'] == script(sh.text[0])]
        choices = matches or source_glyphs
        chosen = choices[min(len(choices) - 1, int(ordinal / max(len(entries), 1) * len(choices)))]
        known = chosen.get('ink_bbox')
        if known is not None:
            gb = np.array(known) * [width, height, width, height]
            ratio = (gb[3] - gb[1]) / source_h; relative_y = (gb[1] - sb[1]) / source_h
        else:
            # Unknown original glyph boxes stay unknown. Use one shaped-run
            # font scale instead of making every kana's ink equally tall.
            ratio = ((y1 - y0) / face.upem) / natural_extent
            relative_y = (natural_top - y1 / face.upem) / natural_extent
        if script(sh.text[0]) == 'punctuation' and chosen['script'] != 'punctuation':
            ratio = load_config()['rules']['style']['punctuation_size']; relative_y = 1 - ratio
        desired = max(target_h * ratio, 1)
        size = desired * face.upem / (y1 - y0)
        g = PlacedGlyph(sh.text, 0, group['kind'], .5, key, sh.gid, sh.path, sh.bounds, face.upem,
                        0., box[1] + target_h * relative_y, (x1 - x0) * size / face.upem, desired,
                        size, 1., 1., '#fdfdfd', group['row'], sh.advance, sh.bearing,
                        face.metrics['ascender'], face.metrics['descender'], mask=sh.mask)
        g.source_start = group['start'] + offset; g.source_end = g.source_start + len(sh.text)
        g.composition_role = group['id']; g.color_reason = 'reference_visual_slot'
        if color_role(chosen['color']) == 'muted': g.color = chosen['color']
        previous = natural[-1] if natural else None
        g.x = optical_x(previous, g, cfg['retrieval']['desired_gap'], cfg['retrieval']['desired_gap']) if previous else 0.
        natural.append(g)
    if not natural: return []
    total_width = max(g.x + g.width for g in natural) - min(g.x for g in natural)
    sx = np.clip((box[2] - box[0]) / max(total_width, 1), cfg['retrieval']['min_scale_x'], cfg['retrieval']['max_scale_x'])
    for g in natural: g.x = box[0] + g.x * sx; g.width *= sx; g.scale_x *= sx
    # Local chromatic slots are mapped once; expanding a word never colors every
    # repeated occurrence through a global string replacement.
    accents = [g for g in source_glyphs if color_role(g['color']) == 'accent']
    used = set()
    for a in accents:
        source_index = source_glyphs.index(a); fraction = source_index / max(len(source_glyphs) - 1, 1)
        candidates = [i for i, g in enumerate(natural) if script(g.text[0]) == a['script'] and i not in used]
        if not candidates: candidates = [i for i in range(len(natural)) if i not in used]
        if candidates:
            selected = min(candidates, key=lambda i: abs(i / max(len(natural) - 1, 1) - fraction))
            natural[selected].color = a['color']; used.add(selected)
    return natural


def layout_title(layout):
    groups = deepcopy(layout.metadata['groups'])
    for i, group in enumerate(groups):
        gs = [g for g in layout.glyphs if g.token == i]
        if not gs: raise ValueError('lost visual group')
        group['row'] = gs[0].row
        group['ink_bbox'] = [min(g.x for g in gs) / layout.width, min(g.y for g in gs) / layout.height,
                             max(g.x + g.width for g in gs) / layout.width, max(g.y + g.height for g in gs) / layout.height]
        group['glyphs'] = [{'text': g.text, 'start': g.source_start, 'end': g.source_end,
                             'script': script(g.text[0]), 'color': g.color, 'color_role': color_role(g.color),
                             'ink_bbox': [g.x / layout.width, g.y / layout.height,
                                          (g.x + g.width) / layout.width, (g.y + g.height) / layout.height]} for g in gs]
        for key in ('source_glyphs', 'source_box'): group.pop(key, None)
    return {'id': 'generated', 'text': layout.text, 'groups': groups,
            'canvas': {'width': layout.width, 'height': layout.height}, 'background': layout.background}


def move_group(layout, index, dx=0., dy=0., scale=1., sx=1.):
    gs = [g for g in layout.glyphs if g.token == index]
    if not gs: return
    b = [min(g.x for g in gs), min(g.y for g in gs), max(g.x + g.width for g in gs), max(g.y + g.height for g in gs)]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    for g in gs:
        g.x = cx + (g.x - cx) * scale * sx + dx; g.y = cy + (g.y - cy) * scale + dy
        g.width *= scale * sx; g.height *= scale; g.size *= scale; g.scale_x *= sx


def fit_canvas(layout, cfg, enlargement=1.):
    gs = layout.glyphs
    x0, y0 = min(g.x for g in gs), min(g.y for g in gs)
    x1, y1 = max(g.x + g.width for g in gs), max(g.y + g.height for g in gs)
    margin = cfg['canvas']['margin']; w, h = layout.width, layout.height
    scale = min(enlargement, w * (1 - 2 * margin) / max(x1 - x0, 1), h * (1 - 2 * margin) / max(y1 - y0, 1))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for g in gs:
        g.x = w / 2 + (g.x - cx) * scale; g.y = h / 2 + (g.y - cy) * scale
        g.width *= scale; g.height *= scale; g.size *= scale
    return layout


def pair_overlap(a, b, factor=.2):
    am, bm = scaled_mask(a, factor), scaled_mask(b, factor)
    ax, ay, bx, by = round(a.x * factor), round(a.y * factor), round(b.x * factor), round(b.y * factor)
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + am.shape[1], bx + bm.shape[1]), min(ay + am.shape[0], by + bm.shape[0])
    if x1 <= x0 or y1 <= y0: return 0
    return int(np.sum(am[y0 - ay:y1 - ay, x0 - ax:x1 - ax] & bm[y0 - by:y1 - by, x0 - bx:x1 - bx]))


def repair_layout(layout, cfg):
    # Repack adjacent glyphs using actual masks; rows preserve reference offsets.
    for row in sorted({g.row for g in layout.glyphs}):
        gs = [g for g in layout.glyphs if g.row == row]
        for previous, g in zip(gs, gs[1:]):
            if pair_overlap(previous, g):
                required = optical_x(previous, g, cfg['retrieval']['desired_gap'], cfg['retrieval']['desired_gap'])
                if required > g.x:
                    delta = required - g.x
                    for other in gs:
                        if other.source_start >= g.source_start: other.x += delta
    rows = sorted({g.row for g in layout.glyphs})
    for row in rows[1:]:
        current = [g for g in layout.glyphs if g.row == row]
        earlier = [g for g in layout.glyphs if g.row < row]
        for _ in range(32):
            if not any(pair_overlap(a, b) for a in earlier for b in current): break
            for g in layout.glyphs:
                if g.row >= row: g.y += cfg['retrieval']['desired_gap']
    return fit_canvas(layout, cfg)


def transfer_layout(query, reference, fonts, cfg, variant, distance):
    aligned = align_groups(query, reference)
    if aligned is None: return None
    groups = source_slots(query, reference, aligned[1], fonts)
    width, height = query['canvas']['width'], query['canvas']['height']
    glyphs = []
    for i, group in enumerate(groups):
        gs = adapt_group(group, fonts, width, height, cfg)
        for g in gs: g.token = i
        glyphs.extend(gs)
    if not glyphs: return None
    # Repack groups, preserving optical overlap and proportional reference gaps.
    for row in sorted({g['row'] for g in groups}):
        indices = [i for i, g in enumerate(groups) if g['row'] == row]
        for previous_i, index in zip(indices, indices[1:]):
            before = [g for g in glyphs if g.token == previous_i]; current = [g for g in glyphs if g.token == index]
            rb, cb = groups[previous_i]['ink_bbox'], groups[index]['ink_bbox']
            reference_gap = (cb[0] - rb[2]) * width
            desired = max(g.x + g.width for g in before) + reference_gap
            ink_safe = optical_x(before[-1], current[0], cfg['retrieval']['desired_gap'], cfg['retrieval']['desired_gap'])
            shift = max(desired, ink_safe) - min(g.x for g in current)
            for g in current: g.x += shift
    attach(groups)
    layout = Layout(query['text'], 'reference_transfer', glyphs, width, height, '#000000', cfg['seed'],
                    lines=[''.join(g['text'] for g in groups if g['row'] == row) for row in sorted({g['row'] for g in groups})],
                    metadata={'groups': groups, 'reference_id': reference['id'], 'retrieval_distance': distance,
                              'mapping_cost': aligned[0], 'grouping_variant': variant, 'mapping': aligned[1],
                              'initial_id': reference['id'] + '-' + str(variant), 'annotation_replay': False})
    fit_canvas(layout, cfg, cfg['retrieval']['resize_variant'][variant])
    repair_layout(layout, cfg)
    return layout if hard_check(layout, cfg)['valid'] else None


def candidate_pool(text, bank, fonts, analyzer, cfg):
    queries = groupings(text, analyzer, cfg)
    ranking = sorted(((min(retrieval_distance(q, ref, cfg) for q in queries), ref) for ref in bank),
                     key=lambda pair: (pair[0], pair[1]['id']))[:cfg['retrieval']['top_k']]
    pool = []
    for distance, reference in ranking:
        for variant, query in enumerate(queries):
            layout = transfer_layout(query, reference, fonts, cfg, variant, distance)
            if layout is not None: pool.append(layout)
    if not pool: raise ValueError('no valid structural transfers')
    pool.sort(key=lambda l: (l.metadata['retrieval_distance'], l.metadata['mapping_cost'], l.metadata['grouping_variant']))
    return pool, [{'id': r['id'], 'distance': d} for d, r in ranking]


def visual_distance(a, b):
    ga, gb = a.glyphs, b.glyphs
    if len(ga) != len(gb): return 1.
    values = []
    for x, y in zip(ga, gb):
        values.append(abs(x.x / a.width - y.x / b.width) + abs(x.y / a.height - y.y / b.height)
                      + abs(x.width / a.width - y.width / b.width) + abs(x.height / a.height - y.height / b.height)
                      + .12 * (x.color != y.color))
    return statistics.mean(values)


def diverse(layouts, count, cfg):
    selected = []
    for layout in layouts:
        if all(visual_distance(layout, other) >= cfg['search']['diversity_distance'] for other in selected): selected.append(layout)
        if len(selected) == count: return selected
    for layout in layouts:
        if all(visual_distance(layout, other) > 1e-5 for other in selected): selected.append(layout)
        if len(selected) == count: break
    return selected


def optimize(initial, model, cfg, seed):
    current = deepcopy(initial); current.score = model.energy(layout_title(current)); best = deepcopy(current)
    rng = random.Random(seed); temp = cfg['search']['temperature']; accepted = 0; invalid = 0
    initial_sizes = {i: max(g.height for g in current.glyphs if g.token == i) for i in range(len(current.metadata['groups']))}
    trace = []
    for step in range(cfg['search']['steps']):
        candidate = deepcopy(current); index = rng.randrange(len(candidate.metadata['groups'])); gs = [g for g in candidate.glyphs if g.token == index]
        height = max(g.height for g in gs); mutation = rng.randrange(5)
        if mutation == 0: move_group(candidate, index, dx=rng.uniform(-1, 1) * height * cfg['search']['move_ratio'])
        elif mutation == 1: move_group(candidate, index, dy=rng.uniform(-1, 1) * height * cfg['search']['move_ratio'])
        elif mutation == 2:
            factor = 1 + rng.uniform(-1, 1) * cfg['search']['scale_ratio']
            ratio = height * factor / initial_sizes[index]
            if cfg['search']['min_scale'] <= ratio <= cfg['search']['max_scale']: move_group(candidate, index, scale=factor)
        elif mutation == 3:
            row = gs[0].row; dx = rng.uniform(-1, 1) * height * cfg['search']['row_move_ratio']
            for g in candidate.glyphs:
                if g.row == row: g.x += dx
        elif len(gs) > 1:
            a, b = rng.sample(gs, 2); a.color, b.color = b.color, a.color
        check = hard_check(candidate, cfg)
        if not check['valid']: invalid += 1; temp *= cfg['search']['cooling']; continue
        candidate.score = model.energy(layout_title(candidate)); change = candidate.score - current.score
        if change > 0 or rng.random() < math.exp(max(-100, change / max(temp, .001))): current = candidate; accepted += 1
        if candidate.score > best.score: best = deepcopy(candidate)
        trace.append({'step': step, 'score': candidate.score, 'best_score': best.score})
        temp *= cfg['search']['cooling']
    best.metadata['optimization'] = {'initial_id': initial.metadata['initial_id'], 'initial_score': model.energy(layout_title(initial)),
                                     'final_score': best.score, 'accepted': accepted, 'invalid': invalid, 'seed': seed, 'trace': trace}
    return best


def generate_loop(text, bank, fonts, analyzer, model, cfg):
    pool, retrieved = candidate_pool(text, bank, fonts, analyzer, cfg)
    for initial in pool: initial.score = model.energy(layout_title(initial))
    ranked_pool = sorted(pool, key=lambda l: (-l.score, l.metadata['initial_id']))
    transfer = diverse(pool, cfg['search']['candidate_count'], cfg)
    ranked = diverse(ranked_pool, cfg['search']['candidate_count'], cfg)
    starts = diverse(ranked_pool, cfg['search']['starts'], cfg)
    optimized = [optimize(l, model, cfg, cfg['seed'] + i * 1009) for i, l in enumerate(starts)]
    optimized.sort(key=lambda l: (-l.score, l.metadata['initial_id']))
    return {'transfer': transfer, 'ranked': ranked, 'optimized': diverse(optimized, cfg['search']['candidate_count'], cfg)}, pool, retrieved


def compare_generated(layout, reference):
    gs = layout.glyphs
    observed = {v['start'] for g in reference['groups'] for v in g['glyphs'] if color_role(v['color']) != 'base'}
    colored = {p for g in gs if color_role(g.color) != 'base' for p in range(g.source_start, g.source_end)}
    reference_accent = {v['start'] for g in reference['groups'] for v in g['glyphs'] if color_role(v['color']) == 'accent'}
    accent = {p for g in gs if color_role(g.color) == 'accent' for p in range(g.source_start, g.source_end)}
    reference_muted = {v['start'] for g in reference['groups'] for v in g['glyphs'] if color_role(v['color']) == 'muted'}
    muted = {p for g in gs if color_role(g.color) == 'muted' for p in range(g.source_start, g.source_end)}
    def jaccard(a, b): return len(a & b) / len(a | b) if a | b else 1.
    actual_box = [min(g.x for g in gs), min(g.y for g in gs), max(g.x + g.width for g in gs), max(g.y + g.height for g in gs)]
    rb = union(pixels(reference)); aspect = (actual_box[2] - actual_box[0]) / (actual_box[3] - actual_box[1])
    reference_aspect = (rb[2] - rb[0]) / (rb[3] - rb[1])
    content = [g.height for g in gs if script(g.text[0]) in ('kanji', 'katakana')]
    known = [v['ink_bbox'][3] - v['ink_bbox'][1] for group in reference['groups'] for v in group['glyphs']
             if v['ink_bbox'] is not None and v['script'] in ('kanji', 'katakana')]
    base = statistics.median(content) if content else statistics.median(g.height for g in gs)
    reference_base = statistics.median(known) * layout.height if known else statistics.median(b[3] - b[1] for b in pixels(reference))
    errors = []
    for group, box in zip(reference['groups'], pixels(reference)):
        matches = [g for g in gs if g.source_start < group['end'] and g.source_end > group['start']]
        if matches:
            height = max(g.y + g.height for g in matches) - min(g.y for g in matches)
            errors.append(abs(math.log((height / base) / ((box[3] - box[1]) / reference_base))))
    return {'line_count_match': len(layout.lines) == len(reference['observed_lines']),
            'exact_break_match': layout.lines == reference['observed_lines'],
            'marked_jaccard': jaccard(observed, colored), 'accent_jaccard': jaccard(reference_accent, accent),
            'muted_jaccard': jaccard(reference_muted, muted), 'aspect_log_error': abs(math.log(aspect / reference_aspect)),
            'group_height_log_error': statistics.mean(errors) if errors else None,
            'reference_marked': sorted(observed), 'generated_marked': sorted(colored)}


def save_layout(layout, folder, stem, cfg, comparison=None, transparent=False):
    renderer = Renderer()
    (folder / (stem + '.svg')).write_text(renderer.svg(layout, transparent=transparent))
    (folder / (stem + '.png')).write_bytes(renderer.png(layout, transparent=transparent))
    record = layout.record(); record.update(image=folder.name + '/' + stem + '.png', svg=folder.name + '/' + stem + '.svg',
                                            hard_check=hard_check(layout, cfg), transparent=transparent)
    if comparison is not None: record['comparison'] = compare_generated(layout, comparison)
    return record


def summary_cases(cases):
    references = [c for c in cases if c['reference']]
    names = ('legacy', 'transfer', 'ranked', 'optimized')
    summaries = {}
    for arm in names:
        first = [c['arms'][arm]['candidates'][0] for c in references]
        all_candidates = [l for c in cases for l in c['arms'][arm]['candidates']]
        summaries[arm] = {'exact_break_match': sum(l['comparison']['exact_break_match'] for l in first),
                          'line_count_match': sum(l['comparison']['line_count_match'] for l in first),
                          'marked_jaccard_mean': statistics.mean(l['comparison']['marked_jaccard'] for l in first),
                          'accent_jaccard_mean': statistics.mean(l['comparison']['accent_jaccard'] for l in first),
                          'muted_jaccard_mean': statistics.mean(l['comparison']['muted_jaccard'] for l in first),
                          'aspect_log_error_median': statistics.median(l['comparison']['aspect_log_error'] for l in first),
                          'group_height_log_error_mean': statistics.mean(l['comparison']['group_height_log_error'] for l in first),
                          'candidate_count': len(all_candidates),
                          'integrity_failures': sum(not l['hard_check']['integrity'] for l in all_candidates),
                          'kinsoku_failures': sum(l['hard_check']['kinsoku'] for l in all_candidates),
                          'overflow_failures': sum(l['hard_check']['overflow'] for l in all_candidates),
                          'max_ink_collision': max(l['hard_check']['collision'] for l in all_candidates)}
    return summaries


def write_contact_sheets(out, cases):
    font = ImageFont.truetype(str(ROOT / 'assets/open-fonts/noto-sans-jp-black.ttf'), 18)
    columns = [('reference', 'Reference'), ('legacy', 'Legacy'), ('transfer', 'Transfer'), ('ranked', '+ Ranker'), ('optimized', '+ Optimizer')]
    for block in range(0, len(cases), 5):
        subset = cases[block:block + 5]
        sheet = Image.new('RGB', (1800, len(subset) * 245 + 36), '#fafafa'); d = ImageDraw.Draw(sheet)
        for j, (_, label) in enumerate(columns): d.text((j * 360 + 10, 8), label, fill='#27272a', font=font)
        for i, case in enumerate(subset):
            y = 36 + i * 245
            d.text((10, y + 2), case['id'] + ' ' + case['text'], font=font, fill='#18181b')
            for j, (arm, _) in enumerate(columns):
                path = out / (case['reference_image'] if arm == 'reference' and case['reference'] else case['arms'][arm]['candidates'][0]['image']) if arm != 'reference' or case['reference'] else None
                if path is not None:
                    im = Image.open(path).convert('RGB'); im.thumbnail((350, 197)); sheet.paste(im, (j * 360 + 5, y + 34))
        sheet.save(out / f'contact-{block // 5 + 1}.jpg', quality=95)


def write_gallery(out, result):
    # Keep glyph geometry and traces in results.json, not in the page payload.
    compact = {'ranker_evaluation': result['ranker_evaluation'], 'cases': []}
    for case in result['cases']:
        row = {k: case[k] for k in ('id', 'text', 'reference', 'reference_image', 'retrieved', 'fold', 'optimizer_pair')}
        row['arms'] = {key: {'candidates': [{k: r[k] for k in ('image', 'svg', 'score', 'lines', 'comparison') if k in r}
                                         for r in arm['candidates']]} for key, arm in case['arms'].items()}
        compact['cases'].append(row)
    data = json.dumps(compact, ensure_ascii=False).replace('<', '\\u003c')
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>16 张参考 · 最小闭环</title>
<style>*{box-sizing:border-box}body{margin:0;background:#fafafa;color:#18181b;font:14px system-ui}main{max-width:1500px;margin:auto;padding:32px 24px}h1{font-size:26px;margin:0 0 24px}input,button,a{font:inherit}input{padding:10px 12px;border:1px solid #d4d4d8;border-radius:8px;background:white;max-width:450px;width:100%}article{margin:30px 0;border:1px solid #e4e4e7;border-radius:12px;background:white;padding:20px}h2{font-size:18px;margin:0 0 18px}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}.label{font-weight:600;margin-bottom:10px}img{width:100%;aspect-ratio:16/9;object-fit:contain;background:#000;border-radius:7px;display:block}nav{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}button{cursor:pointer;border:1px solid #e4e4e7;border-radius:5px;background:white;padding:3px 7px}button.active{background:#18181b;color:white}a{color:inherit;margin-right:12px}details{margin-top:20px}pre{overflow:auto;font-size:12px;max-height:360px;padding:12px;background:#f4f4f5;border-radius:6px}.stats{display:flex;flex-wrap:wrap;gap:28px;margin-bottom:24px}.stats b{font-size:22px;display:block}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:20px;max-width:800px}@media(max-width:1000px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){main{padding:20px 12px}.grid{grid-template-columns:1fr}article{padding:14px}.pair{grid-template-columns:1fr}}</style>
<main><h1>16 张参考 · 最小闭环</h1><div class="stats" id="stats"></div><input id="search" type="search" placeholder="搜索标题" aria-label="搜索标题"><div id="cases"></div></main>
<script>const data=__DATA__,names={legacy:'Legacy',transfer:'Transfer',ranked:'+ Ranker',optimized:'+ Optimizer'},root=document.querySelector('#cases');
function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
const stats=document.querySelector('#stats');for(const [value,label] of [[data.cases.length,'标题'],[data.ranker_evaluation.macro_accuracy,'Ranker 留一正确率'],[data.ranker_evaluation.legal_accuracy,'合法难例正确率']]){const d=el('div');d.append(el('b',typeof value==='number'&&value<1?(value*100).toFixed(1)+'%':value),el('span',label));stats.append(d);}
for(const c of data.cases){const a=el('article');a.dataset.text=(c.id+' '+c.text).toLowerCase();a.append(el('h2',c.id+' '+c.text));const grid=el('div');grid.className='grid';
 if(c.reference){const ref=el('div');ref.append(el('div','Reference'));ref.firstChild.className='label';const img=el('img');img.src=c.reference_image;img.loading='lazy';img.alt='参考原图 '+c.text;ref.append(img);grid.append(ref);}
 for(const [key,name] of Object.entries(names)){const col=el('div'),label=el('div',name);label.className='label';const img=el('img');img.loading='lazy';const nav=el('nav'),downloads=el('div'),png=el('a','PNG'),svg=el('a','SVG');png.download='';svg.download='';downloads.append(png,svg);
 function choose(i){const item=c.arms[key].candidates[i];img.src=item.image;img.alt=name+' '+c.text+' 候选 '+(i+1);png.href=item.image;svg.href=item.svg;for(const b of nav.children)b.classList.toggle('active',Number(b.dataset.index)===i);}
 c.arms[key].candidates.forEach((item,i)=>{const b=el('button',String(i+1));b.dataset.index=i;b.onclick=()=>choose(i);nav.append(b);});choose(0);col.append(label,img,nav,downloads);grid.append(col);}
 a.append(grid);if(c.optimizer_pair){const pair=el('div');pair.className='pair';for(const [path,title] of [[c.optimizer_pair.before,'同一候选 · 优化前'],[c.optimizer_pair.after,'同一候选 · 优化后']]){const d=el('div');d.append(el('div',title));const img=el('img');img.src=path;img.loading='lazy';img.alt=title+' '+c.text;d.append(img);pair.append(d);}a.append(pair);}
 const details=el('details');details.append(el('summary','参数与对照指标'),el('pre',JSON.stringify({retrieved:c.retrieved,fold:c.fold,arms:Object.fromEntries(Object.entries(c.arms).map(([key,v])=>[key,v.candidates[0].comparison||null])),optimizer_pair:c.optimizer_pair},null,2)));a.append(details);root.append(a);}
document.querySelector('#search').oninput=e=>{const q=e.target.value.toLowerCase();for(const a of root.children)a.hidden=!a.dataset.text.includes(q);};</script></html>'''
    (out / 'index.html').write_text(document.replace('__DATA__', data))


def benchmark(data, fonts, out, seed=None):
    cfg = settings()
    if seed is not None: cfg['seed'] = seed
    evaluation = read(out / 'ranker-evaluation.json')
    if not evaluation['gate_passed']: raise RuntimeError('ranker gate failed; repair labels/features before search')
    analyzer = JapaneseAnalyzer(load_config()['rules']); legacy_engine = LayoutEngine(fonts)
    sources = {s['id']: s for s in read(ROOT / 'references/dataset.json')['samples']}
    from experiments.reference_comparison import crop_reference
    rows = data['titles'] + [{'id': f'u{i + 1:02}', 'text': text} for i, text in enumerate(cfg['unseen'])]
    cases = []
    for row in rows:
        start = time.perf_counter(); is_reference = row['id'].startswith('s')
        bank = [r for r in data['titles'] if r['id'] != row['id']]
        model_path = out / 'ranker-folds' / (row['id'] + '.json') if is_reference else out / 'ranker.json'
        model = Ranker(read(model_path)); assert row['id'] not in model.data['training_titles']
        arms, pool, retrieved = generate_loop(row['text'], bank, fonts, analyzer, model, cfg)
        legacy = legacy_engine.generate(row['text'], analyzer.analyze(row['text']), seed=cfg['seed'], count=cfg['search']['candidate_count'])
        arms = {'legacy': legacy, **arms}
        folder = out / row['id']; folder.mkdir(exist_ok=True)
        if is_reference:
            source = ROOT / 'references/originals' / sources[row['id']]['file']
            if source.exists():
                crop_reference(sources[row['id']], folder, (cfg['canvas']['width'], cfg['canvas']['height']))
            elif not (folder / 'reference.jpg').exists():
                # A clone can use the committed clean crop; raw screenshots are
                # needed only to remeasure or rebuild annotation overlays.
                shutil.copyfile(DEFAULT_OUT / row['id'] / 'reference.jpg', folder / 'reference.jpg')
        case = {'id': row['id'], 'text': row['text'], 'reference': is_reference, 'reference_image': row['id'] + '/reference.jpg' if is_reference else None,
                'retrieved': retrieved, 'pool_count': len(pool), 'fold': {'training_titles': model.data['training_titles'], 'retrieval_titles': [t['id'] for t in bank]},
                'model_sha256': digest(model.data), 'arms': {}}
        write(folder / 'initial-pool.json', [{'id': l.metadata['initial_id'], 'reference_id': l.metadata['reference_id'],
                                             'score': l.score, 'title': layout_title(l), 'hard_check': hard_check(l, cfg),
                                             'comparison': compare_generated(l, row) if is_reference else None} for l in pool])
        for arm, candidates in arms.items():
            if len(candidates) != cfg['search']['candidate_count']:
                raise RuntimeError(f'{row["id"]} {arm} only produced {len(candidates)} distinct candidates')
            case['arms'][arm] = {'candidates': [save_layout(l, folder, f'{arm}-{i + 1}', cfg, row if is_reference else None) for i, l in enumerate(candidates)]}
        best = arms['optimized'][0]; before = next(l for l in pool if l.metadata['initial_id'] == best.metadata['initial_id'])
        before_record = save_layout(before, folder, 'optimizer-before', cfg, row if is_reference else None)
        case['optimizer_pair'] = {'initial_id': best.metadata['initial_id'], 'before': before_record['image'], 'after': case['arms']['optimized']['candidates'][0]['image'],
                                  'before_score': before.score, 'after_score': best.score,
                                  'before_comparison': before_record.get('comparison'), 'after_comparison': case['arms']['optimized']['candidates'][0].get('comparison')}
        case['elapsed_ms'] = (time.perf_counter() - start) * 1000; cases.append(case)
        print(row['id'], 'pool', len(pool), 'seconds', round(case['elapsed_ms'] / 1000, 2), flush=True)
    summary = summary_cases(cases)
    result = {'version': 1, 'protocol': '16 leave-one-title-out queries + 4 non-reference texts; shared fonts and renderer; no target annotation in generation',
              **provenance(data, fonts, cfg), 'config': cfg,
              'ranker_evaluation': {k: v for k, v in evaluation.items() if k != 'records'}, 'summary': summary, 'cases': cases,
              'llm_calls': 0, 'aesthetic_claim': 'requires visual review; increased learned score is not proof of improvement'}
    write(out / 'results.json', result); write(out / 'summary.json', summary)
    write_contact_sheets(out, cases); write_gallery(out, result)
    print(json.dumps(summary, indent=2), flush=True)
    return result


def render_text(text, data, fonts, out, model_dir=DEFAULT_OUT, seed=None, transparent=False):
    cfg = settings()
    if seed is not None: cfg['seed'] = seed
    if not text or len(text) > 120 or any(c.isspace() for c in text):
        raise ValueError('本实验支持 1–120 字的单条标题，暂不支持空白字符。')
    model = Ranker(read(model_dir / 'ranker.json'))
    if model.data['annotation_sha256'] != digest(data): raise RuntimeError('ranker annotation hash mismatch; run --ranker')
    if not model.data['evaluation_gate_passed']: raise RuntimeError('ranker gate has not passed')
    analyzer = JapaneseAnalyzer(load_config()['rules'])
    arms, pool, retrieved = generate_loop(text, data['titles'], fonts, analyzer, model, cfg)
    target = out / 'custom'; target.mkdir(exist_ok=True)
    records = [save_layout(l, target, f'candidate-{i + 1}', cfg, transparent=transparent) for i, l in enumerate(arms['optimized'])]
    if len(records) != cfg['search']['candidate_count']: raise RuntimeError('insufficient distinct valid candidates')
    write(target / 'results.json', {'text': text, 'references': retrieved, 'candidates': records,
                                   **provenance(data, fonts, cfg, model), 'transparent': transparent})
    print('Saved six PNG/SVG candidates to', target, flush=True)


def record_title(record):
    """Recover score inputs from saved transferred layouts, without font bytes."""
    groups = deepcopy(record['metadata']['groups'])
    for i, group in enumerate(groups):
        glyphs = [g for g in record['glyphs'] if g['token'] == i]
        boxes = [[g['x'] / record['width'], g['y'] / record['height'],
                  (g['x'] + g['width']) / record['width'], (g['y'] + g['height']) / record['height']] for g in glyphs]
        group['row'] = glyphs[0]['row']; group['ink_bbox'] = union(boxes)
        group['glyphs'] = [{'text': g['text'], 'start': g['source_start'], 'end': g['source_end'],
                            'script': script(g['text'][0]), 'color': g['color'], 'ink_bbox': box}
                           for g, box in zip(glyphs, boxes)]
        for key in ('source_glyphs', 'source_box'): group.pop(key, None)
    return {'id': 'generated', 'text': record['text'], 'groups': groups,
            'canvas': {'width': record['width'], 'height': record['height']}, 'background': record['background']}


def write_blind_gallery(out, cases, seed):
    """Randomized viewing aid. No claim of independent human ratings."""
    rng = random.Random(seed); order = []
    for case in cases:
        arms = list(case['arms']); rng.shuffle(arms)
        order.append({'id': case['id'], 'order': arms})
    write(out / 'blind-key.json', {'seed': seed, 'key': order})
    blocks = []
    names = {'legacy': 'Legacy', 'transfer': 'Transfer', 'ranked': '+ Ranker', 'optimized': '+ Optimizer'}
    for case, key in zip(cases, order):
        cells = []
        if case['reference']:
            cells.append('<div><b>Reference</b><img loading="lazy" src="' + case['reference_image'] + '" alt="参考"></div>')
        for i, arm in enumerate(key['order']):
            item = case['arms'][arm]['candidates'][0]
            cells.append('<div><b data-name="' + names[arm] + '">' + chr(65 + i) + '</b><img loading="lazy" src="' + item['image'] + '" alt="候选 ' + chr(65 + i) + '"></div>')
        blocks.append('<article><h2>' + html.escape(case['id'] + ' ' + case['text']) + '</h2><div class="grid">' + ''.join(cells) + '</div></article>')
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>随机对照</title>
<style>*{box-sizing:border-box}body{margin:0;background:#fafafa;color:#18181b;font:14px system-ui}main{max-width:1500px;margin:auto;padding:32px 24px}h1{font-size:26px}h2{font-size:18px}button{border:1px solid #d4d4d8;border-radius:8px;background:white;padding:9px 14px;cursor:pointer}article{margin:24px 0;padding:20px;border:1px solid #e4e4e7;border-radius:12px;background:white}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}img{display:block;margin-top:10px;width:100%;aspect-ratio:16/9;background:black;object-fit:contain;border-radius:7px}@media(max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:500px){main{padding:20px 12px}.grid{grid-template-columns:1fr}}</style>
<main><h1>随机对照</h1><button id="reveal">显示方法</button>__BLOCKS__</main><script>document.querySelector('#reveal').onclick=e=>{for(const b of document.querySelectorAll('[data-name]'))b.textContent=b.dataset.name;e.target.disabled=true;};</script></html>'''
    (out / 'blind.html').write_text(document.replace('__BLOCKS__', ''.join(blocks)))


def diagnose(data, fonts, out):
    """Post-hoc reference errors and score blind spots, never selection inputs."""
    result = read(out / 'results.json'); cfg = result['config']; analyzer = JapaneseAnalyzer(load_config()['rules'])
    current_fonts = {role: face.metadata['sha256'] for role, face in fonts.items()}
    if current_fonts != {role: meta['sha256'] for role, meta in result['fonts'].items()}:
        raise RuntimeError('diagnosis font hash mismatch; use benchmark fonts')
    references = {t['id']: t for t in data['titles']}; reports = []; pool_records = []
    arm_failures = {arm: Counter() for arm in ('legacy', 'transfer', 'ranked', 'optimized')}
    for case in result['cases']:
        model = Ranker(read(out / 'ranker-folds' / (case['id'] + '.json') if case['reference'] else out / 'ranker.json'))
        pool_path = out / case['id'] / 'initial-pool.json'
        if pool_path.exists():
            pool = read(pool_path)
        else:
            # Supports diagnosing the first frozen run. This repeats only the
            # deterministic transfer stage, never optimizer or target selection.
            bank = [r for r in data['titles'] if r['id'] != case['id']]
            generated, _ = candidate_pool(case['text'], bank, fonts, analyzer, cfg)
            pool = [{'id': l.metadata['initial_id'], 'reference_id': l.metadata['reference_id'], 'score': model.energy(layout_title(l)),
                     'title': layout_title(l), 'hard_check': hard_check(l, cfg),
                     'comparison': compare_generated(l, references[case['id']]) if case['reference'] else None} for l in generated]
            write(pool_path, pool)
        pool_records.append({'id': case['id'], 'count': len(pool), 'source_counts': dict(Counter(p['reference_id'] for p in pool))})
        if not case['reference']: continue
        ref = references[case['id']]; ranked = case['arms']['ranked']['candidates'][0]
        best_color = max(p['comparison']['marked_jaccard'] for p in pool)
        matched = [p for p in pool if p['comparison']['exact_break_match']]
        target_lines = len(ref['observed_lines'])
        bank = [r for r in data['titles'] if r['id'] != case['id']]
        available_rows = sorted({len(r['observed_lines']) for r in bank})
        original_energy = model.energy(ref); replay = redraw(ref, fonts)
        replay_energy = model.energy(layout_title(replay))
        # Explain energy exploitation on generated layouts, rather than treating
        # a higher self-score as a validation result.
        contributions = (model.vector(record_title(ranked)) - model.vector(ref)) * np.array(model.data['weights'])
        feature_names = model.data['features'] + [name + '^2' for name in model.data['features']]
        score_drivers = sorted(zip(feature_names, contributions.tolist()), key=lambda p: -abs(p[1]))[:8]
        pairs = case['optimizer_pair']; before, after = pairs['before_comparison'], pairs['after_comparison']
        changes = {k: after[k] - before[k] for k in ('marked_jaccard', 'aspect_log_error', 'group_height_log_error')}
        reports.append({'id': case['id'], 'target_line_count': target_lines, 'available_reference_line_counts': available_rows,
                        'missing_target_row_count_in_bank': target_lines not in available_rows,
                        'pool_has_exact_break': bool(matched), 'ranker_dropped_exact_break': bool(matched) and not ranked['comparison']['exact_break_match'],
                        'pool_best_marked_jaccard': best_color, 'ranked_marked_jaccard': ranked['comparison']['marked_jaccard'],
                        'ranker_color_regret': best_color - ranked['comparison']['marked_jaccard'],
                        'annotation_energy': original_energy, 'font_replay_energy': replay_energy,
                        'font_replay_hard_check': hard_check(replay, cfg),
                        'annotation_beats_ranked': original_energy > ranked['score'],
                        'font_replay_beats_ranked': replay_energy > ranked['score'],
                        'ranked_energy': ranked['score'], 'optimizer_score_gain': pairs['after_score'] - pairs['before_score'],
                        'ranked_minus_annotation_score_drivers': [{'feature': name, 'contribution': value} for name, value in score_drivers],
                        'optimizer_same_candidate_metric_delta': changes})
        reference_accents = any(color_role(v['color']) == 'accent' for g in ref['groups'] for v in g['glyphs'])
        for arm in arm_failures:
            c = case['arms'][arm]['candidates'][0]['comparison']; f = arm_failures[arm]
            if not c['exact_break_match']: f['break_mismatch'] += 1
            if c['aspect_log_error'] > math.log(1.2): f['aspect_error_over_20pct'] += 1
            if c['group_height_log_error'] > math.log(1.2): f['hierarchy_log_error_over_log_1_2'] += 1
            if c['marked_jaccard'] < .5: f['marked_position_jaccard_below_0_5'] += 1
            if reference_accents and c['accent_jaccard'] == 0: f['zero_chromatic_position_overlap'] += 1

    # Isolate the claimed blindness: same text, geometry and color counts;
    # only occurrence-level color location changes inside one visual group.
    probes = []
    for ref in data['titles']:
        model = Ranker(read(out / 'ranker-folds' / (ref['id'] + '.json')))
        baseline = feature_values(ref)
        for gi, group in enumerate(ref['groups']):
            for i, a in enumerate(group['glyphs']):
                for j in range(i + 1, len(group['glyphs'])):
                    if a['color'] == group['glyphs'][j]['color']: continue
                    other = deepcopy(ref); gs = other['groups'][gi]['glyphs']
                    gs[i]['color'], gs[j]['color'] = gs[j]['color'], gs[i]['color']
                    values = feature_values(other)
                    delta = {k: values[k] - baseline[k] for k in values if abs(values[k] - baseline[k]) > 1e-12}
                    probes.append({'title': ref['id'], 'group': group['id'], 'swapped_spans': [a['start'], group['glyphs'][j]['start']],
                                   'changed_features': delta, 'score_difference': model.energy(other) - model.energy(ref),
                                   'role_changed': color_role(a['color']) != color_role(group['glyphs'][j]['color']),
                                   'blind': not delta, 'label': 'sensitivity probe, not automatically an aesthetic negative'})
    write(out / 'color-sensitivity.json', probes)

    evaluation = read(out / 'ranker-evaluation.json')
    negatives = read(out / 'negatives.json')['pairs']; qa_dir = out / 'ranker-qa'; qa_dir.mkdir(exist_ok=True)
    qa = []; font = ImageFont.truetype(str(ROOT / 'assets/open-fonts/noto-sans-jp-black.ttf'), 16)
    for ref in data['titles']:
        # Show the hardest legal example per title, including ranker mistakes.
        scores = [r for r in evaluation['records'] if r['title'] == ref['id'] and r['legal']]
        chosen = min(scores, key=lambda r: (r['difference'], r['type'], r['ordinal']))
        item = next(n for n in negatives if (n['title'], n['type'], n['ordinal']) == (ref['id'], chosen['type'], chosen['ordinal']))
        original = save_layout(redraw(ref, fonts), qa_dir, ref['id'] + '-original', cfg)
        negative = save_layout(redraw(item['negative'], fonts), qa_dir, ref['id'] + '-negative', cfg)
        qa.append({'id': ref['id'], 'original': original['image'], 'negative': negative['image'], 'evaluation': chosen})
    write(qa_dir / 'results.json', qa)
    for block in range(0, len(qa), 8):
        sheet = Image.new('RGB', (1200, len(qa[block:block + 8]) * 207 + 30), '#fafafa'); d = ImageDraw.Draw(sheet)
        for j, label in enumerate(('Reference', 'Original geometry / current fonts', 'Corrupted geometry / current fonts')):
            d.text((j * 400 + 8, 7), label, font=font, fill='#18181b')
        for i, row in enumerate(qa[block:block + 8]):
            y = 30 + i * 207; e = row['evaluation']
            d.text((8, y), f'{row["id"]}  {e["type"]}  original - corrupted = {e["difference"]:.3f}', font=font, fill='#18181b')
            paths = [out / row['id'] / 'reference.jpg', out / row['original'], out / row['negative']]
            for j, path in enumerate(paths):
                im = Image.open(path).convert('RGB'); im.thumbnail((392, 177)); sheet.paste(im, (j * 400 + 4, y + 25))
        sheet.save(qa_dir / f'contact-{block // 8 + 1}.jpg', quality=95)
    summary = {'reference_queries': len(reports), 'failure_counts': {k: dict(v) for k, v in arm_failures.items()},
               'pool_exact_break_coverage': sum(r['pool_has_exact_break'] for r in reports),
               'ranker_dropped_exact_break_count': sum(r['ranker_dropped_exact_break'] for r in reports),
               'ranker_color_regret_mean': statistics.mean(r['ranker_color_regret'] for r in reports),
               'annotation_beats_ranked_count': sum(r['annotation_beats_ranked'] for r in reports),
               'font_replay_beats_ranked_count': sum(r['font_replay_beats_ranked'] for r in reports),
               'missing_row_count_bank': [r['id'] for r in reports if r['missing_target_row_count_in_bank']],
               'optimizer_same_candidate_score_increased': sum(r['optimizer_score_gain'] > 1e-8 for r in reports),
               'optimizer_same_candidate_color_worse': sum(r['optimizer_same_candidate_metric_delta']['marked_jaccard'] < -1e-8 for r in reports),
               'optimizer_same_candidate_hierarchy_worse': sum(r['optimizer_same_candidate_metric_delta']['group_height_log_error'] > 1e-8 for r in reports),
               'color_position_probe_count': len(probes), 'blind_color_position_probe_count': sum(r['blind'] for r in probes),
               'color_role_position_probe_count': sum(r['role_changed'] for r in probes),
               'blind_color_role_position_probe_count': sum(r['role_changed'] and r['blind'] for r in probes),
               'color_role_probe_titles': sorted({r['title'] for r in probes if r['role_changed']})}
    report = {'protocol': 'post-generation diagnostics only; no diagnostic oracle or query annotation used by selection/search',
              'limits': 'reference likeness is not aesthetic quality; synthetic negatives are provisional labels; developer image review is not independent',
              'summary': summary, 'cases': reports, 'pools': pool_records,
              'ranker_qa_score_basis': 'measured annotation features; replay pictures use common fonts and inferred unresolved kana boxes'}
    write(out / 'diagnostics.json', report); write_blind_gallery(out, result['cases'], cfg['seed'])
    write_gallery(out, result)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--ranker', action='store_true')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--diagnose', action='store_true')
    parser.add_argument('--text')
    parser.add_argument('--model-dir', type=Path, help='--text model directory; defaults to --out when training in this invocation')
    parser.add_argument('--seed', type=int, help='generation seed; corruption/training seed remains fixed in config')
    parser.add_argument('--transparent', action='store_true', help='transparent PNG and SVG for --text')
    parser.add_argument('--kanji', type=Path)
    parser.add_argument('--kana', type=Path)
    args = parser.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    if args.prepare: prepare_annotations(out)
    data = read(ROOT / 'references/minimal_visual_groups.json')
    fonts = get_fonts(args) if args.ranker or args.benchmark or args.text or args.diagnose else None
    if args.ranker: train_rankers(data, fonts, out)
    if args.benchmark: benchmark(data, fonts, out, seed=args.seed)
    if args.diagnose: diagnose(data, fonts, out)
    if args.text:
        model_dir = (args.model_dir or (out if args.ranker else DEFAULT_OUT)).resolve()
        render_text(args.text, data, fonts, out, model_dir, args.seed, args.transparent)


if __name__ == '__main__':
    main()

"""Occurrence and word-position facts; intentionally makes no plot/intent prediction.

The old full benchmark remains a frozen experiment. An overlapping repeated-string
annotation in s036 is corrected explicitly in this study, not silently rewritten.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json

from engine.layout import load_config
from engine.text import JapaneseAnalyzer, script
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CHROMATIC_LABELS = {'blue', 'yellow', 'pink', 'violet', 'red', 'green', 'orange', 'beige', 'brown'}
MUTED_LABELS = {'grey', 'grey-violet', 'dark-grey', 'light-grey', 'light-violet-grey', 'grey-gradient'}
TEXTURE_LABELS = {'grey-blue-texture', 'red-texture'}

def appearance(label):
    if label in CHROMATIC_LABELS:
        return 'local_chromatic'
    if label in MUTED_LABELS:
        return 'muted_or_tinted_tone'
    if label in TEXTURE_LABELS:
        return 'whole_effect'
    raise ValueError(label)

def corrected_reviews(source):
    reviews = deepcopy(source['samples'])
    case = next(s for s in reviews if s['id'] == 's036')
    # Reference lines are [0:4], [4:8], [8:14]. The old find(start+1)
    # interpreted occurrence 1 as overlapping [2:6].
    case['accent_units'][1].update(start=4, end=8)
    corrections = [{'sample_id': 's036', 'unit_text': 'らぶらぶ',
                    'old_span': [2, 6], 'corrected_span': [4, 8],
                    'basis': 'second observed line, visually verified; non-overlapping repeat',
                    'frozen_benchmark_changed': False}]
    # These salient grey roles were absent from the older spot-colour list.
    # Their addition makes the distinction between grey hierarchy and hue explicit.
    for sample_id, text, label, basis in [
        ('s031', '親', 'grey', 'white-background original visibly separates grey 親 from brown 子'),
        ('s035', '命', 'light-grey', 'original image and existing six-sample fine annotation both record light-grey 命')]:
        sample = next(s for s in reviews if s['id'] == sample_id)
        sample['accent_units'].append({'text': text, 'start': 0, 'end': 1, 'occurrence': 0,
                                      'observed_color_label': label, 'visual_role': 'tone_hierarchy',
                                      'exact_rgb': None, 'confidence': 'visual_approximate'})
        sample['accent_units'].sort(key=lambda u: u['start'])
        corrections.append({'sample_id': sample_id, 'added_span': [0, 1], 'text': text,
                            'basis': basis, 'frozen_benchmark_changed': False})
    return reviews, corrections

def unit_features(unit, text, tokens, line_ranges):
    a, b = unit['start'], unit['end']
    assert text[a:b] == unit['text']
    overlap = [t for t in tokens if t.start < b and t.start + len(t.text) > a]
    if len(overlap) == 1:
        t = overlap[0]
        location = ('whole_token' if (a, b) == (t.start, t.start + len(t.text))
                    else 'token_prefix' if a == t.start
                    else 'token_suffix' if b == t.start + len(t.text)
                    else 'token_internal')
    else:
        location = 'multiple_tokens'
    line_indexes = [i for i, (lo, hi) in enumerate(line_ranges) if lo < b and hi > a]
    return {**unit, 'appearance_class': appearance(unit['observed_color_label']),
            'token_position': location,
            'token_spans': [{'text': t.text, 'start': t.start, 'end': t.start + len(t.text), 'pos': t.pos} for t in overlap],
            'scripts': dict(Counter(script(c) for c in unit['text'])),
            'line_indexes': line_indexes,
            'line_initial': any(a == line_ranges[i][0] for i in line_indexes),
            'line_final': any(b == line_ranges[i][1] for i in line_indexes),
            'title_initial': a == 0, 'title_final': b == len(text),
            'repeated_spelling_positions': [i for i in range(len(text)) if text.startswith(unit['text'], i)]}

def structural_mode(units, text):
    marked = {i for u in units for i in range(u['start'], u['end'])}
    if not units:
        return 'no_local_difference_recorded'
    if len(marked) == len(text.replace(' ', '')):
        return 'whole_title_tone_or_effect'
    if len(units) == 1 and len(marked) == 1:
        return 'one_character_difference'
    if len(units) == 1:
        return 'one_span_difference'
    return 'multiple_occurrence_differences'

def token_ids(positions, tokens):
    return {i for i, t in enumerate(tokens) if any(t.start <= p < t.start + len(t.text) for p in positions)}

def write_evidence(cases):
    ids = ['s005', 's009', 's014', 's052', 's033', 's035', 's038', 's048',
           's024', 's060', 's064', 's077', 's030', 's039', 's051', 's054',
           's056', 's072', 's068', 's069']
    indexed = {c['id']: c for c in cases}
    sheet = Image.new('RGB', (1600, 1700), '#fafafa');draw = ImageDraw.Draw(sheet)
    font_path = str(ROOT/'assets/open-fonts/noto-sans-jp-black.ttf')
    title_font = ImageFont.truetype(font_path, 17)
    label_font = ImageFont.truetype(font_path, 15)
    def wrap(text, font):
        lines = [];line = ''
        for char in text:
            if line and draw.textlength(line + char, font=font) > 380:
                lines.append(line);line = ''
            line += char
        if line: lines.append(line)
        return lines
    for k, identifier in enumerate(ids):
        row, column = divmod(k, 4);x, y = column*400 + 10, row*340 + 8
        case = indexed[identifier]
        for n, line in enumerate(wrap(identifier[1:] + ' ' + case['text'], title_font)):
            draw.text((x, y+n*22), line, font=title_font, fill='#18181b')
        tile = Image.open(ROOT/'experiments/reference-benchmark'/identifier/'reference.jpg')
        tile.thumbnail((380, 214));sheet.paste(tile, (x, y+48))
        label = ' / '.join(u['text'] + ':' + u['observed_color_label'] for u in case['units'])
        for n, line in enumerate(wrap(label, label_font)):
            draw.text((x, y+272+n*19), line, font=label_font, fill='#3f3f46')
    sheet.save(ROOT/'analysis/color-position-evidence.jpg', quality=90)

def run():
    path = ROOT / 'analysis/color_reference_review.json'
    source = json.loads(path.read_text())
    reviews, corrections = corrected_reviews(source)
    references = {s['id']: s for s in json.loads((ROOT / 'references/dataset.json').read_text())['samples']}
    generated = {s['id']: s for s in json.loads((ROOT / 'experiments/reference-benchmark/results.json').read_text())['cases']}
    analyzer = JapaneseAnalyzer(load_config()['rules'])
    cases = []
    for s in reviews:
        r = references[s['id']];text = s['text'];tokens = analyzer.analyze(text)
        cursor = 0;line_ranges = []
        for line in r['observed_lines']:
            line_ranges.append((cursor, cursor + len(line)));cursor += len(line)
        assert cursor == len(text)
        units = [unit_features(u, text, tokens, line_ranges) for u in s['accent_units']]
        reference_positions = {p for u in units for p in range(u['start'], u['end'])}
        first = generated[s['id']]['candidates'][0]
        generated_positions = set(first['comparison']['generated_accent_positions'])
        selected_tokens = token_ids(generated_positions, tokens)
        target_tokens = token_ids(reference_positions, tokens)
        chromatic_positions = {p for u in units if u['appearance_class'] == 'local_chromatic' for p in range(u['start'], u['end'])}
        chromatic_tokens = token_ids(chromatic_positions, tokens)
        cases.append({'id': s['id'], 'text': text, 'observed_lines': r['observed_lines'],
                      'transcription_confidence': r['transcription_confidence'],
                      'structural_mode': structural_mode(units, text), 'units': units,
                      'marked_character_count': len(reference_positions),
                      'chromatic_character_count': len(chromatic_positions),
                      'default_chromatic_character_overlap': bool(generated_positions & chromatic_positions),
                      'default_chromatic_word_overlap': bool(selected_tokens & chromatic_tokens),
                      'repeated_glyphs': [{'text': c, 'all_positions': [i for i, ch in enumerate(text) if ch == c],
                                           'marked_positions': [i for i, ch in enumerate(text) if ch == c and i in reference_positions]}
                                          for c, n in Counter(text).items() if n > 1 and any(text[i] == c for i in reference_positions)],
                      'default_character_overlap': bool(generated_positions & reference_positions),
                      'default_word_overlap': bool(selected_tokens & target_tokens),
                      'default_word_correct_but_character_disjoint': bool(selected_tokens & target_tokens) and not bool(generated_positions & reference_positions)})
    all_units = [u for c in cases for u in c['units']]
    one_character = [c for c in cases if c['structural_mode'] == 'one_character_difference' and c['id'] != 's069']
    one_chromatic_character = [c for c in cases if c['chromatic_character_count'] == 1 and c['id'] != 's069']
    no_particles = [{'id': c['id'], 'position': i, 'marked': any(u['start'] <= i < u['end'] for u in c['units'])}
                    for c in cases for i, ch in enumerate(c['text']) if ch == 'の']
    report_summary = {
        'samples': len(cases), 'visually_recorded_units': len(all_units),
        'unit_length_counts': dict(sorted(Counter(u['end'] - u['start'] for u in all_units).items())),
        'units_per_sample': dict(sorted(Counter(len(c['units']) for c in cases).items())),
        'marked_characters_per_sample': dict(sorted(Counter(c['marked_character_count'] for c in cases).items())),
        'structural_modes': dict(Counter(c['structural_mode'] for c in cases)),
        'appearance_unit_counts': dict(Counter(u['appearance_class'] for u in all_units)),
        'appearance_sample_counts': {label: sum(any(u['appearance_class'] == label for u in c['units']) for c in cases)
                                     for label in ('local_chromatic', 'muted_or_tinted_tone', 'whole_effect')},
        'token_position_counts': dict(Counter(u['token_position'] for u in all_units)),
        'marked_character_scripts': dict(Counter(script(c['text'][i]) for c in cases for i in {p for u in c['units'] for p in range(u['start'], u['end'])})),
        'observed_no_occurrences': len(no_particles), 'marked_no_occurrences': sum(p['marked'] for p in no_particles),
        'one_character_evaluable_samples': len(one_character),
        'one_character_default_character_overlap': sum(c['default_character_overlap'] for c in one_character),
        'one_character_default_word_overlap': sum(c['default_word_overlap'] for c in one_character),
        'one_character_word_correct_character_wrong_ids': [c['id'] for c in one_character if c['default_word_correct_but_character_disjoint']],
        'one_character_mark_at_line_start_count': sum(c['units'][0]['line_initial'] for c in one_character),
        'one_character_mark_at_title_start_count': sum(c['units'][0]['title_initial'] for c in one_character),
        'one_character_mark_at_title_end_count': sum(c['units'][0]['title_final'] for c in one_character),
        'one_chromatic_character_evaluable_samples': len(one_chromatic_character),
        'one_chromatic_character_default_character_overlap': sum(c['default_chromatic_character_overlap'] for c in one_chromatic_character),
        'one_chromatic_character_default_word_overlap': sum(c['default_chromatic_word_overlap'] for c in one_chromatic_character),
        'one_chromatic_character_word_correct_character_wrong_ids': [c['id'] for c in one_chromatic_character if c['default_chromatic_word_overlap'] and not c['default_chromatic_character_overlap']],
    }
    result = {'version': 1, 'source_review_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'method': 'Original appearance reviewed across all 82 references; morphology and occurrence statistics follow observation.',
              'appearance_warning': 'Approximate visual-label buckets, not measured saturation; muted tints are not necessarily achromatic or unimportant.',
              'coverage_warning': 'Recorded salient differences, not an exhaustive per-glyph colour segmentation. Baseline ink colour may itself be grey or tinted.',
              'token_warning': 'Sudachi B boundaries can differ from designer semantic blocks; morphology is not ground truth.',
              'intent_warning': 'Structural facts do not establish designer intent, story causality, or optimal aesthetic choices.',
              'scope': 'Research only; no engine rule, live UI, or frozen benchmark changes.',
              'annotation_corrections': corrections, 'summary': report_summary, 'cases': cases}
    (ROOT / 'analysis/color_position_study.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    write_evidence(cases)
    print(json.dumps(report_summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    run()

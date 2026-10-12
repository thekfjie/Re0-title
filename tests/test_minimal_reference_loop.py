from copy import deepcopy
from pathlib import Path
import math
import xml.etree.ElementTree as ET

import pytest

from engine.renderer import Renderer
from engine.text import JapaneseAnalyzer
from engine.layout import load_config
from experiments import minimal_reference_loop as loop


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/minimal-reference-loop'


@pytest.fixture(scope='module')
def data():
    return loop.read(ROOT / 'references/minimal_visual_groups.json')


@pytest.fixture(scope='module')
def fonts():
    return loop.get_fonts()


@pytest.fixture(scope='module')
def model():
    return loop.Ranker(loop.read(OUT / 'ranker.json'))


def test_annotation_spans_and_unknowns_are_explicit(data):
    assert len(data['titles']) == 16
    assert sum(len(t['groups']) for t in data['titles']) == 76
    for title in data['titles']:
        cursor = 0
        for group in title['groups']:
            assert group['start'] == cursor
            assert title['text'][group['start']:group['end']] == group['text']
            assert ''.join(g['text'] for g in group['glyphs']) == group['text']
            assert [g['start'] for g in group['glyphs']] == list(range(group['start'], group['end']))
            for g in group['glyphs']:
                if g['ink_bbox'] is None:
                    assert g['bbox_basis'] == 'unresolved_within_visual_group'
                assert g['font_family'] is None and g['font_size'] is None
            cursor = group['end']
        assert cursor == len(title['text'])
    repeated = next(t for t in data['titles'] if t['id'] == 's048')
    assert [g['row'] for g in repeated['groups'] if g['text'] == '始'] == [1, 3]
    # Color occurrence information lives inside groups; it is not a text-keyed map.
    assert len({g['color'] for group in repeated['groups'] for g in group['glyphs'] if g['text'] == 'ま'}) > 1


def test_fold_training_and_retrieval_inputs_exclude_query(data):
    cfg = loop.settings()
    evaluation = loop.read(OUT / 'ranker-evaluation.json')
    assert evaluation['pair_count'] == 1280
    assert evaluation['gate_passed']
    assert evaluation['macro_accuracy'] >= cfg['ranker']['gate_accuracy']
    assert evaluation['legal_accuracy'] >= cfg['ranker']['gate_legal_accuracy']
    assert min(evaluation['per_type'].values()) >= cfg['ranker']['gate_type_accuracy']
    ids = {t['id'] for t in data['titles']}
    for query in ids:
        fold = loop.read(OUT / 'ranker-folds' / (query + '.json'))
        assert set(fold['training_titles']) == ids - {query}
        assert fold['excluded_titles'] == [query]
        assert fold['training_pair_count'] == 1200
        assert sum(r['title'] == query for r in evaluation['records']) == 80


def test_single_accent_slot_is_not_duplicated_when_group_splits(data, fonts):
    cfg = loop.settings()
    ref = next(t for t in data['titles'] if t['id'] == 's011')
    query = {'groups': [{'id': 'q0', 'text': 'ア', 'start': 0, 'end': 1, 'kind': 'katakana'},
                        {'id': 'q1', 'text': 'イ', 'start': 1, 'end': 2, 'kind': 'katakana'}]}
    slots = loop.source_slots(query, ref, [([0, 1], [1])], fonts)
    glyphs = [g for slot in slots for g in loop.adapt_group(slot, fonts, 1200, 675, cfg)]
    assert len(glyphs) == 2
    assert sum(loop.color_role(g.color) == 'accent' for g in glyphs) == 1
    assert ''.join(g.text for g in glyphs) == 'アイ'


def test_unresolved_kana_preserves_common_font_scale(data, fonts):
    cfg = loop.settings()
    ref = next(t for t in data['titles'] if t['id'] == 's030')
    source = deepcopy(ref['groups'][1])
    assert all(g['ink_bbox'] is None for g in source['glyphs'])
    source['source_box'] = source['ink_bbox']; source['source_glyphs'] = source['glyphs']
    glyphs = loop.adapt_group(source, fonts, 1200, 675, cfg)
    assert max(g.size for g in glyphs) - min(g.size for g in glyphs) < 1e-8
    assert max(g.height for g in glyphs) - min(g.height for g in glyphs) > 1


def test_color_position_blindness_is_reported_not_aesthetic_success(data, model):
    original = next(t for t in data['titles'] if t['id'] == 's048')
    other = deepcopy(original)
    glyphs = other['groups'][3]['glyphs']  # まりと、: move pink from り to と.
    glyphs[1]['color'], glyphs[2]['color'] = glyphs[2]['color'], glyphs[1]['color']
    assert loop.feature_values(original) == loop.feature_values(other)
    assert model.energy(original) == model.energy(other)
    # This regression records a diagnosed limitation, not a feature claim.


def test_transfer_exclusion_and_optimizer_hard_constraints(data, fonts):
    cfg = loop.settings(); cfg['search']['steps'] = 12
    ref = next(t for t in data['titles'] if t['id'] == 's048')
    bank = [t for t in data['titles'] if t['id'] != ref['id']]
    analyzer = JapaneseAnalyzer(load_config()['rules'])
    pool, retrieved = loop.candidate_pool(ref['text'], bank, fonts, analyzer, cfg)
    assert ref['id'] not in {r['id'] for r in retrieved}
    assert all(len(l.lines) <= 2 for l in pool)  # No four-row prototype exists in this held-out bank.
    model = loop.Ranker(loop.read(OUT / 'ranker-folds/s048.json'))
    initial = max(pool, key=lambda l: model.energy(loop.layout_title(l)))
    before = Renderer().svg(initial)
    a = loop.optimize(initial, model, cfg, 72)
    b = loop.optimize(initial, model, cfg, 72)
    assert Renderer().svg(initial) == before
    assert Renderer().svg(a) == Renderer().svg(b)
    assert a.score >= model.energy(loop.layout_title(initial)) - 1e-10
    assert loop.hard_check(a, cfg)['valid']
    invading = deepcopy(a)
    leftmost = min(invading.glyphs, key=lambda g: g.x)
    leftmost.x = 1.  # Still on canvas, but outside the declared safe margin.
    assert not loop.hard_check(invading, cfg)['safe_margin']
    assert not loop.hard_check(invading, cfg)['valid']
    assert ''.join(g.text for g in a.glyphs) == ref['text']
    tree = ET.fromstring(Renderer().svg(a, transparent=True))
    assert tree.find('{http://www.w3.org/2000/svg}rect') is None
    assert tree.find('{http://www.w3.org/2000/svg}text') is None


def test_saved_optimizer_pairs_are_same_initial_candidate_and_fonts():
    result = loop.read(OUT / 'results.json')
    assert len(result['cases']) == 20
    assert result['llm_calls'] == 0
    for case in result['cases']:
        for arm in case['arms'].values():
            assert len(arm['candidates']) == 6
            assert all(c['hard_check']['valid'] for c in arm['candidates'])
        pair = case['optimizer_pair']
        final = case['arms']['optimized']['candidates'][0]
        assert pair['initial_id'] == final['metadata']['initial_id']
        assert math.isclose(pair['before_score'], final['metadata']['optimization']['initial_score'])
        assert pair['after_score'] >= pair['before_score']
        assert set(case['fold']['retrieval_titles']) == set(case['fold']['training_titles'])

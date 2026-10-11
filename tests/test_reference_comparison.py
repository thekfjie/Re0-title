"""Contracts for the full reference artifact and independent diagnostic metrics."""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image
import pytest
from experiments.reference_comparison import compare_record, glyph_positions, jaccard, summary

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/reference-benchmark'

@pytest.fixture(scope='module')
def result():
    return json.loads((OUT / 'results.json').read_text())

def test_all_reference_inputs_and_candidates_are_preserved(result):
    samples = json.loads((ROOT / 'references/dataset.json').read_text())['samples']
    catalog = json.loads((ROOT / 'references/catalog.json').read_text())
    expected = {s['id']: s['text'] for s in samples}
    assert len(expected) == 82
    assert {s['id']: s['text'] for s in catalog} == expected
    assert {s['id']: s['text'] for s in result['cases']} == expected
    assert result['target_annotations_passed_to_engine'] is False
    assert result['generation_reference_inputs'] == ['text', 'canvas_theme']
    assert result['llm_api_calls'] == 0
    for case in result['cases']:
        assert case['status'] == 'ok'
        assert len(case['candidates']) == 6
        assert [c['index'] for c in case['candidates']] == list(range(6))
        assert case['comparison_eligible'] == (case['id'] != 's069')
        for candidate in case['candidates']:
            assert ''.join(candidate['lines']) == case['text']
            assert candidate['text_integrity']
            assert ''.join(g['text'] for g in candidate['glyphs']) == ''.join(c for c in case['text'] if not c.isspace())
            assert not candidate['score_terms']['kinsoku_penalty']
            assert not candidate['score_terms']['overflow_penalty']

def test_every_download_and_reference_image_is_valid(result):
    for case in result['cases']:
        for key in ('reference_image', 'source_image'):
            with Image.open(OUT / case[key]) as image:
                assert image.size == (1200, 675)
                image.verify()
        for candidate in case['candidates']:
            with Image.open(OUT / candidate['image']) as image:
                assert image.size == (1200, 675)
                image.verify()
            svg = ET.parse(OUT / candidate['svg']).getroot()
            assert svg.tag == '{http://www.w3.org/2000/svg}svg'
            assert svg.findall('.//{http://www.w3.org/2000/svg}path')

def test_default_and_reference_assisted_results_are_distinct(result):
    assert summary(result['cases']) == result['summary']
    valid = [c for c in result['cases'] if c['comparison_eligible']]
    assert len(valid) == 81
    assert result['summary']['default_candidate']['exact_break_match_count'] == sum(c['candidates'][0]['lines'] == c['observed_lines'] for c in valid)
    assert result['summary']['six_candidate_coverage']['exact_break_match_count'] == sum(any(x['lines'] == c['observed_lines'] for x in c['candidates']) for c in valid)
    assert any(c['diagnostic_candidate'] != 0 for c in valid)
    assert sum(c['pixel_geometry_eligible'] for c in result['cases']) == 59

def test_occurrence_offsets_do_not_colour_every_repeated_character():
    a = {'source_start': 1, 'source_end': 2, 'text': 'の'}
    b = {'source_start': 3, 'source_end': 4, 'text': 'の'}
    assert glyph_positions([a, b]) == {1: a, 3: b}
    assert jaccard({1}, {3}) == 0
    assert jaccard({1}, {1, 3}) == .5
    assert jaccard(set(), set()) == 1

def test_special_images_and_group_boxes_are_not_claimed_as_character_measurements():
    record = {'metadata': {'resolved_palette': {'foreground': '#ffffff'}},
              'glyphs': [{'source_start': 0, 'source_end': 1, 'color': '#123456', 'text': '待', 'height': 100},
                         {'source_start': 1, 'source_end': 2, 'color': '#ffffff', 'text': 'ち', 'height': 50}],
              'lines': ['待ち'], 'family': 'interwoven'}
    reference = {'measurements': {'config': {'eligible_primary_black': False}},
                 'observed_lines': ['待ち'], 'layout_family': 'interwoven'}
    fine = {'units': [{'unit_kind': 'character', 'char_span': [1, 2], 'ink_height_relative_to_median_kanji': .5},
                      {'unit_kind': 'group', 'char_span': [1, 2], 'ink_height_relative_to_median_kanji': 10}]}
    compared = compare_record(record, reference, {'accent_units': [{'start': 0, 'end': 1}]}, fine)
    assert compared['geometry'] is None
    assert compared['fine_height']['measured_character_count'] == 1
    assert math.isclose(compared['fine_height']['ink_height_mean_absolute_log_error'], 0)
    assert compared['accent_position_jaccard'] == 1

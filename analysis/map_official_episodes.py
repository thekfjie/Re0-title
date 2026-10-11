"""Match the visible reference transcription to primary episode metadata.

Only titles, episode IDs and source URLs are stored. Official synopsis prose is
not copied into the repository. Punctuation-normalized matches stay labelled.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PAGES = ['https://re-zero-anime.jp/tv/story/tv1r.html',
         'https://re-zero-anime.jp/tv/story/tv2.html',
         'https://re-zero-anime.jp/tv/story/tv3.html',
         'https://re-zero-anime.jp/tv/story/']

class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(); self.capture = None; self.parts = []; self.values = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'p' and attrs.get('class', '').startswith('ep-'):
            self.capture = attrs['class'].split()[0]; self.parts = []
        elif tag == 'br' and self.capture:
            self.parts.append('\n')
    def handle_data(self, data):
        if self.capture: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'p' and self.capture:
            self.values.setdefault(self.capture, []).append(''.join(self.parts).strip())
            self.capture = None

def read_page(url):
    data = urllib.request.urlopen(url, timeout=30).read()
    records = []
    for article in re.findall(r'<article\b[^>]*>.*?</article>', data.decode(), re.S):
        parsed = Paragraphs(); parsed.feed(article); values = parsed.values
        if not values.get('ep-subtitle'): continue
        identifier = re.search(r'<article\b[^>]*id="([^"]+)"', article)
        for title in values['ep-subtitle']:
            # A <br> is a visual wrap; a ／ separates two episode subtitles.
            variants = title.replace('\n', '').split('／')
            # Official episode 40 presents two distinct subtitles with <br>.
            # Keep their combined display string as evidence of this exception.
            if values.get('ep-label', [''])[0] == '#40': variants = title.split('\n')
            for variant in variants:
                if variant.strip():
                    records.append({'episode': values.get('ep-label', [''])[0].lstrip('#'),
                                    'title': variant.strip(), 'source_url': url,
                                    'source_anchor': identifier.group(1) if identifier else None,
                                    'synopsis_available': bool(values.get('ep-text')),
                                    'displayed_combined_title': title.replace('\n', '')})
    return {'url': url, 'sha256': hashlib.sha256(data).hexdigest(), 'records': records}

def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if not c.isspace() and c not in '・、,')

def run():
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = list(pool.map(read_page, PAGES))
    episodes = [e for page in pages for e in page['records']]
    cases = []
    for s in json.loads((ROOT/'references/dataset.json').read_text())['samples']:
        exact = [e for e in episodes if e['title'] == s['text']]
        approximate = [e for e in episodes if normalized(e['title']) == normalized(s['text'])]
        matches = exact or approximate
        basis = 'exact_title' if exact else 'punctuation_normalized' if approximate else 'not_matched'
        notes = []
        if s['id'] == 's027':
            matches = [{'episode': 'OVA', 'title': '氷結の絆', 'source_url': 'https://re-zero-anime.jp/hyoketsu/', 'source_anchor': None}]
            basis = 'official_ova_title'
        elif s['id'] == 's069':
            matches = [e for e in episodes if e['title'] == '醜悪なる晩餐会']
            basis = 'context_link_to_title_alteration'
            notes = [{'source_url': 'https://ln-news.com/articles/122598',
                      'evidence': 'Official event report names Beatrice changing the episode 65 subtitle. The image has two painted blocks and changed background/colour.',
                      'limit': 'Visible input stays ■■なる晩餐会. This is not an exact text match; no reconstruction is fed to the engine.'}]
        cases.append({'id': s['id'], 'visible_reference_text': s['text'],
                      'match_basis': basis, 'matches': matches, 'notes': notes,
                      'do_not_equate_reference_index_with_episode': True})
    result = {'version': 1, 'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
              'pages': [{k: p[k] for k in ['url', 'sha256']} for p in pages],
              'scope': 'Episode title lookup only; no claim that synopsis supplies every plot pivot or that author selected typography.',
              'cases': cases}
    (ROOT/'analysis/official_episode_map.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'exact': sum(c['match_basis']=='exact_title' for c in cases),
                      'punctuation_normalized': sum(c['match_basis']=='punctuation_normalized' for c in cases),
                      'ova': sum(c['match_basis']=='official_ova_title' for c in cases),
                      'title_alteration_context': sum(c['match_basis']=='context_link_to_title_alteration' for c in cases),
                      'not_matched': [{'id': c['id'], 'text': c['visible_reference_text']} for c in cases if not c['matches']]}, ensure_ascii=False))

if __name__ == '__main__': run()

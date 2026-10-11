"""Development-sample diagnostics, independent of engine importance/Score. No taste winner."""
from pathlib import Path
import json,math,statistics,subprocess
ROOT=Path(__file__).resolve().parents[1]
def compare(layout,ref):
 gs=layout['glyphs'];kh=statistics.median(g['height'] for g in gs if any('\u4e00'<=c<='\u9fff' for c in g['text']));by_position={};position=0;accents=set()
 for g in gs:
  for i in range(len(g['text'])):by_position[position+i]=g
  if g['color'].lower() not in ('#ffffff','#f6f5f3'):accents.update(range(position,position+len(g['text'])))
  position+=len(g['text'])
 errors=[];reference_accents=set()
 for unit in ref['units']:
  a,b=unit['char_span'];
  if unit['color_label'] not in ('white','light_gray'):reference_accents.update(range(a,b))
  if unit['unit_kind']!='character' or a not in by_position:continue
  ratio=by_position[a]['height']/kh;errors.append(abs(math.log(ratio/unit['ink_height_relative_to_median_kanji'])))
 expected=max(u['line'] for u in ref['units']);union=accents|reference_accents
 return {'ink_height_log_error':round(statistics.mean(errors),4),'line_count_error':abs(len(layout['lines'])-expected),'accent_position_jaccard':round(len(accents&reference_accents)/len(union),4) if union else 1,'family':layout['family'],'lines':layout['lines']}
def main():
 refs={s['sample_id']:s for s in json.loads((ROOT/'analysis/fine_annotations.json').read_text())['samples']}
 current=json.loads((ROOT/'experiments/live-benchmark/results.json').read_text());previous=json.loads(subprocess.check_output(['git','show','b89c38b7d9402e1086bf0ebeb20a9499dba6a9e4:experiments/benchmark/results.json'],cwd=ROOT))
 old={c['id']:c for c in previous['cases']};records=[]
 for case in current['cases']:
  ref=refs.get(case['reference_id'])
  if not ref:continue
  record={'case':case['id'],'reference':case['reference_id'],'previous_A':[compare(l,ref) for l in old[case['id']]['modes']['A']['candidates']]}
  for mode in ('A','B'):record[mode]=[compare(l,ref) for l in case['modes'][mode]['candidates']]
  records.append(record)
 out={'definition':'Absolute log error of visible ink heights, normalized by median kanji; exact fine annotations only. Lower better. Accent position Jaccard higher better. Line error lower better. Metrics are separated, never combined into an aesthetic score.','sample_status':'Development samples used for v2 tuning; not held-out evaluation. All six candidates retained; first and best are different questions.','records':records}
 (ROOT/'analysis/style_geometry.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps([{r['case']:{k:{'first':r[k][0],'best_height':min(x['ink_height_log_error'] for x in r[k]),'best_line_error':min(x['line_count_error'] for x in r[k])} for k in ('previous_A','A','B')}} for r in records],ensure_ascii=False))
if __name__=='__main__':main()

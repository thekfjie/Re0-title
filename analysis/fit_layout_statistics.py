"""Fit only observable occupancy; keep sparse families as explicit hypotheses."""
from pathlib import Path
import json,statistics,collections,yaml
ROOT=Path(__file__).resolve().parents[1]

def main():
    samples=json.loads((ROOT/'references/dataset.json').read_text())['samples'];cases=json.loads((ROOT/'experiments/benchmark_cases.json').read_text());holdout={c['reference_id'] for c in cases if c['reference_id']}
    training=[r for r in samples if r['id'] not in holdout and r['measurements']['config']['eligible_primary_black']]
    by=collections.defaultdict(list)
    for r in training:by[r['layout_family']].append(r)
    result={'held_out_reference_ids':sorted(holdout),'training_ids':[r['id'] for r in training],'families':{},'claim_limit':'Only occupancy is fitted. No token font-size or kerning measurement is inferred from connected components.'}
    rules=yaml.safe_load((ROOT/'config/template_rules.yaml').read_text())
    for family,rows in by.items():
        fills=[r['measurements']['bbox_area_fraction_of_canvas'] for r in rows]
        result['families'][family]={'count':len(rows),'box_fill_median':statistics.median(fills),'width_fraction_median':statistics.median(r['measurements']['bbox_width_fraction_of_canvas'] for r in rows),'height_fraction_median':statistics.median(r['measurements']['bbox_height_fraction_of_canvas'] for r in rows)}
        if len(rows)>=4:rules['families'][family]['fill']=round(max(.12,min(.48,statistics.median(fills))),4)
    (ROOT/'analysis/fitted_layout_statistics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'config/template_rules.yaml').write_text(yaml.safe_dump(rules,sort_keys=False,allow_unicode=True))
    print(json.dumps(result['families'],indent=2))

if __name__=='__main__':main()

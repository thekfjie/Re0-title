import test from 'node:test';import assert from 'node:assert/strict';import {spawnSync} from 'node:child_process';
import {selectAccents,validateColorSettings} from '../web/client/accent.js';
import {checkGlyphColors} from '../web/client/design.js';

const fixtures=JSON.parse(spawnSync('.venv/bin/python',['-c',`import json;from engine.layout import load_config;from engine.text import JapaneseAnalyzer;from engine.accent import select_accents;r=load_config()['rules'];a=JapaneseAnalyzer(r);texts=['聖域の終わりと、崩壊の始まり','命の価値','圣域的终结与崩坏的开始','再会と再会','レム','待ちかねた再会'];out=[]
for text in texts:
 t=a.analyze(text)
 for v in range(3):
  for n in [0,1,2]:
   p={'emphasis_relation':['の','的','再会']};c=select_accents(t,v,n,r,p);out.append({'text':text,'tokens':[x.dict() for x in t],'variant':v,'limit':n,'plan':p,'expected':[[str(i)+':'+str(j),d] for (i,j),d in c.items()]})
print(json.dumps({'rules':r,'cases':out},ensure_ascii=False))`],{encoding:'utf8'}).stdout);
test('Python and browser select the same occurrence-specific anchors across 54 plans',()=>{for(const f of fixtures.cases){const actual=[...selectAccents(f.tokens,f.variant,f.limit,fixtures.rules,f.plan)];assert.deepEqual(actual,f.expected,f.text);for(const [key] of actual){const [i,j]=key.split(':').map(Number);if(f.text.includes('的')||f.text.match(/の/g)?.length>1)assert.ok(!'の的'.includes([...f.tokens[i].text][j]));}}});
test('hex and scalar span contracts reject CSS injection and out-of-range edits',()=>{assert.equal(validateColorSettings('約束',{accents:['#ABCDEF']},[{start:1,end:2,color:'#123ABC'}]).overrides[0].color,'#123abc');assert.throws(()=>validateColorSettings('約束',{foreground:'url(x)'}));assert.throws(()=>validateColorSettings('約束',null,[{start:0,end:3,color:'#ffffff'}]));});
test('manual low-contrast colour is retained and explicitly reported',()=>{const l={text:'命',background:'#000000',resolvedPalette:{foreground:'#ffffff'},colorMode:'auto',glyphs:[{text:'命',token:0,source_start:0,source_end:1,role:'noun',importance:.9,size:40,color:'#123456',color_reason:'manual_override'}]};checkGlyphColors(l,fixtures.rules);assert.equal(l.glyphs[0].color,'#123456');assert.equal(l.colorWarnings.length,1);assert.equal(l.colorDecisions[0].start,0);});
test('unreadable automatic colour uses another readable palette hue before going monochrome',()=>{const l={text:'命',background:'#000000',resolvedPalette:{foreground:'#ffffff',accents:['#123456','#22c55e']},glyphs:[{text:'命',source_start:0,source_end:1,role:'noun',importance:.9,size:40,color:'#123456',color_reason:'content_anchor'}]};checkGlyphColors(l,fixtures.rules);assert.equal(l.glyphs[0].color,'#22c55e');assert.equal(l.glyphs[0].color_reason,'palette_contrast_substitution');});

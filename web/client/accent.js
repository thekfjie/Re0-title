// Scalar offsets identify one occurrence; repeated words are never a global replace.
const kind=c=>/[\p{Script=Han}々〆]/u.test(c)?'kanji':/\p{Script=Hiragana}/u.test(c)?'hiragana':/\p{Script=Katakana}|ー/u.test(c)?'katakana':/[0-9]/.test(c)?'number':/[a-z]/i.test(c)?'latin':/\s/.test(c)?'space':'punctuation';
export function selectAccents(tokens,variant,limit,rules,plan=null){
 const cfg=rules.accent_selection,functional=new Set(cfg.functional_words),blocked=new Set(cfg.protected_characters),chars=[];let start=0;
 tokens.forEach((t,i)=>{[...t.text].forEach((c,j)=>chars.push({i,j,c,start:start+j,t}));start+=[...t.text].length;});
 const result=new Map();if(!limit)return result;
 const text=tokens.map(t=>t.text).join(''),emphasis=new Set();
 for(const word of plan?.emphasis_relation||[]){if(!word||functional.has(word)||[...word].every(c=>blocked.has(c)))continue;const at=text.indexOf(word);if(at>=0){const scalar=[...text.slice(0,at)].length;for(let j=0;j<[...word].length;j++)emphasis.add(scalar+j);}}
 const content=[];
 tokens.forEach((t,i)=>{if(['particle','connector','punctuation'].includes(t.role)||functional.has(t.text))return;const part=chars.filter(x=>x.i===i&&!['punctuation','space'].includes(kind(x.c))&&!blocked.has(x.c));if(!part.length)return;const strong=part.filter(x=>['kanji','katakana','latin','number'].includes(kind(x.c)));let pool=strong.length?strong:part,marked=pool.filter(x=>emphasis.has(x.start));if(marked.length)pool=marked;const x={...(variant===1?pool.at(-1):pool[0])},w=cfg.weights;let value=w.importance*t.importance+(['noun','keyword','concept','verb'].includes(t.role)?w.content_role:0)+(strong.length?w.display_script:0)+(marked.length?w.planner:0)+(cfg.contrast_concepts.some(word=>t.text.includes(word))?w.contrast_concept:0)+([0,tokens.length-1].includes(i)?w.edge:0);content.push({...x,score:value,reason:marked.length?'planner_anchor':'content_anchor'});});
 content.sort((a,b)=>b.score-a.score||a.start-b.start);const selected=[],bridges=chars.filter(x=>x.c==='の'&&x.t.text==='の');
 if(variant===1&&[...text].length<=cfg.bridge_max_chars&&bridges.length===1&&content.length===2){const x=bridges[0];if(x.start>0&&x.start<[...text].length-1)selected.push({...x,score:cfg.bridge_visual_score,reason:'short_visual_bridge'});}
 for(const x of content){if(selected.length>=limit)break;if(selected.some(y=>x.t.text===y.t.text||Math.abs(x.start-y.start)<cfg.min_anchor_distance))continue;selected.push(x);}
 if(selected.length<limit&&content.length===1){const first=selected[0]||content[0],alternatives=chars.filter(x=>x.i===first.i&&!['punctuation','space'].includes(kind(x.c))&&!blocked.has(x.c)&&Math.abs(x.start-first.start)>=cfg.min_anchor_distance);if(alternatives.length)selected.push({...alternatives.at(-1),score:first.score,reason:'word_edge_contrast'});}
 selected.slice(0,limit).forEach((x,rank)=>result.set(x.i+':'+x.j,{rank,reason:x.reason,salience:Math.min(1,x.score)}));return result;
}
export function validateColorSettings(text,custom=null,overrides=[]){
 const color=v=>{if(typeof v!=='string'||!/^#[0-9a-f]{6}$/i.test(v))throw new Error('颜色须为 #RRGGBB');return v.toLowerCase();};let clean=null;
 if(custom!==null){if(typeof custom!=='object'||Array.isArray(custom)||Object.keys(custom).some(k=>!['foreground','accents'].includes(k)))throw new Error('自定义配色格式无效');clean={};if('foreground'in custom)clean.foreground=color(custom.foreground);if('accents'in custom){if(!Array.isArray(custom.accents)||custom.accents.length<1||custom.accents.length>8)throw new Error('自定义强调色须为 1–8 种');clean.accents=custom.accents.map(color);}}
 if(!Array.isArray(overrides)||overrides.length>80)throw new Error('局部颜色数量超限');const spans=overrides.map(x=>{if(!x||Object.keys(x).sort().join(',')!=='color,end,start'||!Number.isInteger(x.start)||!Number.isInteger(x.end)||x.start<0||x.start>=x.end||x.end>[...text].length)throw new Error('局部颜色范围须对应排版文本');return {...x,color:color(x.color)};});return {custom:clean,overrides:spans};
}

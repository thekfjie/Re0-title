import {initTheme} from './theme.js';
initTheme();
const $=s=>document.querySelector(s),pageSize=8,selected=new Map();let data,filtered=[],page=0;
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function picture(src,text){const img=new Image();img.src=src;img.alt=text;img.loading='lazy';img.tabIndex=0;const zoom=()=>{$('#study-zoom img').src=src;$('#study-zoom').showModal();};img.onclick=zoom;img.onkeydown=e=>{if(e.key==='Enter')zoom();};return img;}
function draw(){const list=$('#study-list');list.replaceChildren();for(const c of filtered.slice(page*pageSize,(page+1)*pageSize)){
 const card=el('section','reference-case');card.dataset.case=c.id;const heading=el('div','reference-case-heading');heading.append(el('h2','',c.id+' · '+c.text));card.append(heading);const row=el('div','composition-triplet');
 if(c.reference){const original=el('div','reference-original');original.append(el('h3','','原始参考'),picture('/reference-benchmark/'+c.id+'/reference.jpg','原始参考 '+c.text));row.append(original);}
 for(const [name,label] of [['previous','现版'],['composition','构图实验']]){const column=el('div','reference-generated'),key=c.id+':'+name,index=selected.get(key)||0,candidate=c.arms[name].candidates[index],base='/composition-study/';column.dataset.arm=name;column.append(el('h3','',label+' · '+(index+1)),picture(base+candidate.image,label+' '+c.text),el('div','reference-lines',candidate.lines.join(' / ')));
 const thumbs=el('div','reference-thumbnails');c.arms[name].candidates.forEach((x,i)=>{const b=el('button',i===index?'active':'');b.type='button';b.setAttribute('aria-label',c.id+' '+label+' 候选 '+(i+1));b.setAttribute('aria-pressed',String(i===index));const im=new Image();im.src=base+x.image;im.alt='';im.loading='lazy';b.append(im,el('span','',String(i+1)));b.onclick=()=>{selected.set(key,i);draw();};thumbs.append(b);});column.append(thumbs);
 const downloads=el('div','reference-downloads');for(const [kind,file] of [['PNG',candidate.image],['SVG',candidate.svg]]){const a=el('a','text-button',kind);a.href=base+file;a.download=c.id+'-'+name+'-'+(index+1)+'.'+kind.toLowerCase();downloads.append(a);}column.append(downloads);row.append(column);}
 card.append(row);list.append(card);
 }
 if(!filtered.length)list.append(el('p','empty-state','没有匹配标题'));const pages=Math.max(1,Math.ceil(filtered.length/pageSize));$('#study-status').textContent=filtered.length+' 条标题';$('#study-page').textContent=(page+1)+' / '+pages;$('#study-previous').disabled=page===0;$('#study-next').disabled=page+1>=pages;
}
function filter(){const q=$('#study-search').value.trim().toLowerCase(),kind=$('#study-filter').value;filtered=data.cases.filter(c=>(!q||(c.id+' '+c.text).toLowerCase().includes(q))&&(!kind||kind==='reference'&&c.reference||kind==='unseen'&&!c.reference));page=0;draw();}
$('#study-search').oninput=filter;$('#study-filter').onchange=filter;$('#study-previous').onclick=()=>{page--;draw();window.scrollTo({top:0,behavior:'instant'});};$('#study-next').onclick=()=>{page++;draw();window.scrollTo({top:0,behavior:'instant'});};$('#study-zoom-close').onclick=()=>$('#study-zoom').close();$('#study-zoom').onclick=e=>{if(e.target===$('#study-zoom'))$('#study-zoom').close();};
try{const response=await fetch('/composition-study/index.json');if(!response.ok)throw new Error('实验加载失败');data=await response.json();$('#study-search').value=new URLSearchParams(location.search).get('reference')||'';filter();}catch(e){$('#study-status').textContent=e.message;}

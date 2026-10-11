const labels={compact_anchor:'紧凑锚点',interwoven:'大小交织',wide_block:'横向字块',offset_stack:'错位堆叠',alternating_steps:'交替阶梯'};
export function initReferencePicker(catalog,onChoose){
 const dialog=document.querySelector('#reference-dialog'),list=document.querySelector('#reference-list'),search=document.querySelector('#reference-search'),family=document.querySelector('#reference-family'),count=document.querySelector('#reference-count');
 for(const [value,label] of Object.entries(labels))family.append(new Option(label,value));
 function draw(){const query=search.value.trim().toLocaleLowerCase(),matches=catalog.filter(s=>(!family.value||s.observed_family===family.value)&&(!query||(s.id+' '+s.text).toLocaleLowerCase().includes(query)));list.replaceChildren();count.textContent=matches.length+' / '+catalog.length;
  for(const s of matches){const button=document.createElement('button');button.type='button';button.className='reference-option';button.dataset.reference=s.id;const image=new Image();image.src='/reference-benchmark/'+s.reference_image;image.alt='';image.loading='lazy';const body=document.createElement('span'),id=document.createElement('strong'),title=document.createElement('span');id.textContent=s.id.slice(1);title.textContent=s.text;body.append(id,title);button.append(image,body);if(!s.comparison_eligible){const badge=document.createElement('span');badge.className='badge';badge.textContent='部分遮挡';body.append(badge);}button.onclick=()=>{dialog.close();onChoose(s);};list.append(button);}
  if(!matches.length){const empty=document.createElement('p');empty.className='empty-state';empty.textContent='没有匹配标题';list.append(empty);}
 }
 document.querySelector('#reference-open').onclick=()=>{draw();dialog.showModal();search.focus();};document.querySelector('#reference-close').onclick=()=>dialog.close();dialog.onclick=e=>{if(e.target===dialog)dialog.close();};search.oninput=draw;family.onchange=draw;draw();
 return {find:id=>catalog.find(s=>s.id===id)};
}

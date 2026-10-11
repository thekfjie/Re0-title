const $=s=>document.querySelector(s),text=$('#text'),status=$('#status'),gallery=$('#gallery');
const families={compact_anchor:'紧凑锚点',interwoven:'大小交织',wide_block:'横向字块',offset_stack:'错位堆叠',alternating_steps:'交替阶梯'};
const roles={keyword:'关键词',noun:'名词',verb:'动词',modifier:'修饰',particle:'助词',connector:'连接',punctuation:'标点',concept:'概念',other:'其他'};
let mode='classic',palette='night',worker,ready=false,busy=false,backend=false,llmAvailable=false,sequence=0,operation=0,selected=0,results=[],resultMode='classic',snapshot=null,knownPlans=[],catalog=[],fontIds={},nativeFiles={},fontLoaded={},pending=new Map(),urls=[],cache=new Map(),semanticCache=new Map(),controller;
function message(value,error=false){status.textContent=value;status.classList.toggle('error',error);}
function options(){return {text:text.value,mode,palette,seed:Number($('#seed').value),count:Number($('#count').value),width:Number($('#width').value),height:Number($('#height').value),transparent:$('#transparent').checked};}
function fingerprint(){return JSON.stringify({...options(),fonts:[$('#kanji-select').value,$('#kana-select').value],uploads:Object.fromEntries(Object.entries(nativeFiles).map(([k,v])=>[k,v.name+v.size+v.lastModified]))});}
function matchingPlan(){return knownPlans.find(p=>p.text===text.value)?.plan;}
function canGenerate(){return ready&&fontLoaded.kanji&&fontLoaded.kana&&text.value.trim()&&(mode==='classic'||llmAvailable||(!backend&&matchingPlan()));}
function updateButtons(){
 $('#generate').disabled=busy||!canGenerate();$('#shuffle').disabled=busy||!canGenerate();
 for(const id of ['download-png','download-svg','fullscreen'])$('#'+id).disabled=busy||!results.length;
 $('#previous').disabled=busy||selected<=0;$('#next').disabled=busy||selected>=results.length-1;$('#parameters').hidden=!results.length;
}
function loading(value,label='搜索布局候选'){$('#preview').classList.toggle('loading',value);$('#preview-loading').hidden=!value;$('#progress-text').textContent=label;}
function setBusy(value,label){busy=value;$('#generate').innerHTML=value?'生成中…':'生成候选 <span aria-hidden="true">↗</span>';$('#cancel').hidden=!value;for(const el of $('#form').querySelectorAll('input,select,textarea,button'))if(!['cancel','upload-toggle'].includes(el.id))el.disabled=value;updateButtons();if(value)loading(true,label);else loading(false);}
function modeNote(){
 const note=$('#mode-note');note.hidden=mode==='classic'||llmAvailable;
 if(!note.hidden){note.replaceChildren();const p=document.createElement('span');p.textContent=matchingPlan()&&!backend?'当前使用固定语义计划。实时 LLM 尚未连接。':'实时 LLM 尚未连接。B 的固定计划实验支持下方示例标题。';note.append(p);}
 updateButtons();
}
function dirty(){if(snapshot)$('#stale').hidden=fingerprint()===snapshot;cache.clear();modeNote();}
function revoke(){urls.forEach(u=>URL.revokeObjectURL(u));urls=[];}
function url(blob){const value=URL.createObjectURL(blob);urls.push(value);return value;}
function request(type,args={},transfer=[]){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(new Error('引擎超时，请重试'));},60000);pending.set(id,{resolve,reject,timer});worker.postMessage({id,type,...args},transfer);});}
function initWorker(){
 ready=false;worker=new Worker('/worker.js');
 return new Promise((resolve,reject)=>{
  worker.onmessage=e=>{const data=e.data;if(data.type==='ready'){ready=true;resolve();return;}if(data.type==='startup-error'){reject(new Error(data.message));return;}const item=pending.get(data.id);if(item){clearTimeout(item.timer);pending.delete(data.id);data.type==='error'?item.reject(new Error(data.message)):item.resolve(data);}};
  worker.onerror=e=>{reject(new Error(e.message||'字体引擎启动失败'));message('字体引擎出错，请刷新重试',true);};
 });
}
async function api(path,init={}){const r=await fetch(path,init);let payload;try{payload=await r.json();}catch{throw new Error('服务返回了无效响应');}if(!r.ok)throw new Error(typeof payload.detail==='string'?payload.detail:typeof payload.error==='string'?payload.error:'服务请求失败');return payload;}
function fillSelectors(){for(let role of ['kanji','kana']){const select=$('#'+role+'-select');select.replaceChildren();for(let font of catalog){const option=new Option(font.label,font.id);select.append(option);}if(role==='kana')select.prepend(new Option('与汉字相同','same'));select.value=role==='kanji'?'noto-sans-jp-black':'shippori-mincho-semibold';}}
function selectedFont(role){const value=$('#'+role+'-select').value;return role==='kana'&&value==='same'?$('#kanji-select').value:value;}
async function loadFont(role){
 fontLoaded[role]=false;const id=selectedFont(role);let meta;
 if(id==='uploaded-kanji'||id==='uploaded-kana'){
  const original=id.endsWith('kana')?'kana':'kanji',file=nativeFiles[original];if(!file)throw new Error('上传字体已清除');
  if(backend){fontIds[role]=fontIds['uploaded-'+original];meta={family:file.name};}
  else{const bytes=await file.arrayBuffer();meta=(await request('font',{role,data:bytes,name:file.name},[bytes])).metadata;}
 }else{
  const font=catalog.find(f=>f.id===id);if(!font)throw new Error('字体选择无效');
  if(backend){fontIds[role]='builtin_'+id;meta={family:font.label};}
  else{const r=await fetch('/open-fonts/'+font.file);if(!r.ok)throw new Error('默认字体加载失败，请重试');const bytes=await r.arrayBuffer();meta=(await request('font',{role,data:bytes,name:font.file},[bytes])).metadata;}
 }
 fontLoaded[role]=true;return meta;
}
async function loadSelection(){await loadFont('kanji');await loadFont('kana');updateButtons();}
function drawPlan(plan){$('#semantic-panel').hidden=!plan;const body=$('#semantic-content');body.replaceChildren();if(!plan)return;const container=document.createElement('div');container.className='semantic-tokens';for(let t of plan.tokens){const chip=document.createElement('div');chip.className='semantic-token';const word=document.createElement('span'),info=document.createElement('small');word.textContent=t.text;info.textContent=(roles[t.semantic_role]||t.semantic_role)+' · '+t.importance.toFixed(2);chip.append(word,info);container.append(chip);}body.append(container);}
function select(index){
 if(!results[index])return;selected=index;const item=results[index];$('#preview-image').src=item.previewUrl;$('#preview-image').hidden=false;$('#preview-title').textContent='预览';$('#selected-label').textContent='候选 '+String(index+1).padStart(2,'0')+' · '+families[item.family];$('#canvas-label').textContent=item.width+' × '+item.height;$('#preview').style.aspectRatio=item.width+'/'+item.height;gallery.querySelectorAll('.candidate').forEach((card,i)=>{card.classList.toggle('active',i===index);card.setAttribute('aria-pressed',String(i===index));});updateButtons();
}
function showResults(items,plan,renderOptions){
 revoke();results=items.map(item=>({...item,renderOptions,previewUrl:item.png_url||url(new Blob([item.svg],{type:'image/svg+xml'}))}));resultMode=renderOptions.mode;gallery.replaceChildren();$('#result-count').textContent=results.length;$('#provenance').hidden=false;$('#provenance').textContent=resultMode==='classic'?'A · 传统算法':plan?.provenance?.startsWith('live_')?'B · 实时 LLM':'B · 固定计划';
 results.forEach((item,i)=>{const card=document.createElement('button');card.type='button';card.className='candidate';card.setAttribute('aria-label','候选 '+String(i+1).padStart(2,'0')+' · '+families[item.family]);const img=new Image();img.src=item.previewUrl;img.alt=item.text;const foot=document.createElement('div');foot.className='candidate-foot';const label=document.createElement('strong'),name=document.createElement('span');label.textContent=String(i+1).padStart(2,'0');name.textContent=families[item.family];foot.append(label,name);card.append(img,foot);card.onclick=()=>select(i);gallery.append(card);});drawPlan(plan);select(0);$('#stale').hidden=true;
}
async function generate(force=false){
 if(busy||!canGenerate())return;const current=++operation,key=fingerprint(),o=options();
 if(!Number.isInteger(o.seed)||o.seed<0||o.seed>2147483647){message('Seed 须为 0–2147483647 的整数',true);return;}
 if(!Number.isInteger(o.width)||!Number.isInteger(o.height)||o.width<256||o.height<256||o.width>2400||o.height>2400||o.width*o.height>4000000){message('宽高须为 256–2400 像素，总像素不超过 400 万',true);return;}
 if(cache.has(key)&&!force){const hit=cache.get(key);showResults(hit.items,hit.plan,o);snapshot=key;message('');return;}
 controller=new AbortController();setBusy(true,mode==='llm'&&llmAvailable&&!semanticCache.has(o.text)?'分析日文语义':'搜索断行与字形布局');message('');
 try{
  let data,items,plan;
  if(backend){data=await api('/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...o,fonts:{kanji:fontIds.kanji,kana:fontIds.kana}}),signal:controller.signal});items=data.candidates;plan=data.planner;}
  else{
   if(mode==='llm'&&llmAvailable){plan=semanticCache.get(o.text);if(!plan){const preliminary=(await request('analyze',{text:o.text})).tokens;plan=(await api('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:o.text,tokens:preliminary}),signal:controller.signal})).plan;if(semanticCache.size>=32)semanticCache.clear();semanticCache.set(o.text,plan);}}
   data=await request('render',{options:o,plan});items=data.results;plan=data.plan;
  }
  if(current!==operation)return;cache.set(key,{items,plan});showResults(items,plan,o);snapshot=key;message('');
 }catch(e){if(current===operation&&e.name!=='AbortError')message(e.message,true);}
 finally{if(current===operation)setBusy(false);}
}
async function png(svg,width,height){const value=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));try{const img=new Image();img.src=value;await img.decode();const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;canvas.getContext('2d').drawImage(img,0,0);return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG 导出失败')),'image/png'));}finally{URL.revokeObjectURL(value);}}
function download(blob,name){const value=URL.createObjectURL(blob),a=document.createElement('a');a.href=value;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(value),1000);}
async function exportSelected(format){const item=results[selected];if(!item)return;try{const safe={...item};delete safe.previewUrl;const blob=format==='JSON'?new Blob([JSON.stringify(safe,null,2)],{type:'application/json'}):item.png_url?await fetch(format==='PNG'?item.png_url:item.svg_url).then(r=>{if(!r.ok)throw new Error('结果已过期，请重新生成');return r.blob();}):format==='SVG'?new Blob([item.svg],{type:'image/svg+xml'}):await png(item.svg,item.width,item.height);download(blob,'title-'+(resultMode==='classic'?'A':'B')+'-'+(selected+1)+'-seed'+item.renderOptions.seed+'.'+format.toLowerCase());}catch(e){message(e.message,true);}}
function openZoom(){if(!results[selected])return;$('#zoom-dialog img').src=results[selected].previewUrl;$('#zoom-dialog').showModal();}
$('#form').onsubmit=e=>{e.preventDefault();generate(true);};
text.oninput=()=>{$('#length').textContent=[...text.value].length+' / 80';dirty();};text.oninput();
text.onkeydown=e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();generate(true);}};
document.querySelectorAll('[data-text]').forEach(b=>b.onclick=()=>{text.value=b.dataset.text;text.oninput();generate();});
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(el=>{el.classList.toggle('active',el===b);el.setAttribute('aria-selected',String(el===b));});modeNote();if(snapshot)$('#stale').hidden=fingerprint()===snapshot;generate();});
document.querySelectorAll('[data-palette]').forEach(b=>b.onclick=()=>{palette=b.dataset.palette;document.querySelectorAll('[data-palette]').forEach(el=>{el.classList.toggle('active',el===b);el.setAttribute('aria-pressed',String(el===b));});dirty();generate();});
for(let id of ['seed','width','height'])$('#'+id).onchange=dirty;for(let id of ['count','transparent'])$('#'+id).onchange=()=>{dirty();generate();};
for(let role of ['kanji','kana'])$('#'+role+'-select').onchange=async()=>{dirty();const current=++operation;setBusy(true,'加载字体');try{await loadFont(role);if(role==='kanji'&&$('#kana-select').value==='same')await loadFont('kana');}catch(e){message(e.message,true);}finally{if(current===operation)setBusy(false);}generate();};
for(let role of ['kanji','kana'])$('#'+role).onchange=async e=>{
 const file=e.target.files[0];if(!file)return;const current=++operation,previousFile=nativeFiles[role],previousSelection=$('#'+role+'-select').value;setBusy(true,'解析上传字体');
 try{if(file.size>24*1024*1024)throw new Error('字体上限 24 MiB');if(backend){const body=new FormData();body.append('file',file);const data=await api('/fonts',{method:'POST',body});fontIds['uploaded-'+role]=data.font_id;}nativeFiles[role]=file;const select=$('#'+role+'-select');select.querySelector('option[value="uploaded-'+role+'"]')?.remove();select.append(new Option(file.name,'uploaded-'+role));select.value='uploaded-'+role;$('#'+role+'-name').textContent=file.name;await loadFont(role);if(role==='kanji'&&$('#kana-select').value==='same')await loadFont('kana');dirty();}
 catch(e){if(current===operation){if(previousFile)nativeFiles[role]=previousFile;else delete nativeFiles[role];$('#'+role+'-select').value=previousSelection;$('#'+role+'-name').textContent=previousFile?previousFile.name:'TTF / OTF · 24 MiB';try{await loadFont(role);}catch{}message(e.message,true);}return;}finally{if(current===operation)setBusy(false);}if(current===operation&&fontLoaded[role])generate();
};
$('#upload-toggle').onclick=()=>{$('#uploads').hidden=!$('#uploads').hidden;$('#upload-toggle').setAttribute('aria-expanded',String(!$('#uploads').hidden));};
$('#clear').onclick=async()=>{setBusy(true,'恢复默认字体');try{if(backend)await api('/fonts',{method:'DELETE'});else await request('clear');nativeFiles={};fontIds={};fillSelectors();for(let role of ['kanji','kana']){$('#'+role).value='';$('#'+role+'-name').textContent='TTF / OTF · 24 MiB';}await loadSelection();dirty();message('上传字体已清除');}catch(e){message(e.message,true);}finally{setBusy(false);}generate();};
$('#shuffle').onclick=()=>{$('#seed').value=Math.floor(Math.random()*2147483647);dirty();generate(true);};
$('#cancel').onclick=async()=>{
 ++operation;controller?.abort();if(worker){worker.terminate();for(let item of pending.values()){clearTimeout(item.timer);item.reject(new DOMException('已取消','AbortError'));}pending.clear();}setBusy(false);loading(false);message('已取消');
 if(!backend){ready=false;updateButtons();try{await initWorker();await loadSelection();message('');updateButtons();}catch(e){message(e.message,true);}}
};
$('#download-png').onclick=()=>exportSelected('PNG');$('#download-svg').onclick=()=>exportSelected('SVG');$('#parameters').onclick=()=>exportSelected('JSON');$('#fullscreen').onclick=openZoom;$('#preview-image').onclick=openZoom;$('#zoom-close').onclick=()=>$('#zoom-dialog').close();$('#zoom-dialog').onclick=e=>{if(e.target===$('#zoom-dialog'))$('#zoom-dialog').close();};$('#previous').onclick=()=>select(selected-1);$('#next').onclick=()=>select(selected+1);
$('#semantic-replan').onclick=()=>{semanticCache.delete(text.value);cache.clear();generate(true);};
$('#semantic-toggle').onclick=()=>{const open=$('#semantic-content').hidden;$('#semantic-content').hidden=!open;$('#semantic-toggle').setAttribute('aria-expanded',String(open));$('#semantic-toggle span').textContent=open?'−':'＋';};
document.addEventListener('keydown',e=>{if(!['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)&&!busy&&!$('#zoom-dialog').open){if(e.key==='ArrowLeft')select(Math.max(0,selected-1));if(e.key==='ArrowRight')select(Math.min(results.length-1,selected+1));}});
for(let i=0;i<6;i++){const skeleton=document.createElement('div');skeleton.className='candidate skeleton';gallery.append(skeleton);}
try{
 const [info,plans,fonts]=await Promise.all([fetch('/api/status').then(r=>r.ok?r.json():{}).catch(()=>({})),fetch('/session-plans.json').then(r=>r.json()),fetch('/open-fonts/catalog.json').then(r=>r.json())]);backend=info.service==='python-harfbuzz';llmAvailable=!!info.llm_available;knownPlans=plans;catalog=fonts;fillSelectors();modeNote();
 if(backend){ready=true;$('#privacy-note').textContent='上传字体仅限当前会话，'+Math.round(info.font_ttl_seconds/60)+' 分钟后删除。请确认拥有使用权。';}else{await initWorker();$('#privacy-note').textContent='上传字体仅在本机处理。请确认拥有使用权。';}
 loading(true,'加载默认字体');await loadSelection();loading(false);message('');await generate();
}catch(e){loading(false);message(e.message,true);}
window.addEventListener('pagehide',()=>{revoke();worker?.terminate();controller?.abort();});

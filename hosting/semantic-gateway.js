import contract from '../llm/planner_contract.json' with {type:'json'};
import reference from '../analysis/family_summary.json' with {type:'json'};
import translation from '../llm/translation_contract.json' with {type:'json'};
export function validatePlan(text,plan){
 const keys=['tokens','suggested_layout_family','emphasis_relation'];if(!plan||Object.keys(plan).some(k=>!keys.includes(k))||keys.some(k=>!(k in plan)))throw new Error('语义计划包含未经允许字段');
 if(!contract.schema.properties.suggested_layout_family.enum.includes(plan.suggested_layout_family))throw new Error('未知布局家族');
 if(!Array.isArray(plan.tokens)||!plan.tokens.length||plan.tokens.length>80||plan.tokens.map(t=>t.text).join('')!==text)throw new Error('语义计划改写或遗漏原文');
 for(const t of plan.tokens){if(Object.keys(t).sort().join(',')!=='importance,semantic_role,text,visual_role'||typeof t.text!=='string'||!t.text||!contract.schema.properties.tokens.items.properties.semantic_role.enum.includes(t.semantic_role)||!['primary','secondary','connector'].includes(t.visual_role)||!Number.isFinite(t.importance)||t.importance<0||t.importance>1)throw new Error('无效语义 token');}
 if(!Array.isArray(plan.emphasis_relation)||plan.emphasis_relation.length>4||plan.emphasis_relation.some(t=>typeof t!=='string'||!t||[...t].length>8||!text.includes(t)))throw new Error('无效强调关系');return plan;
}
async function structuredRequest(system,user,responseSchema,name,env,fetcher=fetch){
 const key=env.LLM_API_KEY||env.OPENAI_API_KEY;if(!key)throw new Error('B 尚未配置服务端密钥');
 const base=(env.LLM_BASE_URL||'https://api.openai.com/v1').replace(/\/$/,''),endpoint=new URL(base);
 if(endpoint.protocol!=='https:'||endpoint.username||endpoint.password)throw new Error('LLM_BASE_URL 须为无凭证的 HTTPS 地址');
 const style=env.LLM_API_STYLE||(env.LLM_BASE_URL?'chat_completions':'responses'),jsonMode=env.LLM_JSON_MODE||'json_schema',model=env.LLM_MODEL||'gpt-4.1-mini';
 if(!['chat_completions','responses'].includes(style)||!['json_schema','json_object'].includes(jsonMode))throw new Error('LLM 接口配置无效');
 const messages=[{role:'system',content:system},{role:'user',content:JSON.stringify(user)}],schema={name,strict:true,schema:responseSchema};
 const body=style==='chat_completions'?{model,messages,max_tokens:4096,response_format:jsonMode==='json_schema'?{type:'json_schema',json_schema:schema}:{type:'json_object'}}:{model,input:messages,max_output_tokens:4096,store:false,text:{format:jsonMode==='json_schema'?{type:'json_schema',...schema}:{type:'json_object'}}};
 if(/^gpt-[56]/.test(model)){if(style==='chat_completions'){body.max_completion_tokens=body.max_tokens;delete body.max_tokens;body.reasoning_effort=env.LLM_REASONING_EFFORT||'low';}else body.reasoning={effort:env.LLM_REASONING_EFFORT||'low'};}
 const start=Date.now(),response=await fetcher(base+(style==='chat_completions'?'/chat/completions':'/responses'),{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(35000)});
 if(!response.ok)throw new Error('LLM 接口返回 '+response.status+'，请检查模型与配额');
 const payload=await response.json(),output=style==='chat_completions'?payload.choices?.[0]?.message?.content:payload.output?.flatMap(o=>o.content||[]).filter(c=>c.type==='output_text').map(c=>c.text).join('');let data;try{data=JSON.parse(output);}catch{throw new Error('LLM 未返回完整 JSON');}return {data,metadata:{provenance:'live_'+style,model,usage:payload.usage,request_id:payload.id,api_latency_ms:Date.now()-start}};
}
export async function semanticPlan(text,tokens,env,fetcher=fetch){const {data,metadata}=await structuredRequest(contract.system,{text,morphology:tokens,reference_families:reference},contract.schema,'japanese_title_plan',env,fetcher);validatePlan(text,data);return {...data,...metadata};}
export function validateTranslation(data){if(!data||Object.keys(data).join(',')!=='japanese_text'||typeof data.japanese_text!=='string'||!data.japanese_text.trim()||[...data.japanese_text].length>80||/[\x00-\x1f]/.test(data.japanese_text))throw new Error('译文须为 1–80 字符的单行标题');return data.japanese_text;}
export async function translateTitle(text,env,fetcher=fetch){const {data,metadata}=await structuredRequest(translation.system,{source_text:text},translation.schema,'japanese_title_translation',env,fetcher),target=validateTranslation(data);return {source_text:text,text:target,changed:text!==target,...metadata,provenance:metadata.provenance.replace('live_','live_translation_')};}
const rates=new Map();
export async function handlePlanner(request,env,task='plan'){
 const respond=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
 if(request.method!=='POST')return respond({error:'需要 POST'},405);
 const origin=request.headers.get('Origin');if(origin&&origin!==new URL(request.url).origin)return respond({error:'请求来源不匹配'},403);
 if(!(env.LLM_API_KEY||env.OPENAI_API_KEY))return respond({error:'B 尚未配置服务端密钥'},503);
 const id=request.headers.get('CF-Connecting-IP')||'private-owner',now=Date.now(),events=(rates.get(id)||[]).filter(t=>now-t<60000);if(events.length>=8)return respond({error:'每分钟最多 8 次语义请求'},429);if(rates.size>1024)rates.clear();rates.set(id,[...events,now]);
 try{
  if(Number(request.headers.get('Content-Length'))>32768)return respond({error:'请求过大'},413);
  const reader=request.body?.getReader();if(!reader)return respond({error:'缺少请求体'},400);let chunks=[],size=0;while(true){let {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>32768){await reader.cancel();return respond({error:'请求过大'},413);}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(let c of chunks){bytes.set(c,offset);offset+=c.length;}const body=JSON.parse(new TextDecoder().decode(bytes));
  if(typeof body.text!=='string'||!body.text.trim()||[...body.text].length>80||/[\x00-\x1f]/.test(body.text))return respond({error:'请输入 1–80 字符的单行标题'},422);
  if(task==='translate')return respond({translation:await translateTitle(body.text,env)});
  if(!Array.isArray(body.tokens)||body.tokens.length>80||body.tokens.map(t=>t.text).join('')!==body.text)return respond({error:'无效分词'},422);
  return respond({plan:await semanticPlan(body.text,body.tokens,env)});
 }catch(e){return respond({error:e.name==='TimeoutError'?'语义服务超时':e.message},422);}
}
export const handleTranslation=(request,env)=>handlePlanner(request,env,'translate');

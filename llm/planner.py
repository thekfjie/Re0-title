import os,json,time,math
import httpx
from pathlib import Path
from engine.text import Token

FAMILIES=['compact_anchor','interwoven','wide_block','offset_stack','alternating_steps']
ROLES=['keyword','noun','verb','modifier','particle','connector','punctuation','concept','other']
SCHEMA={'type':'object','properties':{
 'tokens':{'type':'array','minItems':1,'maxItems':80,'items':{'type':'object','properties':{'text':{'type':'string'},'semantic_role':{'type':'string','enum':ROLES},'importance':{'type':'number','minimum':0,'maximum':1},'visual_role':{'type':'string','enum':['primary','secondary','connector']}},'required':['text','semantic_role','importance','visual_role'],'additionalProperties':False}},
 'suggested_layout_family':{'type':'string','enum':FAMILIES},
 'emphasis_relation':{'type':'array','maxItems':4,'items':{'type':'string'}}},
 'required':['tokens','suggested_layout_family','emphasis_relation'],'additionalProperties':False}

SYSTEM='''你是日文标题的语义规划器。保留输入原文、标点和字符顺序。分析 Sudachi 分词，按需纠正；选择语义锚点、助词与连接部分。输出严格符合 schema 的 JSON。不得输出绝对坐标、字体文件、SVG 或图片。主词不必都高重要度，平假名可因语义成为强调点。emphasis_relation 仅包含输入中实际出现的短子串，最多四项。优先数据中有限家族，不新增家族。'''
TRANSLATION=json.loads((Path(__file__).parent/'translation_contract.json').read_text())

def validate_translation(payload):
    if not isinstance(payload,dict) or set(payload)!={'japanese_text'}:raise ValueError('翻译响应字段不匹配')
    text=payload['japanese_text']
    if not isinstance(text,str) or not text.strip() or len(text)>80 or any(ord(c)<32 for c in text):raise ValueError('译文须为 1–80 字符的单行标题')
    return text

def validate_plan(text,plan):
    if not isinstance(plan,dict) or set(plan)-set(SCHEMA['properties'])-{'provenance','usage','api_latency_ms','model','request_id'}:raise ValueError('计划包含未经允许字段')
    if plan.get('suggested_layout_family') not in FAMILIES:raise ValueError('未知布局家族')
    raw=plan.get('tokens')
    if not isinstance(raw,list) or not 1<=len(raw)<=80:raise ValueError('无效 tokens')
    if ''.join(t.get('text','') for t in raw)!=text:raise ValueError('LLM 改写、遗漏或调换了输入文字')
    tokens=[];start=0
    for t in raw:
        if set(t)!= {'text','semantic_role','importance','visual_role'}:raise ValueError('token schema 不匹配')
        if not t['text'] or t['semantic_role'] not in ROLES or t['visual_role'] not in ('primary','secondary','connector'):raise ValueError('无效语义角色')
        value=t['importance']
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:raise ValueError('importance 必须在 0–1')
        tokens.append(Token(t['text'],t['semantic_role'],float(value),start,'LLM',t['visual_role']));start+=len(t['text'])
    relation=plan.get('emphasis_relation')
    if not isinstance(relation,list) or len(relation)>4 or any(not isinstance(s,str) or not s or len(s)>8 or s not in text for s in relation):raise ValueError('无效强调关系')
    return tokens

class SemanticPlanner:
    def __init__(self,key=None,model=None):
        self.key=key or os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY');self.model=model or os.getenv('LLM_MODEL','gpt-4.1-mini')
        self.base_url=os.getenv('LLM_BASE_URL','https://api.openai.com/v1').rstrip('/')
        self.api_style=os.getenv('LLM_API_STYLE','chat_completions' if os.getenv('LLM_BASE_URL') else 'responses')
        self.json_mode=os.getenv('LLM_JSON_MODE','json_schema')
        if not self.key:raise ValueError('服务未配置 LLM_API_KEY 或 OPENAI_API_KEY，B 模式不可用')
        if self.api_style not in ('responses','chat_completions') or self.json_mode not in ('json_schema','json_object'):raise ValueError('无效 LLM 接口配置')
        from urllib.parse import urlparse
        endpoint=urlparse(self.base_url)
        if endpoint.scheme not in ('https','http') or not endpoint.netloc or endpoint.username or endpoint.password:raise ValueError('无效 LLM_BASE_URL')
        if endpoint.scheme=='http' and endpoint.hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('远程 LLM 接口必须使用 HTTPS')

    def _request(self,system,user,schema,name):
        start=time.perf_counter()
        body={'model':self.model,'input':[{'role':'system','content':system},{'role':'user','content':json.dumps(user,ensure_ascii=False)}],
              'text':{'format':{'type':'json_schema','name':name,'strict':True,'schema':schema}},'max_output_tokens':4096,'store':False}
        if self.api_style=='chat_completions':
            body={'model':self.model,'messages':body['input'],'max_tokens':4096,'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}} if self.json_mode=='json_schema' else {'type':'json_object'}}
            if self.model.startswith(('gpt-5','gpt-6')):
                body['max_completion_tokens']=body.pop('max_tokens');body['reasoning_effort']=os.getenv('LLM_REASONING_EFFORT','low')
        elif self.json_mode=='json_object':body['text']['format']={'type':'json_object'}
        if self.api_style=='responses' and self.model.startswith(('gpt-5','gpt-6')):body['reasoning']={'effort':os.getenv('LLM_REASONING_EFFORT','low')}
        response=httpx.post(self.base_url+('/chat/completions' if self.api_style=='chat_completions' else '/responses'),headers={'Authorization':'Bearer '+self.key},json=body,timeout=35)
        if response.status_code>=400:raise ValueError(f'LLM 接口返回 {response.status_code}，检查模型权限/配额')
        payload=response.json()
        output=payload.get('choices',[{}])[0].get('message',{}).get('content','') if self.api_style=='chat_completions' else ''.join(c.get('text','') for item in payload.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
        try:result=json.loads(output)
        except (ValueError,TypeError):raise ValueError('LLM 未返回完整 JSON')
        return result,{'model':self.model,'request_id':payload.get('id'),'usage':payload.get('usage'),'api_latency_ms':round((time.perf_counter()-start)*1000,2)}

    def plan(self,text,sudachi_tokens,dataset_summary):
        plan,metadata=self._request(SYSTEM,{'text':text,'sudachi':[t.dict() for t in sudachi_tokens],'reference_families':dataset_summary},SCHEMA,'japanese_title_plan')
        validate_plan(text,plan)
        plan.update({'provenance':'live_'+self.api_style,**metadata})
        return plan

    def translate(self,text):
        response,metadata=self._request(TRANSLATION['system'],{'source_text':text},TRANSLATION['schema'],'japanese_title_translation')
        translated=validate_translation(response)
        return {'source_text':text,'text':translated,'changed':text!=translated,'provenance':'live_translation_'+self.api_style,**metadata}

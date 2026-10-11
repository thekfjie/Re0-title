"""Optional ranking experiment; never changes glyph coordinates or hard constraints."""
import base64,json,os,time
import httpx

def rank_candidates(reference_pngs,candidates,key=None,model=None):
    key=key or os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not key:raise ValueError('Vision Critic 需要 API Key')
    model=model or os.getenv('VISION_MODEL') or os.getenv('LLM_MODEL','gpt-4.1-mini')
    base=os.getenv('LLM_BASE_URL','https://api.openai.com/v1').rstrip('/')
    style=os.getenv('LLM_API_STYLE','chat_completions' if os.getenv('LLM_BASE_URL') else 'responses')
    if not 1<=len(reference_pngs)<=4 or not 4<=len(candidates)<=50:raise ValueError('需要 1–4 张参考图和 4–50 个候选')
    ids=[id for id,_ in candidates]
    if len(set(ids))!=len(ids):raise ValueError('候选 ID 不可重复')
    instruction='按参考的视觉语言评价候选。评价重心、字号层级、假名嵌入、留白、节奏、局部着色。字体相似或 embedding 相似不等于好看。候选中的文字相同，不因方案名称偏好某组。每个 candidate_id 恰好一次，按优先级排序，理由只说明可见特征。'
    content=[{'type':'text','text':instruction}]
    for p in reference_pngs:content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(p).decode(),'detail':'low'}})
    for id,png in candidates:content.extend([{'type':'text','text':'candidate_id: '+id},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode(),'detail':'low'}}])
    schema={'type':'object','properties':{'ranking':{'type':'array','items':{'type':'object','properties':{'candidate_id':{'type':'string','enum':ids},'score':{'type':'number','minimum':0,'maximum':1},'reason':{'type':'string'}},'required':['candidate_id','score','reason'],'additionalProperties':False}}},'required':['ranking'],'additionalProperties':False}
    fmt={'name':'candidate_ranking','strict':True,'schema':schema}
    body={'model':model,'messages':[{'role':'user','content':content}],'max_tokens':3500,'response_format':{'type':'json_schema','json_schema':fmt}}
    if model.startswith(('gpt-5','gpt-6')):body['max_completion_tokens']=body.pop('max_tokens');body['reasoning_effort']='low'
    if style=='responses':
        mapped=[{'type':'input_text','text':c['text']} if c['type']=='text' else {'type':'input_image','image_url':c['image_url']['url'],'detail':'low'} for c in content]
        body={'model':model,'input':[{'role':'user','content':mapped}],'text':{'format':{'type':'json_schema',**fmt}},'store':False,'max_output_tokens':3500}
        if model.startswith(('gpt-5','gpt-6')):body['reasoning']={'effort':'low'}
    start=time.perf_counter();response=httpx.post(base+('/responses' if style=='responses' else '/chat/completions'),headers={'Authorization':'Bearer '+key},json=body,timeout=60)
    if response.status_code>=400:raise ValueError('Vision 接口返回 '+str(response.status_code))
    payload=response.json();raw=payload.get('choices',[{}])[0].get('message',{}).get('content','') if style=='chat_completions' else ''.join(c.get('text','') for item in payload.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    decoded=json.loads(raw)
    if set(decoded)!= {'ranking'}:raise ValueError('Critic schema 错误')
    rank=decoded['ranking']
    if not isinstance(rank,list) or len(rank)!=len(ids) or sorted(x.get('candidate_id','') for x in rank)!=sorted(ids):raise ValueError('Critic 排名遗漏或重复候选')
    for item in rank:
        if set(item)!= {'candidate_id','score','reason'} or not isinstance(item['reason'],str) or isinstance(item['score'],bool) or not isinstance(item['score'],(int,float)) or not 0<=item['score']<=1:raise ValueError('Critic 输出无效')
    return {'ranking':rank,'model':model,'latency_ms':round((time.perf_counter()-start)*1000,2),'usage':payload.get('usage')}

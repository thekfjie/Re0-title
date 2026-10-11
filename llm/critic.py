"""Optional strict ranking; never changes layout coordinates or constraints.
Experimental and off by default; no benchmark claims without live measurements.
"""
import base64,json,os,time
import httpx

def rank_candidates(reference_pngs,candidates,key=None,model=None):
    key=key or os.getenv('OPENAI_API_KEY')
    if not key:raise ValueError('Vision Critic 需要 API Key')
    model=model or os.getenv('VISION_MODEL','gpt-4.1-mini')
    if not 1<=len(reference_pngs)<=4 or not 4<=len(candidates)<=50:raise ValueError('需要 1–4 张参考图和 4–50 个候选')
    content=[{'type':'input_text','text':'按参考的视觉语言评价候选。评价重心、层级、留白、节奏、局部着色。不要把字体相似或 embedding 相似等同于好看。每个 candidate_id 恰好一次，按优先级排序，理由说明可见特征。'}]
    for p in reference_pngs:content.append({'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(p).decode(),'detail':'low'})
    for id,png in candidates:
        content.extend([{'type':'input_text','text':'candidate_id: '+id},{'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(png).decode(),'detail':'low'}])
    ids=[id for id,_ in candidates]
    schema={'type':'object','properties':{'ranking':{'type':'array','items':{'type':'object','properties':{'candidate_id':{'type':'string','enum':ids},'score':{'type':'number','minimum':0,'maximum':1},'reason':{'type':'string'}},'required':['candidate_id','score','reason'],'additionalProperties':False}}},'required':['ranking'],'additionalProperties':False}
    start=time.perf_counter()
    response=httpx.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json={'model':model,'input':[{'role':'user','content':content}],'text':{'format':{'type':'json_schema','name':'candidate_ranking','strict':True,'schema':schema}},'store':False,'max_output_tokens':2200},timeout=45)
    response.raise_for_status();payload=response.json()
    raw=''.join(c.get('text','') for item in payload.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text');rank=json.loads(raw)['ranking']
    if sorted(x['candidate_id'] for x in rank)!=sorted(ids):raise ValueError('Critic 排名遗漏或重复候选')
    return {'ranking':rank,'model':model,'latency_ms':round((time.perf_counter()-start)*1000,2),'usage':payload.get('usage')}

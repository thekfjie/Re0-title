from pathlib import Path
from contextlib import asynccontextmanager
from collections import defaultdict,deque
from hashlib import sha256
from tempfile import TemporaryDirectory
import asyncio,json,os,secrets,shutil,time,sys
from typing import Literal
from fastapi import FastAPI,UploadFile,File,Request,HTTPException,Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from engine.fonts import UploadFontProvider,PrivateFontProvider,inspect_font,MAX_FONT_BYTES
from engine.layout import load_config
from engine.text import JapaneseAnalyzer
from llm.planner import SemanticPlanner

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.getenv('RUNTIME_DIR',str(ROOT/'.runtime')))
TTL=int(os.getenv('FONT_TTL_SECONDS','3600'))
uploads=UploadFontProvider(RUNTIME/'fonts',TTL);jobs=RUNTIME/'jobs';jobs.mkdir(parents=True,exist_ok=True,mode=0o700)
private=PrivateFontProvider(os.getenv('PRIVATE_FONT_DIR','/private-fonts'),os.getenv('PRIVATE_MODE')=='1')
RATE=defaultdict(deque);SLOTS=asyncio.Semaphore(2)
MIMES={'application/octet-stream','font/ttf','font/otf','application/x-font-ttf','application/x-font-opentype','application/vnd.ms-opentype','application/font-sfnt','font/sfnt'}

def cleanup():
    uploads.cleanup()
    for owner in jobs.iterdir():
        if not owner.is_dir() or owner.is_symlink():continue
        for job in owner.iterdir():
            if job.is_dir() and time.time()-job.stat().st_mtime>=TTL:shutil.rmtree(job,ignore_errors=True)
        if not any(owner.iterdir()):owner.rmdir()
    for owner,events in list(RATE.items()):
        if not events or time.time()-events[-1]>3600:RATE.pop(owner,None)

@asynccontextmanager
async def lifespan(app):
    cleanup()
    async def sweeper():
        while True:
            await asyncio.sleep(60);await asyncio.to_thread(cleanup)
    task=asyncio.create_task(sweeper())
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass

app=FastAPI(title='Japanese Title Lab',lifespan=lifespan)

class BodyLimitMiddleware:
    """Reject chunked or declared oversized bodies before multipart spooling."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method')!='POST' or scope.get('path') not in ('/fonts','/render'):
            return await self.app(scope,receive,send)
        limit=MAX_FONT_BYTES+128*1024 if scope['path']=='/fonts' else 32*1024
        headers=dict(scope.get('headers',[]))
        try:declared=int(headers.get(b'content-length',b'0'))
        except ValueError:declared=limit+1
        if declared>limit:return await Response('请求体过大',status_code=413)(scope,receive,send)
        parts=[];size=0
        while True:
            event=await receive()
            if event['type']=='http.disconnect':return
            part=event.get('body',b'');size+=len(part)
            if size>limit:return await Response('请求体过大',status_code=413)(scope,receive,send)
            parts.append(part)
            if not event.get('more_body'):break
        body=b''.join(parts);delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:delivered=True;return {'type':'http.request','body':body,'more_body':False}
            return await receive()
        return await self.app(scope,replay,send)

app.add_middleware(BodyLimitMiddleware)

@app.middleware('http')
async def session(request,call_next):
    owner=request.cookies.get('title_session','')
    if len(owner)!=43 or any(not(c.isalnum() or c in '_-') for c in owner):owner=secrets.token_urlsafe(32)
    request.state.owner=owner
    if request.method in ('POST','DELETE'):
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return Response('请求来源不匹配',status_code=403)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.set_cookie('title_session',owner,max_age=TTL,httponly=True,samesite='strict',secure=os.getenv('SECURE_COOKIES')=='1')
    return response

def auth_private(request):
    expected=os.getenv('ADMIN_TOKEN')
    supplied=request.headers.get('authorization','').removeprefix('Bearer ')
    if not private.enabled or not expected or not secrets.compare_digest(supplied,expected):raise HTTPException(403,'管理员私有字体需要配置 PRIVATE_MODE=1 与 ADMIN_TOKEN')

def font_path(fid,request):
    if fid.startswith('private_'):auth_private(request);return private.resolve(fid,request.state.owner)
    return uploads.resolve(fid,request.state.owner)

def rate(request):
    now=time.time();events=RATE[request.state.owner]
    while events and now-events[0]>60:events.popleft()
    if len(events)>=8:raise HTTPException(429,'每分钟最多 8 次操作')
    events.append(now)

@app.get('/api/status')
def status():return {'service':'python-harfbuzz','llm_available':bool(os.getenv('OPENAI_API_KEY')),'font_ttl_seconds':TTL,'max_font_bytes':MAX_FONT_BYTES,'private_fonts':private.enabled}

@app.post('/fonts')
async def upload_font(request:Request,file:UploadFile=File(...)):
    rate(request)
    if (file.content_type or 'application/octet-stream') not in MIMES:raise HTTPException(415,'不支持此 MIME 类型')
    data=await file.read(MAX_FONT_BYTES+1);await file.close()
    try:
        # Bounded isolated parser: fontTools never parses hostile uploads in API process.
        async with SLOTS:
            with TemporaryDirectory(prefix='font-check-',dir=RUNTIME) as d:
                p=Path(d)/'input.font';p.write_bytes(data)
                code='from engine.fonts import inspect_font;from pathlib import Path;import sys,json,resource;resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024));print(json.dumps(inspect_font(Path(sys.argv[1]).read_bytes(),sys.argv[2])))'
                process=await asyncio.create_subprocess_exec(sys.executable,'-c',code,str(p),Path(file.filename or 'upload.ttf').name,cwd=ROOT,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:stdout,stderr=await asyncio.wait_for(process.communicate(),15)
                except asyncio.TimeoutError:process.kill();await process.wait();raise ValueError('字体解析超时')
                if process.returncode:raise ValueError('无效字体或字体解析失败')
                metadata=json.loads(stdout)
                # Store vetted bytes without parsing again in API process.
                ownerdir=uploads._owner(request.state.owner);ownerdir.mkdir(mode=0o700,exist_ok=True)
                files=list(ownerdir.iterdir())
                if len(files)>=8 or sum(p.stat().st_size for p in files)+len(data)>64*1024*1024:raise ValueError('会话字体数量或容量超限')
                fid=secrets.token_urlsafe(24);path=ownerdir/(fid+Path(file.filename or 'upload.ttf').suffix.lower());path.write_bytes(data);os.chmod(path,0o600)
                return {'font_id':fid,**metadata,'expires_in_seconds':TTL}
    except (ValueError,KeyError) as e:raise HTTPException(422,str(e))

@app.get('/fonts/private')
def private_fonts(request:Request):auth_private(request);return private.list()

@app.delete('/fonts')
def delete_fonts(request:Request):
    uploads.delete_owner(request.state.owner);shutil.rmtree(jobs/sha256(request.state.owner.encode()).hexdigest(),ignore_errors=True)
    return {'deleted':True}

class RenderInput(BaseModel):
    text:str=Field(min_length=1,max_length=80)
    font_id:str|None=None
    fonts:dict[str,str]|None=None
    mode:Literal['classic','llm']='classic'
    seed:int=Field(default=42,ge=0,le=2147483647)
    count:int=Field(default=6,ge=4,le=8)
    width:int=Field(default=1200,ge=256,le=2400)
    height:int=Field(default=675,ge=256,le=2400)
    palette:Literal['night','violet','crimson','monochrome']='night'
    transparent:bool=False
    heuristic:Literal['balanced','kanji_anchor','semantic_nouns']='balanced'

@app.post('/render')
async def render(args:RenderInput,request:Request):
    rate(request)
    if args.width*args.height>4000000:raise HTTPException(422,'画布像素上限 400 万')
    fids=args.fonts or ({'kanji':args.font_id,'kana':args.font_id} if args.font_id else {})
    if not fids.get('kanji') or set(fids)-{'kanji','kana'}:raise HTTPException(422,'需要 kanji 字体，kana 可选')
    fids.setdefault('kana',fids['kanji'])
    try:paths={k:font_path(v,request) for k,v in fids.items()}
    except ValueError as e:raise HTTPException(404,str(e))
    if args.mode=='llm' and not os.getenv('OPENAI_API_KEY'):raise HTTPException(503,'服务未配置 OPENAI_API_KEY；A 可独立使用')
    async with SLOTS:
        ownerdir=jobs/sha256(request.state.owner.encode()).hexdigest();ownerdir.mkdir(mode=0o700,exist_ok=True)
        jid=secrets.token_urlsafe(20);job=ownerdir/jid;job.mkdir(mode=0o700)
        try:
            input=args.model_dump();font_paths={}
            for role,path in paths.items():
                name='font-'+role+path.suffix;shutil.copyfile(path,job/name);os.chmod(job/name,0o600);font_paths[role]=name
            input['font_paths']=font_paths
            if args.mode=='llm':
                config=load_config();tokens=JapaneseAnalyzer(config['rules']).analyze(args.text)
                summary=json.loads((ROOT/'analysis/family_summary.json').read_text())
                input['plan']=await asyncio.to_thread(SemanticPlanner().plan,args.text,tokens,summary)
            (job/'input.json').write_text(json.dumps(input,ensure_ascii=False))
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','web.render_worker',str(job),cwd=ROOT,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
            try:stdout,stderr=await asyncio.wait_for(process.communicate(),50)
            except asyncio.TimeoutError:process.kill();await process.wait();raise ValueError('任务超时，请减小文本或画布')
            if process.returncode:
                detail=stderr.decode(errors='replace').splitlines()[-1] if stderr else '渲染失败'
                raise ValueError(detail[:300])
            result=json.loads((job/'results.json').read_text())
            for c in result['candidates']:
                c['png_url']=f'/results/{jid}/{c["id"]}.png';c['svg_url']=f'/results/{jid}/{c["id"]}.svg'
            return {'job_id':jid,'mode':args.mode,'expires_in_seconds':TTL,**result,'planner':input.get('plan')}
        except Exception as e:
            shutil.rmtree(job,ignore_errors=True)
            raise HTTPException(422,str(e)[:300])
        finally:
            for p in job.glob('font-*'):p.unlink(missing_ok=True)
            (job/'input.json').unlink(missing_ok=True)

@app.get('/results/{job_id}/{name}')
def result_file(job_id:str,name:str,request:Request):
    if not all(c.isalnum() or c in '_-' for c in job_id) or not __import__('re').fullmatch(r'candidate-[1-8]\.(png|svg)',name):raise HTTPException(404)
    job=jobs/sha256(request.state.owner.encode()).hexdigest()/job_id
    path=job/name
    if not path.is_file() or path.is_symlink() or time.time()-job.stat().st_mtime>=TTL:raise HTTPException(404,'结果不存在或已过期')
    return FileResponse(path,media_type='image/svg+xml' if path.suffix=='.svg' else 'image/png',filename=name)

app.mount('/',StaticFiles(directory=ROOT/'dist' if (ROOT/'dist').is_dir() else ROOT/'web/client',html=True),name='ui')

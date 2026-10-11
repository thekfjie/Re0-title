from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from web.app import app

FONT=Path(__file__).resolve().parents[1]/'assets/open-fonts/noto-sans-jp-black.ttf'

def test_upload_mime_and_header():
    with TestClient(app) as client:
        assert client.post('/fonts',files={'file':('bad.ttf',b'not-a-font','font/ttf')}).status_code==422
        assert client.post('/fonts',files={'file':('bad.ttf',b'not-a-font','text/html')}).status_code==415
        assert client.post('/fonts',content=b'x',headers={'Content-Length':str(30*1024*1024)}).status_code==413

def test_fonts_results_are_session_private_and_copies_deleted():
    if not FONT.exists():pytest.skip('research font required')
    from web.app import uploads,jobs
    with TestClient(app) as a,TestClient(app) as b:
        r=a.post('/fonts',files={'file':('../../evil.ttf',FONT.read_bytes(),'font/ttf')});assert r.status_code==200,r.text
        fid=r.json()['font_id'];assert 'url' not in r.json()
        assert b.post('/render',json={'text':'鎖の音','font_id':fid,'count':4}).status_code==404
        rendered=a.post('/render',json={'text':'鎖の音','font_id':fid,'count':4});assert rendered.status_code==200,rendered.text
        candidate=rendered.json()['candidates'][0];assert a.get(candidate['png_url']).status_code==200
        assert b.get(candidate['png_url']).status_code==404
        assert a.get('/fonts/'+fid+'.ttf').status_code==404
        assert not list(jobs.rglob('font-*'))
        assert a.delete('/fonts').status_code==200
        assert a.get(candidate['png_url']).status_code==404

def test_unconfigured_llm_is_explicit():
    import os
    if os.getenv('OPENAI_API_KEY'):pytest.skip('LLM configured')
    with TestClient(app) as client:assert client.get('/api/status').json()['llm_available'] is False

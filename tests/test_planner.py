import json
from pathlib import Path
from llm.planner import SCHEMA,SemanticPlanner

def test_compatible_server_configuration_and_plan_validation(monkeypatch):
    text='聖域の終わり';plan={'tokens':[{'text':text,'semantic_role':'concept','importance':.9,'visual_role':'primary'}],'suggested_layout_family':'interwoven','emphasis_relation':['聖域']}
    monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_BASE_URL','https://example.test/v1');monkeypatch.setenv('LLM_MODEL','test-model');monkeypatch.setenv('LLM_API_STYLE','chat_completions')
    seen={}
    class Response:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':json.dumps(plan)}}],'usage':{'prompt_tokens':42}}
    def fake(url,**kwargs):seen.update({'url':url,'body':kwargs['json']});return Response()
    monkeypatch.setattr('llm.planner.httpx.post',fake)
    result=SemanticPlanner().plan(text,[],{})
    assert seen['url']=='https://example.test/v1/chat/completions'
    assert seen['body']['model']=='test-model' and seen['body']['response_format']['type']=='json_schema'
    assert result['provenance']=='live_chat_completions' and 'test-only' not in json.dumps(result)
    assert json.loads((Path(__file__).resolve().parents[1]/'llm/planner_contract.json').read_text())['schema']==SCHEMA

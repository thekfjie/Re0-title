import test from 'node:test';import assert from 'node:assert/strict';
import {semanticPlan,validatePlan,handlePlanner} from '../hosting/semantic-gateway.js';
const text='聖域の終わり',plan={tokens:[{text,semantic_role:'concept',importance:.9,visual_role:'primary'}],suggested_layout_family:'interwoven',emphasis_relation:['聖域']};
test('compatible Chat Completions uses server configuration and validates the plan',async()=>{
 let seen;const result=await semanticPlan(text,[{text}],{LLM_API_KEY:'test-only',LLM_BASE_URL:'https://example.test/v1',LLM_MODEL:'test-model',LLM_API_STYLE:'chat_completions'},async(url,init)=>{seen={url,body:JSON.parse(init.body)};return Response.json({id:'fake-provider-response',choices:[{message:{content:JSON.stringify(plan)}}],usage:{prompt_tokens:42,completion_tokens:19}});});assert.equal(seen.url,'https://example.test/v1/chat/completions');assert.equal(seen.body.model,'test-model');assert.equal(seen.body.response_format.type,'json_schema');assert.equal(result.provenance,'live_chat_completions');assert.ok(!JSON.stringify(result).includes('test-only'));
});
test('Responses and JSON-object compatible paths both validate output',async()=>{
 let seen;const result=await semanticPlan(text,[{text}],{OPENAI_API_KEY:'test-only',LLM_API_STYLE:'responses',LLM_JSON_MODE:'json_object'},async(url,init)=>{seen=JSON.parse(init.body);return Response.json({output:[{content:[{type:'output_text',text:JSON.stringify(plan)}]}]});});assert.equal(seen.text.format.type,'json_object');assert.equal(result.provenance,'live_responses');
});
test('rewritten text, coordinates, nonfinite importance and missing keys are rejected',()=>{
 assert.throws(()=>validatePlan('違う原文',plan));assert.throws(()=>validatePlan(text,{...plan,x:300}));assert.throws(()=>validatePlan(text,{...plan,tokens:[{...plan.tokens[0],importance:NaN}]}));assert.throws(()=>validatePlan(text,{tokens:plan.tokens}));
});
test('missing key, foreign Origin and oversized body fail before model execution',async()=>{
 const url='https://private.example/api/plan';assert.equal((await handlePlanner(new Request(url,{method:'POST',body:'{}'}),{})).status,503);assert.equal((await handlePlanner(new Request(url,{method:'POST',headers:{Origin:'https://foreign.example'},body:'{}'}),{LLM_API_KEY:'test-only'})).status,403);assert.equal((await handlePlanner(new Request(url,{method:'POST',body:'x'.repeat(32769)}),{LLM_API_KEY:'test-only'})).status,413);
});

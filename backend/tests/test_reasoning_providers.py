"""从真实协议流中提取正文和思考，验证输出上限传给正确端点。"""
import json
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app.services.providers import llm as module
from app.services.providers.answer_stream import ThinkTagSplitter


@pytest.mark.parametrize('field', ['reasoning_content', 'reasoning', 'thinking'])
async def test_api_stream_keeps_reasoning_and_finish_metadata(field):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        events = [
            {'choices':[{'index':0,'delta':{'role':'assistant',field:'先分析问题'},'finish_reason':None}]},
            {'choices':[{'index':0,'delta':{'content':'正文'},'finish_reason':None}]},
            {'choices':[{'index':0,'delta':{},'finish_reason':'length'}]},
        ]
        return httpx.Response(200, text=''.join('data: '+json.dumps(item)+'\n\n' for item in events)+'data: [DONE]\n\n', headers={'Content-Type':'text/event-stream'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        llm = module.ReasoningChatOpenAI(model='thinking-test', api_key='test-key', base_url='https://model.example/v1', max_tokens=16384, http_async_client=client)
        chunks = [chunk async for chunk in llm.astream([HumanMessage(content='问题')])]
    assert ''.join(c.additional_kwargs.get('reasoning_content','') for c in chunks) == '先分析问题'
    assert ''.join(c.content for c in chunks) == '正文'
    assert chunks[-1].response_metadata['finish_reason'] == 'length'
    assert requests[0].get('max_completion_tokens', requests[0].get('max_tokens')) == 16384


@pytest.mark.parametrize('complete', [True, False])
async def test_ollama_native_thinking_and_limit(monkeypatch, complete):
    requests = []

    def handler(request):
        assert request.url.path == '/api/chat'
        requests.append(json.loads(request.content))
        events = [{'message':{'role':'assistant','thinking':'思考内容','content':''},'done':False},
                  {'message':{'role':'assistant','content':'最终正文'},'done':False}]
        if complete:
            events.append({'message':{'content':''}, 'done':True, 'done_reason':'stop'})
        return httpx.Response(200, text='\n'.join(json.dumps(item) for item in events))

    original = httpx.AsyncClient
    monkeypatch.setattr(module, 'httpx', SimpleNamespace(AsyncClient=lambda **kw: original(transport=httpx.MockTransport(handler), **kw)))
    llm = module.OllamaChatModel(model='qwen3', api_key='ollama', base_url='http://localhost:11434/v1', max_tokens=32768, streaming=True)
    chunks = []
    async def run():
        async for chunk in llm.astream([HumanMessage(content='问题')]):
            chunks.append(chunk)
    if complete:
        await run()
        assert chunks[-1].response_metadata['finish_reason'] == 'stop'
    else:
        with pytest.raises(ValueError, match='意外结束'):
            await run()
    assert ''.join(c.additional_kwargs.get('reasoning_content','') for c in chunks) == '思考内容'
    assert ''.join(c.content for c in chunks) == '最终正文'
    assert requests[0]['options']['num_predict'] == 32768


@pytest.mark.parametrize('parts,answer,reason', [
    (['<thi','nk>思考','</thi','nk>答案'], '答案', '思考'),
    (['普通','正文'], '普通正文', ''),
    (['<think>只有思考'], '', '只有思考'),
    (['  <th','ink>推理</think>','```html\n<div>答案</div>'], '```html\n<div>答案</div>', '推理'),
    (['正文中的 <think> 标签'], '正文中的 <think> 标签', ''),
])
def test_split_think_tags(parts, answer, reason):
    splitter = ThinkTagSplitter()
    pieces = [splitter.feed(piece) for piece in parts] + [splitter.finish()]
    assert ''.join(piece[0] for piece in pieces) == answer
    assert ''.join(piece[1] for piece in pieces) == reason

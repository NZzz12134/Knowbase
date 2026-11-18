"""自动回答模式：资料筛选、上下文、缓存、错误与空知识库边界。"""
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core.exceptions import BusinessError
from app.services.personal_access import retrieval_scope
from app.services.rag import chain as chain_module, relevance
from app.services.rag.retrievers import RetrievedChunk


@pytest.fixture
def chunks():
    return [RetrievedChunk(id=str(uuid.uuid4()), text='官方售价：299 元', score=0.02, metadata={'filename':'products.md'}),
            RetrievedChunk(id=str(uuid.uuid4()), text='续航 8 小时', score=0.01, metadata={'filename':'products.md'})]


class CapturePrompts(BaseCallbackHandler):
    def __init__(self, seen):
        self.seen = seen

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.seen.extend(messages[0])


@pytest.fixture
def flow(monkeypatch):
    mocks = {name: AsyncMock(return_value=value) for name, value in
             [('embed', [[.1]]), ('retrieve', []), ('selector', []), ('read', None), ('write', None)]}
    seen = []
    llm = FakeListChatModel(responses=['直接回答内容'], callbacks=[CapturePrompts(seen)])
    monkeypatch.setattr(chain_module, 'embed_with_cache', mocks['embed'])
    monkeypatch.setattr(chain_module, 'hybrid_retrieve', mocks['retrieve'])
    monkeypatch.setattr(chain_module, 'select_relevant_chunks', mocks['selector'])
    monkeypatch.setattr(chain_module.cache, 'get_cached_answer', mocks['read'])
    monkeypatch.setattr(chain_module.cache, 'set_cached_answer', mocks['write'])
    monkeypatch.setattr(chain_module, 'condense_question', AsyncMock(side_effect=lambda h, q: q))
    monkeypatch.setattr(chain_module, 'get_llm', lambda: llm)
    return {**mocks, 'seen': seen}


async def collect(question='你好', history=None, refresh=False, has_kb=True):
    with retrieval_scope(uuid.UUID(int=1), (uuid.UUID(int=2),) if has_kb else ()):
        return [event async for event in chain_module.run_qa_stream(None, question, history or [], refresh=refresh)]


async def test_no_knowledge_base_skips_embedding_and_retrieval(flow):
    events = await collect(has_kb=False)
    assert events[0][1]['answer_mode'] == 'general'
    for key in ('embed', 'retrieve', 'selector'):
        flow[key].assert_not_awaited()
    assert ''.join(p['content'] for e, p in events if e == 'token') == '直接回答内容'


async def test_irrelevant_candidates_not_passed_to_answer(flow, chunks):
    flow['retrieve'].return_value = chunks
    events = await collect('写一首关于春天的诗')
    flow['selector'].assert_awaited_once_with('写一首关于春天的诗', chunks)
    assert events[0][1]['answer_mode'] == 'general' and not events[0][1]['citations']
    assert '299' not in str(flow['seen']) and '续航' not in str(flow['seen'])
    assert flow['write'].await_args.args[-1] == []


async def test_only_relevant_citations_reach_answer(flow, chunks):
    flow['retrieve'].return_value = chunks
    flow['selector'].return_value = chunks[:1]
    events = await collect('价格是多少？')
    assert events[0][1]['answer_mode'] == 'knowledge'
    assert [c['id'] for c in events[0][1]['citations']] == [chunks[0].id]
    assert '299' in str(flow['seen']) and '续航 8 小时' not in str(flow['seen'])


@pytest.mark.parametrize('knowledge', [False, True])
async def test_answer_uses_original_question_and_history(flow, chunks, monkeypatch, knowledge):
    history = [{'role':'user','content':'我想学 Python'}, {'role':'assistant','content':'可以从基础语法开始'}]
    monkeypatch.setattr(chain_module, 'condense_question', AsyncMock(return_value='Python 学习计划'))
    flow['retrieve'].return_value = chunks
    flow['selector'].return_value = chunks if knowledge else []
    await collect('给我安排三天，每天半小时', history)
    flow['embed'].assert_awaited_once_with(['Python 学习计划'])
    assert [m.content for m in flow['seen'][1:3]] == [m['content'] for m in history]
    assert '给我安排三天，每天半小时' in flow['seen'][-1].content


async def test_cache_separates_modes_history_and_refresh(flow, chunks):
    await collect('same')
    general = flow['read'].await_args.args
    await collect('same', [{'role':'user','content':'不同上下文'}])
    assert general != flow['read'].await_args.args
    flow['retrieve'].return_value = chunks
    flow['selector'].return_value = chunks
    await collect('same')
    assert general != flow['read'].await_args.args
    flow['read'].reset_mock()
    assert (await collect('same', refresh=True))[-1][1]['cached'] is False
    flow['read'].assert_not_awaited()


@pytest.mark.parametrize('knowledge', [False, True])
async def test_cached_answers_emit_current_sources_and_mode(flow, chunks, knowledge):
    flow['retrieve'].return_value = chunks
    flow['selector'].return_value = chunks if knowledge else []
    flow['read'].return_value = {'answer':'缓存回答', 'citations':[{'id':'stale'}]}
    events = await collect()
    assert events[0][1]['citations'] == (chain_module._format_context(chunks)[1] if knowledge else [])
    assert events[0][1]['answer_mode'] == ('knowledge' if knowledge else 'general')
    assert events[-1] == ('usage', {'cached':True})
    flow['write'].assert_not_awaited()


async def test_retrieval_errors_do_not_pretend_sources_are_irrelevant(flow):
    flow['embed'].side_effect = RuntimeError('offline')
    with pytest.raises(BusinessError) as exc:
        await collect()
    assert exc.value.code == 'retrieval_unavailable'
    flow['read'].assert_not_awaited()


@pytest.mark.parametrize('ids', [[1], [2], [], [2, 1]])
async def test_semantic_selection_keeps_source_order(monkeypatch, chunks, ids):
    monkeypatch.setattr(relevance, 'get_llm', lambda: FakeListChatModel(responses=[json.dumps({'relevant_ids':ids})]))
    selected = await relevance.select_relevant_chunks('问题', chunks)
    assert selected == [c for i, c in enumerate(chunks, 1) if i in ids]


@pytest.mark.parametrize('response', ['invalid', '{"relevant_ids":[3]}', '{"relevant_ids":[true]}',
                                    '{"relevant_ids":[1,1]}', '{"relevant_ids":"all"}', '[]'])
async def test_invalid_relevance_output_does_not_choose_a_route(monkeypatch, chunks, response):
    monkeypatch.setattr(relevance, 'get_llm', lambda: FakeListChatModel(responses=[response]))
    with pytest.raises(BusinessError) as exc:
        await relevance.select_relevant_chunks('问题', chunks)
    assert exc.value.code == 'relevance_unavailable'


async def test_no_candidates_skips_relevance_model(monkeypatch):
    def unexpected():
        pytest.fail('Empty candidates must skip relevance model')
    monkeypatch.setattr(relevance, 'get_llm', unexpected)
    assert await relevance.select_relevant_chunks('问题', []) == []


@pytest.mark.parametrize('content,finish,code', [
    ('', 'length', 'answer_token_limit'),
    ('<html>尚未写完', 'length', 'answer_token_limit'),
    ('', 'stop', 'empty_answer'),
    ('   \n', 'stop', 'empty_answer'),
    ('', None, 'empty_answer'),
])
async def test_empty_or_truncated_answer_is_not_cached_as_success(flow, monkeypatch, content, finish, code):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.runnables import RunnableGenerator

    async def upstream(inputs):
        async for _ in inputs:
            pass
        yield AIMessageChunk(content='', additional_kwargs={'reasoning_content':'内部推理'})
        yield AIMessageChunk(content=content)
        yield AIMessageChunk(content='', response_metadata={'finish_reason':finish} if finish else {})

    monkeypatch.setattr(chain_module, 'get_llm', lambda: RunnableGenerator(upstream))
    events = []
    with pytest.raises(BusinessError) as exc:
        with retrieval_scope(uuid.UUID(int=1), ()):
            async for event in chain_module.run_qa_stream(None, '写一个完整动画', []):
                events.append(event)
    assert exc.value.code == code
    assert ''.join(p['content'] for e, p in events if e == 'token') == content
    assert all(e != 'usage' for e, _ in events)
    flow['write'].assert_not_awaited()


async def test_empty_cached_answer_is_regenerated(flow):
    flow['read'].return_value = {'answer':'  \n', 'citations':[]}
    events = await collect(has_kb=False)
    assert ''.join(p['content'] for e, p in events if e == 'token') == '直接回答内容'
    assert events[-1][1]['cached'] is False
    flow['write'].assert_awaited_once()


async def test_text_blocks_exclude_reasoning_and_keep_complete_answer(flow, monkeypatch):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.runnables import RunnableGenerator

    async def upstream(inputs):
        async for _ in inputs:
            pass
        yield AIMessageChunk(content=[{'type':'reasoning', 'text':'内部推理'}, {'type':'text', 'text':'完整正文'}])
        yield AIMessageChunk(content='', response_metadata={'finish_reason':'stop'})

    monkeypatch.setattr(chain_module, 'get_llm', lambda: RunnableGenerator(upstream))
    events = await collect(has_kb=False)
    assert ''.join(p['content'] for e, p in events if e == 'token') == '完整正文'
    assert flow['write'].await_args.args[-2] == '完整正文'
    assert ''.join(p['content'] for e, p in events if e == 'reasoning') == '内部推理'
    assert flow['write'].await_args.kwargs['reasoning_content'] == '内部推理'


@pytest.mark.parametrize('enabled', [True, False])
async def test_reasoning_setting_applies_to_live_and_cached_answers(flow, monkeypatch, enabled):
    from langchain_core.messages import AIMessageChunk
    from langchain_core.runnables import RunnableGenerator
    from app.services.model_config_service import get_model_settings, model_settings_scope

    async def upstream(inputs):
        async for _ in inputs:
            pass
        yield AIMessageChunk(content='', additional_kwargs={'reasoning_content':'先检查边界'})
        yield AIMessageChunk(content='<thi')
        yield AIMessageChunk(content='nk>标签中的思考</think>最终正文')

    monkeypatch.setattr(chain_module, 'get_llm', lambda: RunnableGenerator(upstream))
    with model_settings_scope(get_model_settings().model_copy(update={'SHOW_REASONING':enabled})):
        live = await collect(has_kb=False)
        flow['read'].return_value = {'answer':'最终正文','reasoning_content':'缓存思考'}
        cached = await collect(has_kb=False)
    assert ''.join(p['content'] for e,p in live if e == 'token') == '最终正文'
    expected = '先检查边界标签中的思考' if enabled else ''
    assert ''.join(p['content'] for e,p in live if e == 'reasoning') == expected
    assert flow['write'].await_args.kwargs['reasoning_content'] == expected
    assert ''.join(p['content'] for e,p in cached if e == 'reasoning') == ('缓存思考' if enabled else '')

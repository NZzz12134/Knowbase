"""RAG 链路测试：问题改写、直接回答、引用事件。"""
import uuid
import pytest

from app.services.rag import chain as chain_module
from app.services.rag.retrievers import RetrievedChunk
from app.services.personal_access import retrieval_scope


@pytest.fixture(autouse=True)
def active_scope(monkeypatch):
    async def relevant(question, chunks):
        return chunks
    monkeypatch.setattr(chain_module, 'select_relevant_chunks', relevant)
    with retrieval_scope(uuid.UUID(int=1), (uuid.UUID(int=2),)):
        yield


@pytest.fixture
def fake_chunks():
    return [
        RetrievedChunk(
            id="11111111-1111-1111-1111-111111111111",
            text="官方售价：299 元",
            score=0.85,
            metadata={"filename": "products.md", "page": 1},
        ),
        RetrievedChunk(
            id="22222222-2222-2222-2222-222222222222",
            text="续航 8 小时",
            score=0.72,
            metadata={"filename": "products.md", "page": 1},
        ),
    ]


async def test_empty_retrieval_direct_answer(monkeypatch):
    """检索为空 → 对话模型直接回答，不附知识库引用。"""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    monkeypatch.setattr(chain_module, 'get_llm', lambda: FakeListChatModel(responses=['你好，可以直接聊聊。']))
    async def no_cache(*args):
        return None
    monkeypatch.setattr(chain_module.cache, 'get_cached_answer', no_cache)
    monkeypatch.setattr(chain_module.cache, 'set_cached_answer', no_cache)
    async def fake_embed(texts):
        return [[0.1] * 8 for _ in texts]

    async def fake_retrieve(*args, **kwargs):
        return []

    monkeypatch.setattr(chain_module, "embed_with_cache", fake_embed)
    monkeypatch.setattr(chain_module, "hybrid_retrieve", fake_retrieve)

    events = []
    async for event, payload in chain_module.run_qa_stream(None, "问题", []):
        events.append((event, payload))

    assert events[0] == ('citations', {'citations': [], 'answer_mode': 'general', 'mode': 'general'})
    assert ''.join(p['content'] for e, p in events if e == 'token') == '你好，可以直接聊聊。'


async def test_citations_event_emitted(monkeypatch, fake_chunks):
    """有检索结果 → 先发 citations 事件，再流式 token。"""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    async def fake_embed(texts):
        return [[0.1] * 8 for _ in texts]

    async def fake_retrieve(*args, **kwargs):
        return fake_chunks

    async def fake_get_cached(*a, **k):
        return None

    fake_llm = FakeListChatModel(responses=["回答内容"])
    monkeypatch.setattr(chain_module, "get_llm", lambda: fake_llm)
    monkeypatch.setattr(chain_module, "embed_with_cache", fake_embed)
    monkeypatch.setattr(chain_module, "hybrid_retrieve", fake_retrieve)
    # 关闭答案缓存干扰
    monkeypatch.setattr(chain_module.cache, "get_cached_answer", fake_get_cached)
    monkeypatch.setattr(chain_module.cache, "set_cached_answer", _fake_set)

    events = []
    async for event, payload in chain_module.run_qa_stream(None, "问题", []):
        events.append((event, payload))

    kinds = [e for e, _ in events]
    assert kinds[0] == "citations"
    assert events[0][1]['answer_mode'] == 'knowledge'
    assert kinds[-1] == "usage"
    citations = events[0][1]["citations"]
    assert len(citations) == 2
    assert citations[0]["filename"] == "products.md"
    assert citations[0]["page"] == 1
    tokens = [p["content"] for e, p in events if e == "token"]
    assert "".join(tokens) == "回答内容"


async def _fake_set(*args, **kwargs):
    return None


async def test_condense_without_history_is_identity():
    """无历史时 condense 直接返回原问题（不调 LLM）。"""
    result = await chain_module.condense_question([], "蓝牙耳机续航？")
    assert result == "蓝牙耳机续航？"

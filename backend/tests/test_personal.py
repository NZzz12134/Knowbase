"""Personal flows and security boundaries, with fake model/queue and temporary original files."""
import copy
import io
import json
import uuid
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.models import ChatSession, Chunk, Citation, Document, KnowledgeBase, Message, User, UserModelConfig
from app.services import model_config_service as models
from app.services.personal_access import current_scope, retrieval_scope


@pytest.fixture(autouse=True)
async def clean_personal_records(db_session):
    yield
    # These tests create document-owning ordinary users; remove their FK dependents
    # before older test modules delete non-admin accounts.
    ids = list((await db_session.execute(select(User.id).where(User.username.startswith('p_', autoescape=True)))).scalars())
    await db_session.execute(delete(KnowledgeBase).where(KnowledgeBase.created_by.in_(ids)))
    await db_session.execute(delete(ChatSession).where(ChatSession.user_id.in_(ids)))
    await db_session.execute(delete(User).where(User.id.in_(ids)))
    await db_session.commit()


@pytest.fixture(autouse=True)
def local_storage(monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services import document_service
    from app.services.rag import vector_store
    monkeypatch.setattr(get_settings(), "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(document_service, "_enqueue_parse", lambda _: "fake-task")
    for name in ("ensure_collection", "delete_collection", "delete_by_document"):
        monkeypatch.setattr(vector_store, name, lambda *a, **k: None)


async def account(client):
    response = await client.post('/api/v1/auth/register', json={"username": "p_" + uuid.uuid4().hex[:16], "password": "test12345"})
    assert response.status_code == 201, response.text
    data = response.json()
    return {"Authorization": "Bearer " + data["access_token"]}, uuid.UUID(data["user"]["id"])


async def knowledge(client, headers, name="我的笔记"):
    r = await client.post('/api/v1/kbs', json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def upload(client, headers, kb):
    config = (await client.get('/api/v1/me/model-config', headers=headers)).json()
    if not config['personal']:
        saved = await client.put('/api/v1/me/model-config', json=model_payload(), headers=headers)
        assert saved.status_code == 200, saved.text
    r = await client.post(f'/api/v1/documents?kb_id={kb}', files={"file": ("笔记.txt", "这是一份私有学习笔记。".encode(), "text/plain")}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def model_payload(name="personal-model"):
    ep = {"mode": "api", "model": name, "base_url": "https://models.example/v1", "api_key": "personal-secret", "protocol": "openai"}
    return {"revision": 0, "llm": dict(ep), "embedding": dict(ep), "rerank": dict(ep), "rerank_enabled": False}


async def test_personal_knowledge_and_documents_are_private(client, admin_token):
    a, _ = await account(client)
    b, _ = await account(client)
    kb = await knowledge(client, a)
    doc = await upload(client, a, kb)
    assert (await client.get('/api/v1/kbs', headers=b)).json() == []
    assert (await client.get('/api/v1/documents', headers=b)).json()["total"] == 0
    for method, url, body in [
        ("patch", f'/kbs/{kb}', {"name": "stolen"}), ("delete", f'/kbs/{kb}', None),
        ("get", f'/documents/{doc}', None), ("get", f'/documents/{doc}/chunks', None),
        ("get", f'/documents/{doc}/file', None), ("get", f'/documents/{doc}/preview', None),
        ("post", f'/documents/{doc}/retry', None), ("post", f'/documents/{doc}/reparse', None),
        ("delete", f'/documents/{doc}', None), ("post", '/sessions', {"kb_id": kb}),
    ]:
        r = await client.request(method, '/api/v1' + url, json=body, headers=b)
        assert r.status_code == 404, (url, r.text)
    r = await client.post(f'/api/v1/documents?kb_id={kb}', files={"file": ("x.txt", b"x")}, headers=b)
    assert r.status_code == 404
    # Admin role cannot bypass another person's source ownership via legacy routes.
    admin = {"Authorization": "Bearer " + admin_token}
    assert (await client.get(f'/api/v1/admin/documents/{doc}', headers=admin)).status_code == 404
    assert (await client.delete(f'/api/v1/admin/kbs/{kb}', headers=admin)).status_code == 404


async def test_original_preview_download_and_delete(client):
    a, _ = await account(client)
    kb = await knowledge(client, a)
    doc = await upload(client, a, kb)
    preview = await client.get(f'/api/v1/documents/{doc}/preview', headers=a)
    assert preview.status_code == 200 and "私有学习笔记" in preview.json()["text"]
    original = await client.get(f'/api/v1/documents/{doc}/file', headers=a)
    assert "私有学习笔记" in original.content.decode()
    assert original.headers["cache-control"] == "no-store"
    assert (await client.delete(f'/api/v1/documents/{doc}', headers=a)).status_code == 204
    assert (await client.get(f'/api/v1/documents/{doc}/file', headers=a)).status_code == 404


async def test_personal_models_never_inherit_or_expose_system_keys(client, db_session, monkeypatch):
    a, aid = await account(client)
    b, bid = await account(client)
    config = (await client.get('/api/v1/me/model-config', headers=a)).json()
    assert not config["personal"] and not config["llm"]["api_key_configured"]
    saved = await client.put('/api/v1/me/model-config', json=model_payload(), headers=a)
    assert saved.status_code == 200, saved.text
    assert "personal-secret" not in saved.text
    row = await db_session.get(UserModelConfig, aid)
    assert row.config["llm"]["api_key"] != "personal-secret"
    assert (await models.load_model_settings(aid)).LLM_MODEL == "personal-model"
    assert (await client.get('/api/v1/me/model-config', headers=b)).json()["revision"] == 0
    assert await db_session.get(UserModelConfig, bid) is None
    data = model_payload(); data["revision"] = saved.json()["revision"]
    data["llm"]["api_key"] = None
    assert (await client.put('/api/v1/me/model-config', json=data, headers=a)).status_code == 200
    assert (await models.load_model_settings(aid)).LLM_API_KEY == "personal-secret"
    from app.api.v1 import personal
    seen = []
    async def probe(role, config):
        seen.append(config[role]["api_key"])
        return {"success": True, "message": "OK"}
    monkeypatch.setattr(personal, "_probe", probe)
    r = await client.post('/api/v1/me/model-config/test', headers=b, json={"role": "llm", "endpoint": {**data["llm"], "api_key": None}})
    assert not r.json()["success"] and seen == []
    assert (await client.delete('/api/v1/me/model-config', headers=a)).status_code == 204
    assert not (await client.get('/api/v1/me/model-config', headers=a)).json()["personal"]


async def test_unconfigured_account_cannot_use_environment_models(client, db_session, monkeypatch):
    from app.core.config import Settings
    from app.core.exceptions import BusinessError
    from app.services.providers.llm import get_llm
    from app.services.providers.embeddings import get_embeddings
    from app.services import document_service
    for prefix in ('LLM', 'EMBEDDING', 'RERANK'):
        for suffix, value in (('MODEL', 'must-not-inherit'), ('API_KEY', 'env-secret'), ('BASE_URL', 'https://environment.example/v1')):
            monkeypatch.setenv(f'{prefix}_{suffix}', value)
    monkeypatch.setattr(models, 'get_settings', lambda: Settings())
    a, aid = await account(client)
    for path in ('/me/model-config', '/admin/model-config'):
        config = (await client.get('/api/v1' + path, headers=a)).json()
        assert config['revision'] == 0 and not config['personal'] and not config['rerank_enabled']
        for role in models.ROLES:
            assert config[role]['model'] == config[role]['base_url'] == ''
            assert not config[role]['api_key_configured']
    assert not (await client.get('/api/v1/me/onboarding', headers=a)).json()['personal_models']
    assert await db_session.get(UserModelConfig, aid) is None
    runtime = models.get_model_settings()
    assert runtime.LLM_MODEL == runtime.EMBEDDING_MODEL == runtime.RERANK_MODEL == ''
    assert runtime.LLM_API_KEY == runtime.EMBEDDING_API_KEY == runtime.RERANK_API_KEY == ''
    for provider in (get_llm, get_embeddings):
        with pytest.raises(BusinessError) as exc:
            provider()
        assert exc.value.code == 'model_config_required'
    with pytest.raises(BusinessError):
        await models.load_model_settings(aid)
    kb = await knowledge(client, a)
    enqueue = []
    monkeypatch.setattr(document_service, '_enqueue_parse', lambda did: enqueue.append(did))
    upload_response = await client.post(f'/api/v1/documents?kb_id={kb}', headers=a, files={'file': ('note.txt', b'private note')})
    assert upload_response.status_code == 428 and not enqueue
    assert (await client.get('/api/v1/documents', headers=a)).json()['total'] == 0
    sid = (await client.post('/api/v1/sessions', json={}, headers=a)).json()['id']
    response = await client.post('/api/v1/chat/stream', headers=a, json={'session_id': sid, 'question': 'hello'})
    assert response.status_code == 428 and response.json()['detail']['code'] == 'model_config_required'
    assert (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items'] == []


async def test_first_model_save_accepts_no_rerank_and_reset_returns_empty(client):
    a, aid = await account(client)
    data = model_payload()
    data.pop('rerank')
    for role in ('llm', 'embedding'):
        data[role].update(mode='ollama', api_key='', base_url='http://localhost:11434')
    saved = await client.put('/api/v1/me/model-config', json=data, headers=a)
    assert saved.status_code == 200, saved.text
    assert saved.json()['personal'] and not saved.json()['embedding_changed']
    assert saved.json()['rerank']['model'] == saved.json()['rerank']['base_url'] == ''
    assert (await client.get('/api/v1/me/onboarding', headers=a)).json()['personal_models']
    assert (await models.load_model_settings(aid)).LLM_MODEL == 'personal-model'
    data['revision'] = 1; data['rerank_enabled'] = True
    assert (await client.put('/api/v1/me/model-config', json=data, headers=a)).status_code == 422
    assert (await client.delete('/api/v1/me/model-config', headers=a)).status_code == 204
    blank = (await client.get('/api/v1/me/model-config', headers=a)).json()
    assert not blank['personal'] and blank['llm']['model'] == blank['embedding']['model'] == ''
    assert not (await client.get('/api/v1/me/onboarding', headers=a)).json()['personal_models']


async def test_worker_without_models_fails_without_calling_providers(client, db_session, monkeypatch):
    from app.services.parsing import pipeline
    a, aid = await account(client)
    kb = await knowledge(client, a)
    did = uuid.uuid4()
    db_session.add(Document(id=did, kb_id=uuid.UUID(kb), filename='legacy.txt', file_path='unused.txt', file_type='txt', uploaded_by=aid))
    await db_session.commit()
    async def unexpected(*args):
        pytest.fail('Unconfigured worker must not parse or call providers')
    monkeypatch.setattr(pipeline, '_run_parse_pipeline', unexpected)
    result = await pipeline.run_parse_pipeline(str(did))
    assert result['status'] == 'failed'
    row = await db_session.get(Document, did)
    await db_session.refresh(row)
    assert row.parse_status == 'failed' and '我的模型' in row.error_message


async def test_all_knowledge_retrieval_filters_stale_and_foreign_chunks(client, db_session, monkeypatch):
    from app.services.rag import retrievers, vector_store, cache
    from app.services.providers.embeddings import _cache_key as embed_key
    a, aid = await account(client); b, bid = await account(client)
    ka = await knowledge(client, a); kb = await knowledge(client, b)
    da = await upload(client, a, ka); dbid = await upload(client, b, kb)
    chunks = []
    for did, kid in ((da, ka), (dbid, kb)):
        doc = await db_session.get(Document, uuid.UUID(did)); doc.parse_status = "succeeded"
        ch = Chunk(document_id=doc.id, kb_id=uuid.UUID(kid), seq=0, content=did, token_count=2, content_hash=did)
        db_session.add(ch); chunks.append(ch)
    await db_session.commit()
    monkeypatch.setattr(vector_store, "query_collection", lambda *a, **k: ([str(c.id) for c in chunks], [c.content for c in chunks], [{"kb_id": str(c.kb_id)} for c in chunks], [.9, .9]))
    settings = models.get_model_settings().model_copy(update={"RETRIEVAL_MODE": "vector", "RERANK_ENABLED": False})
    with models.model_settings_scope(settings), retrieval_scope(aid, (uuid.UUID(ka),)):
        hits = await retrievers.hybrid_retrieve('问题', None, [.1])
        assert [h.id for h in hits] == [str(chunks[0].id)]
        assert await retrievers._all_kb_ids() == [uuid.UUID(ka)]
        ak = cache._cache_key('same', 'all', 'model'); ae = embed_key('same')
    with retrieval_scope(bid, (uuid.UUID(kb),)):
        assert ak != cache._cache_key('same', 'all', 'model') and ae != embed_key('same')
    cols = [SimpleNamespace(name=vector_store.collection_name(uuid.UUID(k))) for k in (ka, kb)]
    monkeypatch.setattr(vector_store, "get_chroma_client", lambda: SimpleNamespace(list_collections=lambda: cols))
    with retrieval_scope(aid, (uuid.UUID(ka),)):
        assert vector_store._all_collections() == [cols[0]]
    assert vector_store._all_collections() == []


async def test_chat_retry_reuses_answer_and_skips_current_turn_history(client, monkeypatch):
    from app.api.v1 import chat
    from app.services import message_service
    a, aid = await account(client)
    await client.put('/api/v1/me/model-config', json=model_payload('my-chat'), headers=a)
    sid = (await client.post('/api/v1/sessions', json={}, headers=a)).json()["id"]
    seen = []
    async def stream(kb, question, history, refresh=False):
        seen.append((question, history, refresh, models.get_model_settings().LLM_MODEL, current_scope()[0]))
        yield 'token', {"content": "新回答"}
    async def no_title(*args): pass
    monkeypatch.setattr(chat, 'run_qa_stream', stream)
    monkeypatch.setattr(message_service, 'auto_title_session', no_title)
    first = await client.post('/api/v1/chat/stream', json={"session_id": sid, "question": "原问题"}, headers=a)
    assert 'event: start' in first.text and 'event: done' in first.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()["items"]
    mid = items[-1]["id"]
    retry = await client.post('/api/v1/chat/stream', json={"session_id": sid, "question": "篡改的问题", "retry_message_id": mid}, headers=a)
    assert 'event: done' in retry.text
    after = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()["items"]
    assert len(after) == 2 and after[-1]["id"] == mid
    assert seen[-1] == ('原问题', [], True, 'my-chat', str(aid))


async def test_export_restore_and_delete_only_own_data(client, db_session, monkeypatch):
    a, aid = await account(client); b, _ = await account(client)
    ka = await knowledge(client, a, '私有导出'); kb = await knowledge(client, b, '不能导出')
    doc = await upload(client, a, ka)
    r = await client.get('/api/v1/me/export', headers=a)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        data = json.loads(z.read('knowbase.json'))
        assert [k['id'] for k in data['knowledge_bases']] == [ka]
        assert 'personal-secret' not in z.read('knowbase.json').decode()
        assert len(z.read(f'documents/{doc}.txt')) > 0
    restored = await client.post('/api/v1/me/import', files={"file": ('backup.zip', r.content)}, headers=a)
    assert restored.status_code == 200, restored.text
    assert restored.json()['documents'] == 1
    assert len((await client.get('/api/v1/kbs', headers=a)).json()) == 2
    assert len((await client.get('/api/v1/kbs', headers=b)).json()) == 1
    invalid = await client.post('/api/v1/me/import', files={"file": ('bad.zip', b'invalid')}, headers=a)
    assert invalid.status_code == 400
    assert (await client.post('/api/v1/me/delete-data', json={"password": "wrong", "confirmation": "删除我的全部数据"}, headers=a)).status_code == 400
    from app.services import personal_data
    class EmptyCache:
        async def scan_iter(self, **kwargs):
            if False: yield ''
    monkeypatch.setattr(personal_data, 'get_redis', lambda: EmptyCache())
    deleted = await client.post('/api/v1/me/delete-data', json={"password": "test12345", "confirmation": "删除我的全部数据"}, headers=a)
    assert deleted.status_code == 204, deleted.text
    assert (await client.get('/api/v1/kbs', headers=a)).json() == []
    assert (await client.get('/api/v1/kbs', headers=b)).json()[0]['id'] == kb
    assert (await client.get('/api/v1/auth/me', headers=a)).status_code == 200
    await db_session.refresh(await db_session.get(User, aid))
    assert await db_session.get(UserModelConfig, aid) is None


async def test_onboarding_progress_and_document_failure_retry(client, db_session):
    a, _ = await account(client)
    assert (await client.get('/api/v1/me/onboarding', headers=a)).json()['documents'] == 0
    kb = await knowledge(client, a); doc = await upload(client, a, kb)
    assert (await client.get('/api/v1/me/onboarding', headers=a)).json()['processing'] == 1
    row = await db_session.get(Document, uuid.UUID(doc)); row.parse_status = 'failed'; row.error_message = 'temporary network failure'
    await db_session.commit()
    assert (await client.get('/api/v1/me/onboarding', headers=a)).json()['failed'] == 1
    assert (await client.post(f'/api/v1/documents/{doc}/retry', headers=a)).json()['parse_status'] == 'pending'


async def test_citations_recheck_owner_and_hide_deleted_sources(client, db_session):
    a, aid = await account(client); b, bid = await account(client)
    kb = await knowledge(client, a); did = await upload(client, a, kb)
    doc = await db_session.get(Document, uuid.UUID(did)); doc.parse_status = 'succeeded'
    chunk = Chunk(document_id=doc.id, kb_id=doc.kb_id, seq=0, content='private source', token_count=2, content_hash='x')
    sa, sb = ChatSession(user_id=aid), ChatSession(user_id=bid)
    db_session.add_all([chunk, sa, sb]); await db_session.flush()
    ma, mb = Message(session_id=sa.id, role='assistant', content='answer'), Message(session_id=sb.id, role='assistant', content='legacy answer')
    db_session.add_all([ma, mb]); await db_session.flush()
    db_session.add_all([Citation(message_id=m.id, chunk_id=chunk.id, rank=1) for m in (ma, mb)])
    await db_session.commit()
    own = await client.get(f'/api/v1/messages/{ma.id}/citations', headers=a)
    assert own.json()[0]['document_id'] == did and own.json()[0]['source'] is None
    assert (await client.get(f'/api/v1/messages/{ma.id}/citations', headers=b)).status_code == 404
    assert (await client.get(f'/api/v1/messages/{mb.id}/citations', headers=b)).json() == []
    assert (await client.delete(f'/api/v1/documents/{did}', headers=a)).status_code == 204
    assert (await client.get(f'/api/v1/messages/{ma.id}/citations', headers=a)).json() == []


async def test_parse_task_uses_knowledge_owner_personal_model(client, db_session, monkeypatch):
    from app.services.parsing import pipeline
    a, aid = await account(client)
    kb = await knowledge(client, a); doc = await upload(client, a, kb)
    data = model_payload('owner-embedding')
    data['revision'] = (await client.get('/api/v1/me/model-config', headers=a)).json()['revision']
    assert (await client.put('/api/v1/me/model-config', json=data, headers=a)).status_code == 200
    async def parse(document_id):
        assert document_id == doc
        assert models.get_model_settings().EMBEDDING_MODEL == 'owner-embedding'
        assert current_scope() == (str(aid), (uuid.UUID(kb),))
        return {"status": "succeeded"}
    monkeypatch.setattr(pipeline, '_run_parse_pipeline', parse)
    assert (await pipeline.run_parse_pipeline(doc))['status'] == 'succeeded'
    assert current_scope() == ('', ())


async def test_busy_deletion_and_failed_index_cleanup_do_not_report_success(client, db_session, monkeypatch):
    a, _ = await account(client)
    kb = await knowledge(client, a); did = await upload(client, a, kb)
    doc = await db_session.get(Document, uuid.UUID(did)); doc.parse_status = 'parsing'
    await db_session.commit()
    assert (await client.delete(f'/api/v1/documents/{did}', headers=a)).status_code == 409
    assert (await client.post('/api/v1/me/delete-data', json={"password": "test12345", "confirmation": "删除我的全部数据"}, headers=a)).status_code == 409
    doc.parse_status = 'failed'; await db_session.commit()
    from app.services.rag import vector_store
    def unavailable(*args, **kwargs): raise RuntimeError('offline')
    monkeypatch.setattr(vector_store, 'delete_by_document', unavailable)
    assert (await client.delete(f'/api/v1/documents/{did}', headers=a)).status_code == 503
    assert (await client.get(f'/api/v1/documents/{did}/file', headers=a)).status_code == 200


async def test_archive_path_traversal_is_rejected_without_partial_import(client):
    a, _ = await account(client)
    kid, did = str(uuid.uuid4()), str(uuid.uuid4())
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        z.writestr('knowbase.json', json.dumps({"format": "knowbase-personal-v1", "knowledge_bases": [{"id": kid, "name": "unsafe"}],
            "documents": [{"id": did, "kb_id": kid, "filename": "note.txt", "file_type": "txt", "archive_path": "../../outside.txt"}], "sessions": []}))
        z.writestr('../../outside.txt', 'secret')
    r = await client.post('/api/v1/me/import', files={"file": ('backup.zip', output.getvalue())}, headers=a)
    assert r.status_code == 400
    assert (await client.get('/api/v1/kbs', headers=a)).json() == []


async def test_interrupted_answer_preserves_partial_content_and_can_retry(client, monkeypatch):
    from app.api.v1 import chat
    from app.services import message_service
    a, _ = await account(client)
    assert (await client.put('/api/v1/me/model-config', json=model_payload(), headers=a)).status_code == 200
    sid = (await client.post('/api/v1/sessions', json={}, headers=a)).json()['id']
    async def broken(*args, **kwargs):
        yield 'token', {"content": "已经收到的内容"}
        raise RuntimeError('upstream disconnected')
    monkeypatch.setattr(chat, 'run_qa_stream', broken)
    response = await client.post('/api/v1/chat/stream', json={"session_id": sid, "question": "问题"}, headers=a)
    assert 'event: error' in response.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items']
    assert items[-1]['status'] == 'failed' and items[-1]['content'] == '已经收到的内容'
    async def recovered(*args, **kwargs):
        yield 'token', {"content": "恢复后的完整回答"}
    async def title(*args): pass
    monkeypatch.setattr(chat, 'run_qa_stream', recovered)
    monkeypatch.setattr(message_service, 'auto_title_session', title)
    response = await client.post('/api/v1/chat/stream', json={"session_id": sid, "question": "问题", "retry_message_id": items[-1]['id']}, headers=a)
    assert 'event: done' in response.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items']
    assert len(items) == 2 and items[-1]['content'] == '恢复后的完整回答'


async def test_adaptive_answer_mode_and_citations_survive_reload_and_retry(client, db_session, monkeypatch):
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from unittest.mock import AsyncMock
    from app.services.rag import chain, relevance
    from app.services.rag.retrievers import RetrievedChunk
    from app.services import message_service
    a, _ = await account(client)
    kb = await knowledge(client, a)
    did = await upload(client, a, kb)
    doc = await db_session.get(Document, uuid.UUID(did)); doc.parse_status = 'succeeded'
    chunk = Chunk(document_id=doc.id, kb_id=doc.kb_id, seq=0, content='耳机售价 299 元', content_hash='adaptive')
    db_session.add(chunk); await db_session.commit()
    candidate = RetrievedChunk(id=str(chunk.id), text=chunk.content, score=.02,
        metadata={'filename':doc.filename, 'document_id':did})
    monkeypatch.setattr(chain, 'embed_with_cache', AsyncMock(return_value=[[.1]]))
    monkeypatch.setattr(chain, 'hybrid_retrieve', AsyncMock(return_value=[candidate]))
    monkeypatch.setattr(chain, 'condense_question', AsyncMock(side_effect=lambda h, q: q))
    monkeypatch.setattr(chain.cache, 'get_cached_answer', AsyncMock(return_value=None))
    monkeypatch.setattr(chain.cache, 'set_cached_answer', AsyncMock())
    judge = FakeListChatModel(responses=['{"relevant_ids":[1]}', '{"relevant_ids":[]}', '{"relevant_ids":[]}'])
    answer = FakeListChatModel(responses=['售价为 299 元。[1]', '这是模型直接回答。', '可以从 Python 基础语法开始。'])
    monkeypatch.setattr(relevance, 'get_llm', lambda: judge)
    monkeypatch.setattr(chain, 'get_llm', lambda: answer)
    monkeypatch.setattr(message_service, 'auto_title_session', AsyncMock())
    sid = (await client.post('/api/v1/sessions', json={'kb_id':kb}, headers=a)).json()['id']
    first = await client.post('/api/v1/chat/stream', json={'session_id':sid, 'question':'耳机多少钱？'}, headers=a)
    assert '"answer_mode": "knowledge"' in first.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items']
    mid = items[-1]['id']
    assert items[-1]['answer_mode'] == 'knowledge' and items[-1]['citations_count'] == 1
    retry = await client.post('/api/v1/chat/stream', json={'session_id':sid, 'question':'ignored', 'retry_message_id':mid}, headers=a)
    assert '"answer_mode": "general"' in retry.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items']
    assert len(items) == 2 and items[-1]['id'] == mid
    assert items[-1]['answer_mode'] == 'general' and items[-1]['citations_count'] == 0
    assert (await client.get(f'/api/v1/messages/{mid}/citations', headers=a)).json() == []
    unrelated = await client.post('/api/v1/chat/stream', json={'session_id':sid, 'question':'怎么学习 Python？'}, headers=a)
    tokens = [json.loads(block.split('data: ', 1)[1])['content'] for block in unrelated.text.split('\n\n')
              if block.startswith('event: token\n')]
    assert 'Python' in ''.join(tokens) and '"answer_mode": "general"' in unrelated.text
    items = (await client.get(f'/api/v1/sessions/{sid}/messages', headers=a)).json()['items']
    assert len(items) == 4 and items[-1]['answer_mode'] == 'general' and items[-1]['citations_count'] == 0

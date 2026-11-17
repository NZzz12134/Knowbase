"""个人配置、密钥保护、模型协议与跨配置索引隔离回归测试。"""
import copy
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import delete, select

from app.models import ModelConfig, User, UserModelConfig
from app.services import model_config_service as service


@pytest.fixture(autouse=True)
async def clean_model_config(db_session):
    await db_session.execute(delete(ModelConfig))
    await db_session.execute(delete(UserModelConfig))
    await db_session.commit()
    yield
    await db_session.execute(delete(ModelConfig))
    await db_session.execute(delete(UserModelConfig))
    await db_session.commit()


def config_payload():
    endpoint = {"mode": "api", "model": "test-model", "base_url": "https://models.example/v1", "api_key": "secret-test-key", "protocol": "openai"}
    return {"revision": 0, "llm": dict(endpoint), "embedding": dict(endpoint), "rerank": dict(endpoint), "rerank_enabled": True}


async def test_personal_config_secret_round_trip(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = config_payload()
    response = await client.put("/api/v1/admin/model-config", json=data, headers=headers)
    assert response.status_code == 200, response.text
    public = response.json()
    assert public["revision"] == 1
    assert "secret-test-key" not in response.text
    assert "api_key" not in public["llm"]
    assert public["llm"]["api_key_configured"] is True
    user_id = await db_session.scalar(select(User.id).where(User.username == "admin"))
    row = await db_session.get(UserModelConfig, user_id)
    assert await db_session.get(ModelConfig, 1) is None
    assert "secret-test-key" not in json.dumps(row.config)
    assert (await service.read_config(db_session, user_id))["llm"]["api_key"] == "secret-test-key"

    for role in service.ROLES:
        data[role]["api_key"] = None
    data["revision"] = 1
    data["llm"]["model"] = "new-model"
    response = await client.put("/api/v1/admin/model-config", json=data, headers=headers)
    assert response.status_code == 200
    runtime = await service.load_model_settings(user_id)
    assert runtime.LLM_MODEL == "new-model"
    assert runtime.LLM_API_KEY == "secret-test-key"
    assert runtime.MODEL_CONFIG_REVISION == 2
    assert (await client.put("/api/v1/admin/model-config", json=data, headers=headers)).status_code == 409
    assert "secret-test-key" not in (await client.get("/api/v1/admin/model-config", headers=headers)).text


async def test_ollama_save_clear_key(client, admin_token, db_session):
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = config_payload()
    for role in service.ROLES:
        data[role].update(mode="ollama", base_url="http://localhost:11434", api_key="")
    response = await client.put("/api/v1/admin/model-config", json=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["llm"]["api_key_configured"] is False
    user_id = await db_session.scalar(select(User.id).where(User.username == "admin"))
    runtime = await service.load_model_settings(user_id)
    from app.services.providers.llm import get_llm
    with service.model_settings_scope(runtime):
        llm = get_llm()
        assert str(llm.openai_api_base) == "http://localhost:11434/v1"
        assert llm.model_name == "test-model"
    assert service.get_model_settings().MODEL_CONFIG_REVISION == 0


async def test_equal_model_access_and_validation(client, admin_token, monkeypatch):
    from app.api.v1 import personal
    monkeypatch.setattr(personal, "_probe", AsyncMock(return_value={"success": True, "message": "连接成功"}))
    for method, path, body in [("GET", "", None), ("PUT", "", config_payload()), ("POST", "/test", {"role": "llm", "endpoint": config_payload()["llm"]})]:
        response = await client.request(method, "/api/v1/admin/model-config" + path, json=body)
        assert response.status_code == 401
    name = "modeluser_" + uuid.uuid4().hex[:10]
    await client.post("/api/v1/auth/register", json={"username": name, "password": "testPass123"})
    login = await client.post("/api/v1/auth/login", json={"username": name, "password": "testPass123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for method, path, body in [("GET", "", None), ("PUT", "", config_payload()), ("POST", "/test", {"role": "llm", "endpoint": config_payload()["llm"]})]:
        assert (await client.request(method, "/api/v1/admin/model-config" + path, json=body, headers=headers)).status_code == 200
    # 旧接口只修改本人的配置，另一个账号不受影响。
    assert (await client.get("/api/v1/me/model-config", headers={"Authorization": f"Bearer {admin_token}"})).json()["revision"] == 0
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = config_payload()
    data["embedding"]["base_url"] = "file:///tmp/model"
    assert (await client.put("/api/v1/admin/model-config", json=data, headers=headers)).status_code == 422


async def test_connection_uses_unsaved_settings_without_persisting(client, admin_token, monkeypatch):
    from app.services.providers import embeddings
    seen = []

    def fake_embeddings():
        settings = service.get_model_settings()
        seen.append((settings.EMBEDDING_MODEL, settings.EMBEDDING_MODE))
        return SimpleNamespace(aembed_documents=AsyncMock(return_value=[[0.1, 0.2, 0.3]]))

    monkeypatch.setattr(embeddings, "get_embeddings", fake_embeddings)
    endpoint = {**config_payload()["embedding"], "mode": "ollama", "model": "bge-m3", "api_key": ""}
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.post("/api/v1/admin/model-config/test", json={"role": "embedding", "endpoint": endpoint}, headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "3" in response.json()["message"]
    assert seen == [("bge-m3", "ollama")]
    assert (await client.get("/api/v1/admin/model-config", headers=headers)).json()["revision"] == 0


@pytest.mark.parametrize("mode,path", [("api", "/v1/embeddings"), ("ollama", "/api/embed")])
async def test_embedding_protocols(monkeypatch, mode, path):
    from app.services.providers import embeddings
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body == {"model": "embed-test", "input": ["one", "two"]}
        data = {"embeddings": [[1., 0.], [0., 1.]]} if mode == "ollama" else {"data": [{"index": 1, "embedding": [0., 1.]}, {"index": 0, "embedding": [1., 0.]}]}
        return httpx.Response(200, json=data)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(embeddings, "httpx", SimpleNamespace(AsyncClient=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)))
    provider = embeddings.OpenAICompatEmbeddings("embed-test", "key", "http://localhost:11434/v1", mode=mode)
    assert await provider.aembed_documents(["one", "two"]) == [[1., 0.], [0., 1.]]
    assert requests[0].url.path == path


@pytest.mark.parametrize("mode,protocol,path", [("api", "openai", "/v1/rerank"), ("api", "dashscope", "/api/v1/services/rerank/text-rerank/text-rerank"), ("ollama", "openai", "/api/chat")])
async def test_rerank_protocols(monkeypatch, mode, protocol, path):
    from app.services.providers import rerank as module
    config = config_payload()
    config["rerank"].update(mode=mode, protocol=protocol, base_url="http://localhost:11434/v1", model="rank-test")
    config["rerank_enabled"] = True
    paths = []

    def handler(request):
        paths.append(request.url.path)
        body = json.loads(request.content)
        assert body["model"] == "rank-test"
        ranked = [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]
        if mode == "ollama":
            document = json.loads(body["messages"][1]["content"])["document"]
            return httpx.Response(200, json={"message": {"content": json.dumps({"score": 0.9 if document == "relevant" else 0.1})}})
        return httpx.Response(200, json={"output": {"results": ranked}} if protocol == "dashscope" else {"results": ranked})

    client_type = httpx.AsyncClient
    async with client_type(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(module, "_client", lambda: client)
        monkeypatch.setattr(module, "httpx", SimpleNamespace(AsyncClient=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw)))
        with service.model_settings_scope(service.runtime_settings(config)):
            assert await module.rerank("question", ["irrelevant", "relevant"], 1) == [(1, 0.9)]
    assert paths and set(paths) == {path}


async def test_cache_and_collection_isolation(monkeypatch):
    from app.services.providers.embeddings import _cache_key
    from app.services.rag import vector_store, cache
    config = config_payload()
    original = service.runtime_settings(config)
    kb = uuid.uuid4()
    with service.model_settings_scope(original):
        old_name = vector_store.collection_name(kb)
        old_key = _cache_key("question")
        old_answer = cache._cache_key("question", str(kb), original.LLM_MODEL)
    changed = copy.deepcopy(config)
    changed["embedding"]["base_url"] = "http://another-host:11434"
    changed["embedding"]["mode"] = "ollama"
    changed["revision"] = 2
    with service.model_settings_scope(service.runtime_settings(changed)):
        new_name = vector_store.collection_name(kb)
        assert old_name != new_name
        assert old_key != _cache_key("question")
        assert old_answer != cache._cache_key("question", str(kb), original.LLM_MODEL)
        cols = [SimpleNamespace(name=old_name), SimpleNamespace(name=new_name)]
        monkeypatch.setattr(vector_store, "get_chroma_client", lambda: SimpleNamespace(list_collections=lambda: cols))
        from app.services.personal_access import retrieval_scope
        with retrieval_scope(uuid.uuid4(), (kb,)):
            assert vector_store._all_collections() == [cols[1]]
        assert vector_store._all_collections() == []  # unscoped queries fail closed


def test_model_error_does_not_leak_secret():
    from app.api.v1.model_config import _test_error
    request = httpx.Request("POST", "http://models.example")
    response = httpx.Response(400, json={"error": {"code": "Arrearage", "message": "secret-key"}}, request=request)
    message = _test_error(httpx.HTTPStatusError("secret-key", request=request, response=response))
    assert "欠费" in message
    assert "secret-key" not in message


async def test_parse_task_reads_latest_config_and_keeps_snapshot(monkeypatch, db_session):
    from app.services.parsing import pipeline
    config = config_payload()
    config["embedding"]["model"] = "first-embedding"
    latest = service.runtime_settings(config)

    from app.models import Document, KnowledgeBase, User
    from sqlalchemy import select
    admin = await db_session.scalar(select(User).where(User.username == "admin"))
    kb = KnowledgeBase(name="snapshot", created_by=admin.id)
    db_session.add(kb)
    await db_session.flush()
    doc = Document(kb_id=kb.id, filename="snapshot.txt", file_path="test.txt", file_type="txt", uploaded_by=admin.id)
    db_session.add(doc)
    await db_session.commit()

    async def load(user_id=None):
        assert user_id == admin.id
        return latest

    async def parse(document_id):
        before = service.get_model_settings().EMBEDDING_MODEL
        # 后台配置改变时，已运行任务仍持有自己的快照。
        nonlocal latest
        latest = latest.model_copy(update={"EMBEDDING_MODEL": "second-embedding"})
        assert service.get_model_settings().EMBEDDING_MODEL == before
        return {"model": before}

    monkeypatch.setattr(service, "load_model_settings", load)
    monkeypatch.setattr(pipeline, "_run_parse_pipeline", parse)
    assert await pipeline.run_parse_pipeline(str(doc.id)) == {"model": "first-embedding"}
    assert await pipeline.run_parse_pipeline(str(doc.id)) == {"model": "second-embedding"}
    assert service.get_model_settings().EMBEDDING_MODEL != "second-embedding"


async def test_condense_uses_current_model_after_switch(monkeypatch):
    from app.services.rag import condense
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    def llm():
        return FakeListChatModel(responses=[service.get_model_settings().LLM_MODEL])

    monkeypatch.setattr(condense, "get_llm", llm)
    original = service.get_model_settings()
    history = [{"role": "user", "content": "图书馆几点开放"}]
    for model in ("first-model", "second-model"):
        with service.model_settings_scope(original.model_copy(update={"LLM_MODEL": model})):
            assert await condense.condense_question(history, "周末呢") == model


async def test_chat_request_loads_saved_config(client, admin_token, monkeypatch):
    from app.api.v1 import chat
    from app.services import message_service
    headers = {"Authorization": f"Bearer {admin_token}"}
    data = config_payload()
    saved = await client.put("/api/v1/admin/model-config", json=data, headers=headers)
    assert saved.status_code == 200
    session = await client.post("/api/v1/sessions", json={"title": "model-config-test"}, headers=headers)
    assert session.status_code in (200, 201)
    seen = []

    async def stream(*args, **kwargs):
        seen.append(service.get_model_settings().LLM_MODEL)
        yield "token", {"content": "fake answer"}

    async def title(*args):
        assert service.get_model_settings().LLM_MODEL == seen[-1]

    monkeypatch.setattr(chat, "run_qa_stream", stream)
    monkeypatch.setattr(message_service, "auto_title_session", title)
    for model in ("test-model", "new-chat-model"):
        if model == "new-chat-model":
            data["revision"] = saved.json()["revision"]
            data["llm"]["model"] = model
            assert (await client.put("/api/v1/admin/model-config", json=data, headers=headers)).status_code == 200
        response = await client.post("/api/v1/chat/stream", json={"session_id": session.json()["id"], "question": "test"}, headers=headers)
        assert response.status_code == 200
        assert "fake answer" in response.text and "event: done" in response.text
        assert seen[-1] == model


async def test_saved_index_namespace_survives_env_changes(db_session, monkeypatch):
    from app.schemas.model_config_schema import ModelConfigIn
    from app.services.rag.vector_store import collection_name
    config = config_payload()
    data = config_payload()
    data["embedding"] = config["embedding"]
    saved = await service.save_config(db_session, ModelConfigIn(**data))
    assert saved["embedding_changed"] is False
    persisted = await service.read_config(db_session)
    with service.model_settings_scope(service.runtime_settings(persisted)):
        original = collection_name(uuid.UUID(int=1))
    monkeypatch.setenv("EMBEDDING_MODEL", "different-env-default")
    with service.model_settings_scope(service.runtime_settings(persisted)):
        assert collection_name(uuid.UUID(int=1)) == original


async def test_legacy_role_migration_preserves_personal_keys(db_session):
    from app.db.init_db import migrate_legacy_roles
    from app.schemas.model_config_schema import ModelConfigIn

    owners = [User(username="legacy_" + uuid.uuid4().hex[:10], hashed_password="unused", role="admin") for _ in range(2)]
    other = User(username="legacy_" + uuid.uuid4().hex[:10], hashed_password="unused")
    db_session.add_all([*owners, other])
    await db_session.commit()
    try:
        await service.save_config(db_session, ModelConfigIn(**config_payload()))
        personal = config_payload()
        personal["llm"]["api_key"] = "keep-personal-key"
        await service.save_config(db_session, ModelConfigIn(**personal), owners[1].id)
        legacy = await db_session.get(ModelConfig, 1)

        await migrate_legacy_roles(db_session)
        await db_session.refresh(owners[0])
        await db_session.refresh(owners[1])
        assert all(user.role == "user" for user in owners)
        copied = await db_session.get(UserModelConfig, owners[0].id)
        assert copied.config == legacy.config and copied.revision == legacy.revision
        assert (await service.read_config(db_session, owners[0].id))["llm"]["api_key"] == "secret-test-key"
        assert (await service.read_config(db_session, owners[1].id))["llm"]["api_key"] == "keep-personal-key"
        assert await db_session.get(UserModelConfig, other.id) is None
        # 没有个人配置时不会使用遗留全局配置或安装环境。
        from app.core.exceptions import BusinessError
        for user_id in (other.id, None):
            with pytest.raises(BusinessError) as exc:
                await service.load_model_settings(user_id)
            assert exc.value.code == "model_config_required"
        await migrate_legacy_roles(db_session)
        assert (await service.read_config(db_session, owners[0].id))["revision"] == legacy.revision
    finally:
        ids = [user.id for user in [*owners, other]]
        await db_session.execute(delete(UserModelConfig).where(UserModelConfig.user_id.in_(ids)))
        await db_session.execute(delete(User).where(User.id.in_(ids)))
        await db_session.commit()

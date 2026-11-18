"""会话与消息 API 测试：CRUD、所有权隔离、软删除、历史排序。"""
import uuid

import pytest


@pytest.fixture(autouse=True)
async def _clean(db_session):
    from sqlalchemy import delete

    from app.models import ChatSession, Message, User

    await db_session.execute(delete(Message))
    await db_session.execute(delete(ChatSession))
    await db_session.execute(delete(User).where(User.username != "admin"))
    await db_session.commit()
    yield


async def _register(client, username):
    resp = await client.post(
        "/api/v1/auth/register", json={"username": username, "password": "abc12345"}
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


async def test_session_crud_flow(client):
    token = await _register(client, "sessuser1")

    # 新建
    resp = await client.post("/api/v1/sessions", json={"title": "我的会话"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    session_id = resp.json()["id"]
    assert resp.json()["title"] == "我的会话"

    # 列表
    resp = await client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == session_id

    # 重命名
    resp = await client.patch(
        f"/api/v1/sessions/{session_id}", json={"title": "改名了"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "改名了"

    # 软删除
    resp = await client.delete(f"/api/v1/sessions/{session_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204
    resp = await client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {token}"})
    assert len(resp.json()["items"]) == 0


async def test_session_ownership_isolation(client, db_session):
    """用户 B 访问用户 A 的会话 → 404；消息历史同样隔离。"""
    token_a = await _register(client, "ownerA")
    token_b = await _register(client, "ownerB")

    resp = await client.post("/api/v1/sessions", json={"title": "A的会话"}, headers={"Authorization": f"Bearer {token_a}"})
    session_id = resp.json()["id"]

    # B 重命名 A 的会话 → 404
    resp = await client.patch(
        f"/api/v1/sessions/{session_id}", json={"title": "劫持"}, headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

    # B 读 A 的消息历史 → 404
    resp = await client.get(
        f"/api/v1/sessions/{session_id}/messages", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert resp.status_code == 404

    # B 删除 A 的会话 → 404
    resp = await client.delete(f"/api/v1/sessions/{session_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404


async def test_message_history_order_and_preview(client, db_session):
    """历史按时间正序；列表预览为最后一条消息。"""
    from app.db.base import utcnow
    from app.models import ChatSession, Message, User

    token = await _register(client, "histuser")

    # 直接 DB 造数据（同一秒内写入多条，模拟原秒级精度下的乱序风险场景）
    from datetime import timedelta

    user_row = (
        await db_session.execute(
            __import__("sqlalchemy").select(User).where(User.username == "histuser")
        )
    ).scalar_one()
    session = ChatSession(user_id=user_row.id, title="历史会话")
    db_session.add(session)
    await db_session.flush()
    now = utcnow()
    for i, (role, content) in enumerate(
        [("user", "问题1"), ("assistant", "回答1"), ("user", "问题2"), ("assistant", "回答2")]
    ):
        # 同一秒内、相隔仅微秒级（真实插入行为的模拟）
        db_session.add(
            Message(
                session_id=session.id, role=role, content=content,
                created_at=now + timedelta(microseconds=i * 1000),
            )
        )
    await db_session.commit()

    # 历史正序且交替
    resp = await client.get(
        f"/api/v1/sessions/{session.id}/messages", headers={"Authorization": f"Bearer {token}"}
    )
    items = resp.json()["items"]
    assert [m["role"] for m in items] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in items] == ["问题1", "回答1", "问题2", "回答2"]

    # 会话列表预览 = 最后一条
    resp = await client.get("/api/v1/sessions", headers={"Authorization": f"Bearer {token}"})
    items = resp.json()["items"]
    assert items[0]["last_message_preview"] == "回答2"


async def test_invalid_session_404(client):
    token = await _register(client, "nobodyuser")
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/sessions/{fake_id}/messages", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


async def test_upgrade_and_reload_long_answer(client, db_session):
    """旧 TEXT 自动扩容且可重复启动，超过 64KB 的回答能完整存取。"""
    from app.db.init_db import create_tables
    from app.db.session import engine
    from app.models import Message

    async with engine.begin() as conn:
        assert await conn.scalar(__import__("sqlalchemy").text("SELECT DATABASE()")) == "rag_qa_test"
        await conn.exec_driver_sql("ALTER TABLE messages MODIFY COLUMN content TEXT NOT NULL")
    await create_tables()
    await create_tables()
    async with engine.begin() as conn:
        column = await conn.exec_driver_sql(
            "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'messages' AND COLUMN_NAME = 'content'"
        )
        assert column.scalar_one() == "mediumtext"

    token = await _register(client, "longansweruser")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post("/api/v1/sessions", json={"title": "长回答"}, headers=headers)
    session_id = response.json()["id"]
    content = "长回答" * 30_000
    db_session.add(Message(session_id=uuid.UUID(session_id), role="assistant", content=content))
    await db_session.commit()
    response = await client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"][0]["content"] == content


async def test_equal_timestamps_history_pagination_and_preview(client, db_session):
    """复现问题与回复同一微秒且 UUID 逆序，验证历史、分页、上下文及预览。"""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models import ChatSession, Message, User
    from app.services.message_service import get_recent_history

    token = await _register(client, "tiedtimeuser")
    user = await db_session.scalar(select(User).where(User.username == "tiedtimeuser"))
    session = ChatSession(user_id=user.id, title="相同时间")
    other = ChatSession(user_id=user.id, title="另一会话")
    db_session.add_all([session, other])
    await db_session.flush()
    now = datetime(2026, 11, 17, 1, 43, 16, 280521)
    for i, (role, content) in enumerate([
        ("user", "问题1"), ("assistant", "回答1"),
        ("user", "问题2"), ("assistant", "回答2"),
    ]):
        db_session.add(Message(
            id=uuid.UUID(int=100 - i), session_id=session.id, role=role, content=content,
            created_at=now + timedelta(seconds=i // 2),
        ))
    db_session.add(Message(session_id=other.id, role="user", content="另一会话的问题", created_at=now + timedelta(seconds=1)))
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/sessions/{session.id}/messages"
    expected = ["问题1", "回答1", "问题2", "回答2"]
    for _ in range(2):
        response = await client.get(url, headers=headers)
        assert [m["content"] for m in response.json()["items"]] == expected
    pages = []
    for page in range(1, 5):
        response = await client.get(url, params={"page": page, "page_size": 1}, headers=headers)
        pages.extend(m["content"] for m in response.json()["items"])
    assert pages == expected
    assert [m["content"] for m in await get_recent_history(db_session, session.id, 3)] == expected[-3:]
    response = await client.get("/api/v1/sessions", headers=headers)
    previews = {m["id"]: m["last_message_preview"] for m in response.json()["items"]}
    assert previews[str(session.id)] == "回答2"
    assert previews[str(other.id)] == "另一会话的问题"


async def test_new_messages_order_when_clock_does_not_advance(client, db_session, monkeypatch):
    from datetime import datetime
    from sqlalchemy import select
    from app.models import ChatSession, User
    from app.services import message_service

    await _register(client, "fixedclockuser")
    user = await db_session.scalar(select(User).where(User.username == "fixedclockuser"))
    session = ChatSession(user_id=user.id)
    db_session.add(session)
    await db_session.commit()
    now = datetime(2026, 11, 17, 1, 43, 16, 280521)
    monkeypatch.setattr(message_service, "utcnow", lambda: now)
    messages = []
    for question in ("问题1", "问题2"):
        messages.append(await message_service.create_user_message(db_session, session.id, question))
        messages.append(await message_service.create_assistant_placeholder(db_session, session.id))
    await db_session.commit()
    timestamps = [m.created_at for m in messages]
    assert timestamps[0] == now
    assert all(a < b for a, b in zip(timestamps, timestamps[1:]))

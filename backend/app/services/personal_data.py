"""Portable personal archives: original documents and chat history, never credentials."""
import asyncio
import json
import tempfile
import uuid
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select

from app.core.exceptions import BusinessError
from app.core.redis_client import get_redis
from app.models import ChatSession, Chunk, Citation, Document, KnowledgeBase, Message, UserModelConfig
from app.services.message_order import message_order
from app.utils.file_utils import resolve_storage_path, save_upload, validate_upload


async def export_archive(db, user):
    kbs = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.created_by == user.id))).scalars().all()
    docs = (await db.execute(select(Document).where(Document.kb_id.in_([k.id for k in kbs]), Document.deleted_at.is_(None)))).scalars().all()
    if any(d.file_type != "url" and not resolve_storage_path(d.file_path).is_file() for d in docs):
        raise BusinessError("backup_missing_file", "部分原文件已缺失，请在我的文档重新上传或移除缺失记录后备份", 409)
    sessions = (await db.execute(select(ChatSession).where(ChatSession.user_id == user.id, ChatSession.is_deleted.is_(False)))).scalars().all()
    messages = (await db.execute(select(Message).where(Message.session_id.in_([s.id for s in sessions])).order_by(*message_order()))).scalars().all()
    manifest = {"format": "knowbase-personal-v1", "knowledge_bases": [
        {"id": str(k.id), "name": k.name, "description": k.description} for k in kbs],
        "documents": [{"id": str(d.id), "kb_id": str(d.kb_id), "filename": d.filename,
                       "file_type": d.file_type, "source_url": d.source_url,
                       "archive_path": f"documents/{d.id}.{d.file_type}" if d.file_type != "url" else None} for d in docs],
        "sessions": [{"id": str(s.id), "title": s.title, "kb_id": str(s.kb_id) if s.kb_id else None,
                      "messages": [{"id": str(m.id), "role": m.role, "content": m.content, "status": m.status, "created_at": m.created_at.isoformat(),
                                    "reasoning_content": (m.token_usage or {}).get("reasoning_content", ""),
                                    "answer_mode": (m.token_usage or {}).get("answer_mode")}
                                   for m in messages if m.session_id == s.id]} for s in sessions]}
    # Preserve source snapshots without leaking file-system paths or another owner's citations.
    sources = (await db.execute(select(Citation, Chunk, Document).join(Chunk, Chunk.id == Citation.chunk_id)
        .join(Document, Document.id == Chunk.document_id).where(
            Citation.message_id.in_([m.id for m in messages]), Document.kb_id.in_([k.id for k in kbs]),
            Document.deleted_at.is_(None)).order_by(Citation.rank))).all()
    manifest["citations"] = [{"message_id": str(c.message_id), "filename": d.filename, "page": ch.page_number,
                               "text": ch.content, "rank": c.rank} for c, ch, d in sources]
    handle = tempfile.NamedTemporaryFile(prefix="knowbase-", suffix=".zip", delete=False)
    path = Path(handle.name)
    handle.close()
    def write():
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("knowbase.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for d in docs:
                if d.file_type != "url":
                    original = resolve_storage_path(d.file_path)
                    if original.is_file():
                        archive.write(original, f"documents/{d.id}.{d.file_type}")
            for s in manifest["sessions"]:
                text = "# " + s["title"] + "\n\n" + "\n\n".join(
                    ("## 你" if m["role"] == "user" else "## 知库") + "\n\n" + m["content"] for m in s["messages"])
                archive.writestr(f"chats/{s['id']}.md", text)
            archive.writestr("README.txt", "知库个人备份：原文件、知识库、聊天 JSON 和 Markdown。\n不包含密码、API Key 或模型配置。恢复后文档会重新解析，请先配置模型。")
    try:
        await asyncio.to_thread(write)
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


class ArchiveKB(BaseModel):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=10000)


class ArchiveDoc(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    file_type: str
    source_url: str | None = Field(None, max_length=1000)
    archive_path: str | None = None


class ArchiveMessage(BaseModel):
    role: str
    content: str = Field(max_length=2_000_000)
    status: str = "completed"
    reasoning_content: str = Field("", max_length=200_000)
    answer_mode: str | None = None


class ArchiveSession(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID | None = None
    title: str = Field(max_length=200)
    messages: list[ArchiveMessage] = Field(max_length=10000)


class Archive(BaseModel):
    format: str
    knowledge_bases: list[ArchiveKB] = Field(max_length=1000)
    documents: list[ArchiveDoc] = Field(max_length=5000)
    sessions: list[ArchiveSession] = Field(max_length=5000)


async def import_archive(db, user, file):
    from app.services.document_service import _enqueue_or_fail, _validate_url
    limit = 200 * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise BusinessError("archive_too_large", "备份包不能超过 200MB")
    import io
    paths = []
    pending = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 15000 or sum(i.file_size for i in archive.infolist()) > limit:
                raise ValueError("备份解压后的总大小不能超过 200MB")
            data = Archive.model_validate_json(archive.read("knowbase.json"))
            if data.format != "knowbase-personal-v1":
                raise ValueError("不是有效的知库个人备份")
            if len({d.id for d in data.documents}) != len(data.documents) or sum(len(s.messages) for s in data.sessions) > 100000:
                raise ValueError("备份包含重复文档或过多消息")
            kb_map = {k.id: uuid.uuid4() for k in data.knowledge_bases}
            if len(kb_map) != len(data.knowledge_bases):
                raise ValueError("备份中有重复知识库")
            # Validate all files before adding any database rows.
            contents = {}
            for d in data.documents:
                if d.kb_id not in kb_map:
                    raise ValueError("备份文档的知识库不存在")
                if d.file_type == "url":
                    _validate_url(d.source_url or "")
                else:
                    expected = f"documents/{d.id}.{d.file_type}"
                    if d.archive_path != expected:
                        raise ValueError("备份文件路径无效")
                    content = archive.read(expected)
                    kind, checksum = validate_upload(d.filename, content, 50)
                    if kind != d.file_type:
                        raise ValueError("备份文件类型不一致")
                    contents[d.id] = (content, checksum)
            if data.documents:
                from app.services.model_config_service import require_personal_config
                await require_personal_config(db, user.id)
            for k in data.knowledge_bases:
                db.add(KnowledgeBase(id=kb_map[k.id], name=k.name, description=k.description, created_by=user.id))
            await db.flush()
            for d in data.documents:
                if d.file_type == "url":
                    rel, checksum, size = d.source_url, None, None
                else:
                    content, checksum = contents[d.id]
                    rel, size = save_upload(content, d.file_type), len(content)
                    paths.append(resolve_storage_path(rel))
                doc = Document(kb_id=kb_map[d.kb_id], filename=d.filename, file_type=d.file_type,
                               source_url=d.source_url, file_path=rel, checksum=checksum, file_size=size,
                               uploaded_by=user.id, parse_status="pending")
                db.add(doc)
                pending.append(doc)
            from datetime import timedelta
            from app.db.base import utcnow
            for s in data.sessions:
                session = ChatSession(user_id=user.id, title=s.title, kb_id=kb_map.get(s.kb_id))
                db.add(session)
                await db.flush()
                start = utcnow()
                for idx, m in enumerate(s.messages):
                    if m.role not in ("user", "assistant"):
                        raise ValueError("备份消息角色无效")
                    db.add(Message(session_id=session.id, role=m.role, content=m.content,
                                   status="completed" if m.status == "completed" else "stopped",
                                   token_usage={"reasoning_content": m.reasoning_content,
                                                "answer_mode": m.answer_mode if m.answer_mode in ("general", "knowledge") else None},
                                   created_at=start + timedelta(microseconds=idx)))
            await db.commit()
    except (ValueError, KeyError, zipfile.BadZipFile, ValidationError) as exc:
        await db.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        raise BusinessError("invalid_archive", "备份包无效、文件缺失或超过限制，请使用完整的知库备份包", 400) from exc
    except Exception:
        await db.rollback()
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    failed = 0
    for doc in pending:
        try:
            await _enqueue_or_fail(db, doc)
        except BusinessError:
            failed += 1
    return {"knowledge_bases": len(data.knowledge_bases), "documents": len(pending), "sessions": len(data.sessions), "queue_failed": failed}


async def clear_personal_data(db, user):
    from app.services.kb_service import delete_kb
    kbs = (await db.execute(select(KnowledgeBase).where(KnowledgeBase.created_by == user.id))).scalars().all()
    busy = await db.scalar(select(Document.id).where(Document.kb_id.in_([k.id for k in kbs]), Document.parse_status == "parsing", Document.deleted_at.is_(None)).limit(1))
    generating = await db.scalar(select(Message.id).join(ChatSession).where(ChatSession.user_id == user.id, Message.status == "generating").limit(1))
    if busy or generating:
        raise BusinessError("data_busy", "还有文档正在解析或回答正在生成，请完成或停止后再删除", 409)
    # Clear caches first; if Redis is unavailable, don't claim a complete deletion.
    try:
        redis = get_redis()
        for prefix in (f"chatcache:{user.id}:*", f"embed:{user.id}:*"):
            async for key in redis.scan_iter(match=prefix, count=100):
                await redis.delete(key)
    except Exception as exc:
        raise BusinessError("cache_unavailable", "缓存服务不可用，暂未删除数据，请稍后重试", 503) from exc
    for kb in kbs:
        await delete_kb(db, kb.id)
    await db.execute(delete(ChatSession).where(ChatSession.user_id == user.id))
    await db.execute(delete(UserModelConfig).where(UserModelConfig.user_id == user.id))
    await db.commit()

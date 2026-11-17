"""知识库服务：CRUD + Chroma collection 生命周期 + 管理端统计。"""
import logging
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError
from app.models import ChatSession, Chunk, Document, KnowledgeBase
from app.services.rag import vector_store

logger = logging.getLogger(__name__)


async def create_kb(
    db: AsyncSession, name: str, description: str | None, created_by: uuid.UUID
) -> KnowledgeBase:
    kb = KnowledgeBase(name=name, description=description, created_by=created_by)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    # 向量集合在首次解析时，使用该账号的 Embedding 配置创建。
    return kb


async def update_kb(
    db: AsyncSession, kb_id: uuid.UUID, name: str | None, description: str | None, is_active: bool | None
) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise BusinessError("kb_not_found", "知识库不存在", 404)
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    if is_active is not None:
        kb.is_active = is_active
    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_kb(db: AsyncSession, kb_id: uuid.UUID) -> None:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise BusinessError("kb_not_found", "知识库不存在", 404)
    # 绑定该 KB 的会话解除绑定（外键 ondelete SET NULL 兜底，显式更新避免依赖）
    from app.services.document_service import delete_document
    docs = (await db.execute(select(Document).where(Document.kb_id == kb_id, Document.deleted_at.is_(None)))).scalars().all()
    if any(doc.parse_status == "parsing" for doc in docs):
        raise BusinessError("document_busy", "知识库中有文档正在解析，请等待完成后删除", 409)
    for doc in docs:
        await delete_document(db, doc.id)
    # Also clean originals that were soft-deleted by older releases.
    from app.utils.file_utils import resolve_storage_path
    all_docs = (await db.execute(select(Document).where(Document.kb_id == kb_id))).scalars().all()
    for doc in all_docs:
        if doc.file_type != "url":
            resolve_storage_path(doc.file_path).unlink(missing_ok=True)
    try:
        vector_store.delete_collection(kb_id, strict=True)
    except Exception as exc:
        raise BusinessError("index_unavailable", "索引清理未完成，请稍后重试删除知识库", 503) from exc
    await db.execute(
        update(ChatSession).where(ChatSession.kb_id == kb_id).values(kb_id=None)
    )
    await db.delete(kb)  # documents/chunks 由 FK ondelete CASCADE 清理
    await db.commit()
    logger.info("Knowledge base %s deleted", kb_id)


async def list_active_kbs(db: AsyncSession, user_id=None) -> list[KnowledgeBase]:
    from sqlalchemy import select

    rows = await db.execute(select(KnowledgeBase).where(KnowledgeBase.is_active.is_(True), KnowledgeBase.created_by == user_id))
    return list(rows.scalars().all())


async def list_kbs_admin(db: AsyncSession, user_id=None) -> list[dict]:
    """管理端列表：附带文档/分块数量与解析状态统计。"""
    from sqlalchemy import select

    kbs = list((await db.execute(select(KnowledgeBase).where(KnowledgeBase.created_by == user_id))).scalars().all())
    kb_ids = [k.id for k in kbs]

    doc_stats: dict[uuid.UUID, dict] = {}
    chunk_stats: dict[uuid.UUID, int] = {}
    if kb_ids:
        rows = await db.execute(
            select(Document.kb_id, Document.parse_status, func.count().label("cnt"))
            .where(Document.kb_id.in_(kb_ids), Document.deleted_at.is_(None))
            .group_by(Document.kb_id, Document.parse_status)
        )
        for kb_id, status, cnt in rows.all():
            doc_stats.setdefault(kb_id, {})[status] = cnt
        rows = await db.execute(
            select(Chunk.kb_id, func.count().label("cnt"))
            .where(Chunk.kb_id.in_(kb_ids))
            .group_by(Chunk.kb_id)
        )
        chunk_stats = {kb_id: cnt for kb_id, cnt in rows.all()}

    return [
        {
            "id": k.id,
            "name": k.name,
            "description": k.description,
            "is_active": k.is_active,
            "created_at": k.created_at,
            "document_count": sum(doc_stats.get(k.id, {}).values()),
            "chunk_count": chunk_stats.get(k.id, 0),
            "parse_stats": doc_stats.get(k.id, {}),
        }
        for k in kbs
    ]

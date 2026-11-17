"""个人空间授权。所有账号仅能操作自己的资料。"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import select

from app.core.exceptions import BusinessError
from app.models import Document, KnowledgeBase

_scope = ContextVar("personal_retrieval_scope", default=("", ()))


async def owned_kb(db, kb_id, user_id):
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or kb.created_by != user_id:
        raise BusinessError("kb_not_found", "知识库不存在", 404)
    return kb


async def owned_document(db, doc_id, user_id):
    doc = await db.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise BusinessError("document_not_found", "文档不存在", 404)
    await owned_kb(db, doc.kb_id, user_id)
    return doc


async def active_kb_ids(db, user_id, kb_id=None):
    stmt = select(KnowledgeBase.id).where(
        KnowledgeBase.created_by == user_id, KnowledgeBase.is_active.is_(True)
    )
    if kb_id is not None:
        stmt = stmt.where(KnowledgeBase.id == kb_id)
    ids = tuple((await db.execute(stmt)).scalars())
    if kb_id is not None and not ids:
        raise BusinessError("kb_not_found", "知识库不存在或已停用", 404)
    return ids


@contextmanager
def retrieval_scope(user_id, kb_ids):
    token = _scope.set((str(user_id), tuple(kb_ids)))
    try:
        yield
    finally:
        _scope.reset(token)


def current_scope():
    return _scope.get()

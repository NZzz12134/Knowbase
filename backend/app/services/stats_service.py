"""个人统计：所有计数和趋势始终限定当前账号的有效资料与会话。"""
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import (
    ChatSession,
    Chunk,
    Document,
    Feedback,
    KnowledgeBase,
    Message,
)


def _scope(user_id):
    kbs = select(KnowledgeBase.id).where(KnowledgeBase.created_by == user_id)
    docs = select(Document.id).where(Document.kb_id.in_(kbs), Document.deleted_at.is_(None))
    sessions = select(ChatSession.id).where(ChatSession.user_id == user_id, ChatSession.is_deleted.is_(False))
    messages = select(Message.id).where(Message.session_id.in_(sessions))
    return kbs, docs, sessions, messages


async def overview(db: AsyncSession, user_id) -> dict:
    async def count(model, *conds) -> int:
        stmt = select(func.count()).select_from(model)
        for c in conds:
            stmt = stmt.where(c)
        return (await db.execute(stmt)).scalar_one()

    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    kbs, docs, sessions, messages = _scope(user_id)
    session_count = await count(ChatSession, ChatSession.id.in_(sessions))
    message_count = await count(Message, Message.id.in_(messages))
    assistant_count = await count(Message, Message.id.in_(messages), Message.role == "assistant")
    document_count = await count(Document, Document.id.in_(docs))
    chunk_count = await count(Chunk, Chunk.document_id.in_(docs))
    kb_count = await count(KnowledgeBase, KnowledgeBase.id.in_(kbs))
    today_qa = await count(Message, Message.id.in_(messages), Message.role == "user", Message.created_at >= today_start)

    doc_status = (
        await db.execute(
            select(Document.parse_status, func.count())
            .where(Document.id.in_(docs))
            .group_by(Document.parse_status)
        )
    ).all()
    doc_status_map = dict(doc_status)
    succeeded = doc_status_map.get("succeeded", 0)
    failed = doc_status_map.get("failed", 0)
    parse_success_rate = round(succeeded / (succeeded + failed) * 100, 1) if (succeeded + failed) else 100.0

    like_count = await count(Feedback, Feedback.message_id.in_(messages), Feedback.user_id == user_id, Feedback.rating == "like")
    dislike_count = await count(Feedback, Feedback.message_id.in_(messages), Feedback.user_id == user_id, Feedback.rating == "dislike")

    return {
        "session_count": session_count,
        "message_count": message_count,
        "assistant_answer_count": assistant_count,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "kb_count": kb_count,
        "today_qa": today_qa,
        "parse_success_rate": parse_success_rate,
        "feedback_like": like_count,
        "feedback_dislike": dislike_count,
    }


async def daily_qa(db: AsyncSession, user_id, days: int = 30) -> list[dict]:
    start = utcnow().date() - timedelta(days=days - 1)
    _, _, _, messages = _scope(user_id)

    rows = await db.execute(
        select(
            func.date(Message.created_at).label("day"),
            func.sum(func.if_(Message.role == "user", 1, 0)).label("questions"),
            func.sum(func.if_(Message.role == "assistant", 1, 0)).label("answers"),
        )
        .where(Message.created_at >= start, Message.id.in_(messages))
        .group_by("day")
        .order_by("day")
    )

    data = {str(r[0]): {"questions": int(r[1] or 0), "answers": int(r[2] or 0)} for r in rows.all()}

    fb_rows = await db.execute(
        select(
            func.date(Feedback.created_at).label("day"),
            func.sum(func.if_(Feedback.rating == "like", 1, 0)).label("likes"),
            func.sum(func.if_(Feedback.rating == "dislike", 1, 0)).label("dislikes"),
        )
        .where(Feedback.created_at >= start, Feedback.message_id.in_(messages), Feedback.user_id == user_id)
        .group_by("day")
    )
    fb_data = {str(r[0]): {"likes": int(r[1] or 0), "dislikes": int(r[2] or 0)} for r in fb_rows.all()}

    result = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        result.append(
            {
                "day": day,
                "questions": data.get(day, {}).get("questions", 0),
                "answers": data.get(day, {}).get("answers", 0),
                "likes": fb_data.get(day, {}).get("likes", 0),
                "dislikes": fb_data.get(day, {}).get("dislikes", 0),
            }
        )
    return result


async def document_stats(db: AsyncSession, user_id) -> list[dict]:
    rows = await db.execute(
        select(
            KnowledgeBase.id,
            KnowledgeBase.name,
            Document.parse_status,
            func.count().label("cnt"),
        )
        .join(Document, Document.kb_id == KnowledgeBase.id)
        .where(Document.deleted_at.is_(None), KnowledgeBase.created_by == user_id)
        .group_by(KnowledgeBase.id, KnowledgeBase.name, Document.parse_status)
    )
    per_kb: dict[uuid.UUID, dict] = {}
    for kb_id, kb_name, status, cnt in rows.all():
        entry = per_kb.setdefault(kb_id, {"kb_id": str(kb_id), "kb_name": kb_name, "statuses": {}})
        entry["statuses"][status] = cnt
    return list(per_kb.values())

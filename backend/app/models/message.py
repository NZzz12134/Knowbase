import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPkMixin, utcnow


class Message(Base, UUIDPkMixin):
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_session_created", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    # generating(流式中) | completed | failed | stopped(客户端断开)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="completed", server_default="completed"
    )
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 服务层保证同会话时间递增；旧的相同时间记录由统一排序规则兜底。
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, default=utcnow)

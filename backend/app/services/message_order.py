"""统一消息顺序：时间相同时，历史提问排在回复之前，UUID 仅用于稳定分页。"""
from sqlalchemy import case

from app.models import Message


def message_order(*, descending=False):
    role_order = case((Message.role == "user", 0), else_=1)
    columns = (Message.created_at, role_order, Message.id)
    return tuple(column.desc() if descending else column.asc() for column in columns)

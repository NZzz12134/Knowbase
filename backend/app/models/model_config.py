from sqlalchemy import Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ModelConfig(Base, TimestampMixin):
    """唯一一行全局模型配置；密钥在 JSON 中以 Fernet 密文保存。"""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)

"""建表与旧版本数据迁移。新安装通过注册创建账号，无预置特权账号。"""
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import engine
from app.models import ModelConfig, User, UserModelConfig

logger = logging.getLogger(__name__)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123456"


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 可配置的大输出可能超过 MySQL TEXT 的 64KB，升级时只扩容，不改动正文。
        if conn.dialect.name == "mysql":
            kind = await conn.exec_driver_sql(
                "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'messages' AND COLUMN_NAME = 'content'"
            )
            if kind.scalar_one_or_none() in ("text", "tinytext"):
                await conn.exec_driver_sql("ALTER TABLE messages MODIFY COLUMN content MEDIUMTEXT NOT NULL")
                logger.info("Expanded messages.content to MEDIUMTEXT for long answers")


async def seed_admin(db: AsyncSession) -> None:
    """测试/旧脚本兼容账号，无特殊权限；生产初始化不调用。"""
    result = await db.execute(select(User).where(User.username == ADMIN_USERNAME))
    if result.scalar_one_or_none() is not None:
        return
    db.add(
        User(
            username=ADMIN_USERNAME,
            hashed_password=hash_password(ADMIN_PASSWORD),
        )
    )
    await db.commit()
    logger.info("Created compatibility account")


async def migrate_legacy_roles(db: AsyncSession) -> None:
    """Copy existing encrypted model settings to former owners before retiring role flags."""
    legacy = await db.get(ModelConfig, 1)
    owners = (await db.execute(select(User).where(User.role == "admin"))).scalars().all()
    for user in owners:
        if legacy is not None and await db.get(UserModelConfig, user.id) is None:
            db.add(UserModelConfig(user_id=user.id, revision=legacy.revision, config=legacy.config))
    await db.execute(update(User).where(User.role != "user").values(role="user"))
    await db.commit()


async def init_db(db: AsyncSession) -> None:
    await create_tables()
    await migrate_legacy_roles(db)

"""个人使用统计接口（登录后仅查看本人数据）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.models import User
from app.services import stats_service

router = APIRouter(tags=["personal-stats"])


@router.get("/overview")
async def overview(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await stats_service.overview(db, admin.id)


@router.get("/daily-qa")
async def daily_qa(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await stats_service.daily_qa(db, admin.id)


@router.get("/documents")
async def document_stats(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await stats_service.document_stats(db, admin.id)

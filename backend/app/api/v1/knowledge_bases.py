"""个人知识库 CRUD 及旧路径别名；所有资料按创建者隔离。"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.kb_schema import KBCreate, KBOut, KBUpdate
from app.services import kb_service
from app.services.personal_access import owned_kb

router = APIRouter(tags=["knowledge-bases"])


@router.get("/kbs", response_model=list[KBOut])
async def list_kbs(
    include_inactive: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用户侧：活跃知识库列表（会话绑定用）。"""
    if include_inactive:
        return await kb_service.list_kbs_admin(db, user.id)
    kbs = await kb_service.list_active_kbs(db, user.id)
    return [
        KBOut(
            id=k.id, name=k.name, description=k.description,
            is_active=k.is_active, created_at=k.created_at,
        )
        for k in kbs
    ]


admin_router = APIRouter(prefix="/admin/kbs", tags=["admin-kbs"])


@admin_router.get("", response_model=list[KBOut])
async def admin_list_kbs(
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await kb_service.list_kbs_admin(db, admin.id)


@admin_router.post("", response_model=KBOut, status_code=201)
async def admin_create_kb(
    data: KBCreate,
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kb = await kb_service.create_kb(db, data.name, data.description, admin.id)
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        is_active=kb.is_active, created_at=kb.created_at,
    )


@admin_router.patch("/{kb_id}", response_model=KBOut)
async def admin_update_kb(
    kb_id: uuid.UUID,
    data: KBUpdate,
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await owned_kb(db, kb_id, admin.id)
    kb = await kb_service.update_kb(db, kb_id, data.name, data.description, data.is_active)
    return KBOut(
        id=kb.id, name=kb.name, description=kb.description,
        is_active=kb.is_active, created_at=kb.created_at,
    )


@admin_router.delete("/{kb_id}", status_code=204)
async def admin_delete_kb(
    kb_id: uuid.UUID,
    admin: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await owned_kb(db, kb_id, admin.id)
    await kb_service.delete_kb(db, kb_id)


# Both personal and legacy admin entry points enforce ownership.
@router.post("/kbs", response_model=KBOut, status_code=201)
async def create_personal_kb(data: KBCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await kb_service.create_kb(db, data.name, data.description, user.id)


@router.patch("/kbs/{kb_id}", response_model=KBOut)
async def update_personal_kb(kb_id: uuid.UUID, data: KBUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_kb(db, kb_id, user.id)
    return await kb_service.update_kb(db, kb_id, data.name, data.description, data.is_active)


@router.delete("/kbs/{kb_id}", status_code=204)
async def delete_personal_kb(kb_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_kb(db, kb_id, user.id)
    await kb_service.delete_kb(db, kb_id)

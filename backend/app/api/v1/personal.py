"""个人模型、引导、原文访问与数据管理。所有资源按登录用户授权。"""
import asyncio
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.v1.model_config import _probe, _test_error
from app.core.deps import get_current_user, get_db
from app.core.exceptions import BusinessError
from app.core.security import verify_password
from app.models import Document, KnowledgeBase, User, UserModelConfig
from app.schemas.model_config_schema import ModelConfigIn, ModelTestIn
from app.services import model_config_service as models
from app.services.personal_access import owned_document
from app.utils.file_utils import resolve_storage_path

router = APIRouter(tags=["personal"])


@router.get("/me/model-config")
async def get_models(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    config = await models.read_config(db, user.id)
    return {**models.public_config(config), "personal": config["revision"] > 0}


@router.put("/me/model-config")
async def save_models(data: ModelConfigIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {**await models.save_config(db, data, user.id), "personal": True}


@router.delete("/me/model-config", status_code=204)
async def reset_models(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(UserModelConfig, user.id)
    if row:
        await db.delete(row)
        await db.commit()


@router.post("/me/model-config/test")
async def test_models(data: ModelTestIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    config = await models.read_config(db, user.id)
    config[data.role] = models.resolve_endpoint(data.endpoint, config[data.role])
    config["rerank_enabled"] = True
    if config[data.role]["mode"] == "api" and not config[data.role]["api_key"]:
        return {"success": False, "message": "请填写你自己的 API Key。"}
    try:
        async with asyncio.timeout(180):
            return await _probe(data.role, config)
    except Exception as exc:
        return {"success": False, "message": _test_error(exc)}


@router.get("/me/onboarding")
async def onboarding(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    kbs = list((await db.execute(select(KnowledgeBase.id).where(KnowledgeBase.created_by == user.id))).scalars())
    rows = (await db.execute(select(Document.parse_status, func.count()).where(
        Document.kb_id.in_(kbs), Document.deleted_at.is_(None)).group_by(Document.parse_status))).all()
    counts = dict(rows)
    return {"knowledge_bases": len(kbs), "documents": sum(counts.values()),
            "ready": counts.get("succeeded", 0), "processing": counts.get("pending", 0) + counts.get("parsing", 0),
            "failed": counts.get("failed", 0), "personal_models": await db.get(UserModelConfig, user.id) is not None}


@router.get("/documents/{doc_id}/file")
async def original_file(doc_id: uuid.UUID, inline: bool = False, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    doc = await owned_document(db, doc_id, user.id)
    if doc.file_type == "url":
        raise BusinessError("no_original_file", "网页资料没有上传原文件，请使用原文预览", 404)
    path = resolve_storage_path(doc.file_path)
    if not path.is_file():
        raise BusinessError("file_not_found", "原文件已不存在，请重新上传", 404)
    return FileResponse(path, filename=doc.filename, media_type="application/pdf" if doc.file_type == "pdf" else "application/octet-stream",
                        content_disposition_type="inline" if inline and doc.file_type == "pdf" else "attachment",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/documents/{doc_id}/preview")
async def preview(doc_id: uuid.UUID, page: int = Query(1, ge=1), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    doc = await owned_document(db, doc_id, user.id)
    from app.models import Chunk
    # URL previews use the stored snapshot; never refetch untrusted URLs when viewing.
    if doc.file_type == "url":
        text = "\n\n".join((await db.execute(select(Chunk.content).where(Chunk.document_id == doc.id).order_by(Chunk.seq))).scalars())
    else:
        from app.services.parsing.loaders import load_document
        path = resolve_storage_path(doc.file_path)
        if not path.is_file():
            raise BusinessError("file_not_found", "原文件已不存在", 404)
        try:
            docs = await asyncio.to_thread(load_document, doc.file_type, str(path))
            text = "\n\n".join(d.page_content for d in docs)
        except Exception:
            raise BusinessError("preview_failed", "原文暂时无法预览，请下载原文件查看", 422)
    size = 20000
    return {"document_id": str(doc.id), "filename": doc.filename, "file_type": doc.file_type,
            "source_url": doc.source_url, "page": page, "pages": max(1, (len(text) + size - 1) // size),
            "text": text[(page - 1) * size:page * size]}


@router.get("/me/export")
async def export_data(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.personal_data import export_archive
    path = await export_archive(db, user)
    return FileResponse(path, filename="knowbase-backup.zip", media_type="application/zip",
                        headers={"Cache-Control": "no-store"}, background=BackgroundTask(path.unlink, missing_ok=True))


@router.post("/me/import")
async def import_data(file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.personal_data import import_archive
    return await import_archive(db, user, file)


class DeleteDataIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirmation: str


@router.post("/me/delete-data", status_code=204)
async def delete_data(data: DeleteDataIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.confirmation != "删除我的全部数据" or not verify_password(data.password, user.hashed_password):
        raise BusinessError("confirmation_failed", "请输入正确的当前密码和确认文字", 400)
    from app.services.personal_data import clear_personal_data
    await clear_personal_data(db, user)

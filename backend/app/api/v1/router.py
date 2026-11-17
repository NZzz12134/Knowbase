from fastapi import APIRouter
from app.api.v1 import personal

from app.api.v1 import (
    admin_stats,
    auth,
    chat,
    citations,
    documents,
    feedback,
    knowledge_bases,
    sessions,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(personal.router)
api_router.include_router(sessions.router)
api_router.include_router(chat.router)
api_router.include_router(citations.router)
api_router.include_router(feedback.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(knowledge_bases.admin_router, include_in_schema=False)
api_router.include_router(documents.router, prefix="/documents")
api_router.include_router(documents.router, prefix="/admin/documents", include_in_schema=False)
api_router.include_router(admin_stats.router, prefix="/me/stats")
api_router.include_router(admin_stats.router, prefix="/admin/stats", include_in_schema=False)
# Old URLs are personal aliases; they cannot access or mutate installation-wide settings.
api_router.add_api_route("/admin/model-config", personal.get_models, methods=["GET"], include_in_schema=False)
api_router.add_api_route("/admin/model-config", personal.save_models, methods=["PUT"], include_in_schema=False)
api_router.add_api_route("/admin/model-config/test", personal.test_models, methods=["POST"], include_in_schema=False)

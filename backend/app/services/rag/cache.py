"""聊天答案缓存：相同问题（+KB+prompt版本+模型）1 小时内复用，伪流式回放。"""
import hashlib
import json
import logging

from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.services.model_config_service import get_model_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v4-reasoning"


def _cache_key(question: str, kb_id: str, model: str) -> str:
    s = get_model_settings()
    from app.services.personal_access import current_scope
    scope = current_scope()
    raw = f"{scope}|{question}|{kb_id}|{PROMPT_VERSION}|{model}|{s.LLM_MODE}|{s.LLM_BASE_URL}|{s.MODEL_CONFIG_REVISION}|{s.LLM_MAX_TOKENS}|{s.SHOW_REASONING}"
    return f"chatcache:{scope[0] or 'system'}:{hashlib.md5(raw.encode('utf-8')).hexdigest()}"


async def get_cached_answer(question: str, kb_id: str | None, model: str) -> dict | None:
    key = _cache_key(question, kb_id or "all", model)
    try:
        data = await get_redis().get(key)
        return json.loads(data) if data else None
    except Exception:
        return None


async def set_cached_answer(
    question: str, kb_id: str | None, model: str, answer: str, citations: list[dict], reasoning_content: str = ""
) -> None:
    key = _cache_key(question, kb_id or "all", model)
    try:
        await get_redis().set(
            key,
            json.dumps({"answer": answer, "citations": citations, "reasoning_content": reasoning_content}, ensure_ascii=False),
            ex=get_settings().CHAT_CACHE_TTL,
        )
    except Exception as exc:
        logger.warning("chat cache write skipped: %s", exc)

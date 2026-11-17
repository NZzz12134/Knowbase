"""Rerank Provider。

- RERANK_PROVIDER=dashscope：DashScope 原生端点（兼容模式不支持 /rerank）
  POST {base}/api/v1/services/rerank/text-rerank/text-rerank
- 其他（如 siliconflow）：OpenAI 兼容端点 POST {base}/rerank
"""
import logging
from functools import lru_cache

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.services.model_config_service import get_model_settings
from app.services.providers.ollama import ollama_rerank

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30)


def _retryable(exc: BaseException) -> bool:
    """4xx 客户端错误（权限/格式）重试无意义，仅网络错误与 5xx 重试。"""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


@retry(
    wait=wait_exponential(multiplier=1, max=30),
    stop=stop_after_attempt(2),
    retry=retry_if_exception(_retryable),
    reraise=True,
)
async def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[tuple[int, float]]:
    """返回 [(原文档索引, 相关度分数)]，按分数降序。"""
    s = get_model_settings()
    if not s.RERANK_ENABLED:
        raise RuntimeError("rerank disabled")
    if not s.RERANK_MODEL or not s.RERANK_BASE_URL or (s.RERANK_MODE == "api" and not s.RERANK_API_KEY):
        from app.core.exceptions import BusinessError
        raise BusinessError("model_config_required", "请先配置自己的 Rerank 模型，或关闭重排", 428)
    top_n = top_n or min(len(documents), s.RERANK_TOP_N)
    if not documents:
        return []
    if s.RERANK_MODE == "ollama":
        async with httpx.AsyncClient(timeout=120) as client:
            return await ollama_rerank(client, s.RERANK_BASE_URL, s.RERANK_MODEL, s.RERANK_API_KEY, query, documents, top_n)
    headers = {"Authorization": f"Bearer {s.RERANK_API_KEY}"}

    if s.RERANK_PROVIDER == "dashscope":
        payload = {
            "model": s.RERANK_MODEL,
            "input": {"query": query, "documents": documents},
            "parameters": {"top_n": top_n, "return_documents": False},
        }
        from urllib.parse import urlsplit
        p = urlsplit(s.RERANK_BASE_URL)
        url = f"{p.scheme}://{p.netloc}/api/v1/services/rerank/text-rerank/text-rerank"
        resp = await _client().post(url, json=payload, headers=headers)
        resp.raise_for_status()
        results = resp.json().get("output", {}).get("results", [])
    else:
        payload = {
            "model": s.RERANK_MODEL,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        url = f"{s.RERANK_BASE_URL.rstrip('/')}/rerank"
        resp = await _client().post(url, json=payload, headers=headers)
        resp.raise_for_status()
        results = resp.json().get("results", [])

    import math
    ranked = [(r["index"], float(r["relevance_score"])) for r in results]
    if not ranked or any(type(i) is not int or not 0 <= i < len(documents) or not math.isfinite(score) for i, score in ranked) or len({i for i, _ in ranked}) != len(ranked):
        raise ValueError("Rerank 服务返回了无效的索引或评分")
    return sorted(ranked, key=lambda item: -item[1])[:top_n]

"""问答编排：改写 → 检索与相关性判断 → 知识库回答或普通对话流。

返回 async generator：yield ("citations"|"token"|"usage", payload)
"""
import logging
import hashlib
import json
import uuid
from typing import AsyncGenerator

from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage, HumanMessage

from app.services.providers.embeddings import embed_with_cache
from app.services.providers.llm import get_llm
from app.services.rag import cache
from app.services.rag.condense import condense_question
from app.services.rag.prompts import GENERAL_PROMPT, QA_PROMPT
from app.services.rag.relevance import select_relevant_chunks
from app.services.personal_access import current_scope
from app.services.rag.retrievers import RetrievedChunk, hybrid_retrieve
from app.services.model_config_service import get_model_settings

logger = logging.getLogger(__name__)


def _format_context(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    """构造 prompt 上下文与 citations 载荷。引用编号 [1..n] 与 citations 顺序一致。"""
    parts = []
    citations = []
    for i, c in enumerate(chunks, start=1):
        src = c.metadata.get("filename") or c.metadata.get("source") or "未知来源"
        location = ""
        if c.metadata.get("page"):
            location += f"，第 {c.metadata['page']} 页"
        if c.metadata.get("row_start"):
            location += f"，第 {c.metadata['row_start']}-{c.metadata.get('row_end') or c.metadata['row_start']} 行"
        parts.append(f"[{i}] {c.text}\n（来源: {src}{location}）")
        citations.append(
            {
                "id": c.id,
                "document_id": c.metadata.get("document_id"),
                "text": c.text,
                "filename": c.metadata.get("filename"),
                "source": c.metadata.get("source") if str(c.metadata.get("source", "")).startswith(("https://", "http://")) else None,
                "page": c.metadata.get("page"),
                "row_start": c.metadata.get("row_start"),
                "row_end": c.metadata.get("row_end"),
                "heading_path": c.metadata.get("heading_path"),
                "score": round(c.score, 4),
            }
        )
    return "\n\n".join(parts), citations


async def run_qa_stream(
    session_kb_id: uuid.UUID | None,
    question: str,
    history: list[dict],
    refresh: bool = False,
) -> AsyncGenerator[tuple[str, dict], None]:
    """完整问答流。事件类型：citations / token / usage。"""
    # 1. 问题改写（带历史时）
    standalone = await condense_question(history, question)

    # 没有可访问的启用知识库时直接对话，无需请求 Embedding 服务。
    chunks = []
    if current_scope()[1]:
        try:
            query_embedding = (await embed_with_cache([standalone]))[0]
        except Exception as exc:
            logger.exception("embedding failed for question: %s", exc)
            from app.core.exceptions import BusinessError
            raise BusinessError("retrieval_unavailable", "检索服务暂时不可用，请检查我的模型中的 Embedding 连接后重试", 503) from exc
        candidates = await hybrid_retrieve(standalone, session_kb_id, query_embedding)
        chunks = await select_relevant_chunks(standalone, candidates)

    context, citations = _format_context(chunks)
    answer_mode = "knowledge" if chunks else "general"
    # 回答同时依赖原问题、历史、模式和经过授权的当前资料，不能只按改写问题复用。
    recent_history = history[-6:]
    cache_scope = hashlib.sha256(json.dumps(
        [str(session_kb_id), answer_mode, context, question, recent_history], ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()

    # 3. 答案缓存
    model = get_model_settings().LLM_MODEL
    cached = None if refresh else await cache.get_cached_answer(standalone, cache_scope, model)
    yield "citations", {"citations": citations, "answer_mode": answer_mode,
                         "mode": _retrieval_mode_desc() if chunks else "general"}
    if cached:
        answer = cached["answer"]
        # Cached answers use the freshly authorized sources emitted above.
        # 伪流式回放：按 24 字符分片
        for i in range(0, len(answer), 24):
            yield "token", {"content": answer[i : i + 24]}
        yield "usage", {"cached": True}
        return

    # 4. LLM 流式生成
    chain = (QA_PROMPT if chunks else GENERAL_PROMPT) | get_llm() | StrOutputParser()
    messages = [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
                for m in recent_history]
    full = []
    try:
        async for piece in chain.astream(
            {"context": context, "question": question, "history": messages}
        ):
            full.append(piece)
            yield "token", {"content": piece}
    except Exception:
        logger.exception("LLM stream failed")
        raise

    answer = "".join(full)
    if answer.strip():
        await cache.set_cached_answer(
            standalone, cache_scope, model,
            answer, citations,
        )
    yield "usage", {"cached": False, "model": model}


def _retrieval_mode_desc() -> str:
    settings = get_model_settings()
    parts = [settings.RETRIEVAL_MODE]
    if settings.RERANK_ENABLED:
        parts.append("rerank")
    return "+".join(parts)

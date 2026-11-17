"""候选资料相关性判断。融合分数只用于排序，不能直接作为相关性概率。"""
import json
import logging

from langchain_core.output_parsers import JsonOutputParser

from app.core.exceptions import BusinessError
from app.services.providers.llm import get_llm
from app.services.rag.prompts import RELEVANCE_PROMPT

logger = logging.getLogger(__name__)


async def select_relevant_chunks(question, chunks):
    if not chunks:
        return []
    payload = json.dumps({"question": question, "candidates": [
        {"id": i, "text": chunk.text} for i, chunk in enumerate(chunks, 1)
    ]}, ensure_ascii=False)
    try:
        result = await (RELEVANCE_PROMPT | get_llm().bind(temperature=0) | JsonOutputParser()).ainvoke({"input": payload})
        ids = result.get("relevant_ids") if isinstance(result, dict) else None
        if (not isinstance(ids, list) or any(type(i) is not int or not 1 <= i <= len(chunks) for i in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("Invalid relevance result")
        chosen = set(ids)
        return [chunk for i, chunk in enumerate(chunks, 1) if i in chosen]
    except Exception as exc:
        logger.warning("Knowledge relevance check failed: %s", type(exc).__name__)
        raise BusinessError("relevance_unavailable", "暂时无法判断资料相关性，请稍后重试或检查对话模型连接", 503) from exc

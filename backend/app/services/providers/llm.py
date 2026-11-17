"""对话模型：动态配置的 OpenAI 兼容 API 或 Ollama /v1 接口。"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.services.model_config_service import get_model_settings

def get_llm() -> ChatOpenAI:
    s = get_model_settings()
    if not s.LLM_MODEL or not s.LLM_BASE_URL or (s.LLM_MODE == "api" and not s.LLM_API_KEY):
        from app.core.exceptions import BusinessError
        raise BusinessError("model_config_required", "请先配置自己的对话模型", 428)
    base_url = s.LLM_BASE_URL
    if s.LLM_MODE == "ollama":
        from app.services.providers.ollama import ollama_root
        base_url = ollama_root(base_url) + "/v1"
    return _create_llm(s.LLM_MODEL, s.LLM_API_KEY or "ollama", base_url, s.LLM_TEMPERATURE, s.LLM_MAX_TOKENS)


@lru_cache(maxsize=8)
def _create_llm(model, api_key, base_url, temperature, max_tokens):
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
        request_timeout=120,
        max_retries=2,
    )

"""对话模型：动态配置的 OpenAI 兼容 API 或 Ollama 原生流接口。"""
from functools import lru_cache
import json

import httpx
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_openai import ChatOpenAI

from app.services.model_config_service import get_model_settings


class ReasoningChatOpenAI(ChatOpenAI):
    """保留兼容 API 独立的思考字段（上游 LangChain 默认会丢弃）。"""

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        if result is not None and choices:
            delta = choices[0].get("delta") or {}
            for key in ("reasoning_content", "reasoning", "thinking"):
                if isinstance(delta.get(key), str) and delta[key]:
                    result.message.additional_kwargs["reasoning_content"] = delta[key]
                    break
        return result


class OllamaChatModel(ReasoningChatOpenAI):
    """原生流接口保留 message.thinking，输出上限映射到 num_predict。"""

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        from app.services.providers.ollama import ollama_root
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        options = {"num_predict": payload.get("max_completion_tokens", payload.get("max_tokens", self.max_tokens)),
                   "temperature": payload.get("temperature", self.temperature)}
        if stop:
            options["stop"] = stop
        key = self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        headers = {"Authorization": f"Bearer {key}"} if key and key != "ollama" else {}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", ollama_root(str(self.openai_api_base)) + "/api/chat",
                                     headers=headers, json={"model": self.model_name, "messages": payload["messages"],
                                                            "stream": True, "options": options}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise ValueError("Ollama 流式生成失败")
                    message = data.get("message") or {}
                    reasoning = message.get("thinking") or ""
                    chunk = AIMessageChunk(content=message.get("content") or "",
                                           additional_kwargs={"reasoning_content": reasoning} if reasoning else {})
                    info = {"finish_reason": data.get("done_reason") or "stop"} if data.get("done") else None
                    generation = ChatGenerationChunk(message=chunk, generation_info=info)
                    if run_manager:
                        await run_manager.on_llm_new_token(chunk.content, chunk=generation)
                    yield generation
                    if data.get("done"):
                        return
                raise ValueError("Ollama 流式响应意外结束")


def get_llm() -> ChatOpenAI:
    s = get_model_settings()
    if not s.LLM_MODEL or not s.LLM_BASE_URL or (s.LLM_MODE == "api" and not s.LLM_API_KEY):
        from app.core.exceptions import BusinessError
        raise BusinessError("model_config_required", "请先配置自己的对话模型", 428)
    base_url = s.LLM_BASE_URL
    if s.LLM_MODE == "ollama":
        from app.services.providers.ollama import ollama_root
        base_url = ollama_root(base_url) + "/v1"
    return _create_llm(s.LLM_MODEL, s.LLM_API_KEY or "ollama", base_url, s.LLM_TEMPERATURE, s.LLM_MAX_TOKENS, s.LLM_MODE)


@lru_cache(maxsize=8)
def _create_llm(model, api_key, base_url, temperature, max_tokens, mode="api"):
    provider = OllamaChatModel if mode == "ollama" else ReasoningChatOpenAI
    return provider(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
        request_timeout=120,
        max_retries=2,
    )

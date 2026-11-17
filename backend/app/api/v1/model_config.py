"""Shared model connection probes; HTTP settings live in the personal API."""
import httpx
from app.services import model_config_service as service


def _test_error(exc):
    # 不回传上游原始响应、请求头或 URL，避免泄露服务密钥。
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or (response.status_code if response is not None else None)
    if response is not None:
        try:
            error = response.json().get("error", {})
            if isinstance(error, dict) and (error.get("code") == "Arrearage" or error.get("type") == "Arrearage"):
                return "模型账户欠费或额度不可用，请检查服务商账单。"
        except (ValueError, AttributeError):
            pass
    if status in (401, 403):
        return "API Key 无效或没有模型访问权限。"
    if status == 404:
        return "服务地址或模型不存在，请检查地址、模型名称及本地模型是否已拉取。"
    if status == 429:
        return "模型服务限流或额度不足，请检查服务商控制台。"
    if status:
        return f"模型服务返回 HTTP {status}，请检查协议、模型和服务状态。"
    if isinstance(exc, httpx.TimeoutException) or "Timeout" in type(exc).__name__:
        return "模型连接超时，请检查服务是否可达或等待本地模型加载完成。"
    if isinstance(exc, httpx.TransportError) or "Connection" in type(exc).__name__:
        return "无法连接模型服务，请检查地址、端口和网络。"
    return "模型响应无效，请确认模型支持所选用途及协议；Ollama 重排需要支持 JSON 输出的对话模型。"


async def _probe(role, config):
    with service.model_settings_scope(service.runtime_settings(config)):
        if role == "llm":
            from app.services.providers.llm import get_llm

            # 思考模型在很小的输出预算内可能只返回思考 token；成功响应即连接可用。
            await get_llm().bind(max_tokens=64).ainvoke("请回复 OK")
            message = "对话模型连接成功。"
        elif role == "embedding":
            from app.services.providers.embeddings import get_embeddings

            vectors = await get_embeddings().aembed_documents(["模型连接测试"])
            message = f"Embedding 连接成功，向量维度：{len(vectors[0])}。"
        else:
            from app.services.providers.rerank import rerank

            await rerank("图书馆开放时间", ["图书馆每天九点开放。", "今天有雨。"], top_n=2)
            message = "Rerank 连接成功，已完成相关性评分。"
    return {"success": True, "message": message}

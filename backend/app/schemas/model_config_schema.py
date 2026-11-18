from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class ModelEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: Literal["api", "ollama"] = "api"
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=1000)
    api_key: SecretStr | None = None  # null 保留；空字符串清除
    protocol: Literal["openai", "dashscope"] = "openai"

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        p = urlsplit(value)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError("服务地址必须是无账号、查询参数的 HTTP/HTTPS 地址")
        return value.rstrip("/")


class ModelConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=0)
    llm: ModelEndpoint
    embedding: ModelEndpoint
    rerank: ModelEndpoint | None = None
    rerank_enabled: bool = False
    max_output_tokens: int | None = Field(None, ge=128, le=131072, strict=True)
    show_reasoning: bool | None = None

    @model_validator(mode="after")
    def validate_protocols(self):
        if self.llm.protocol != "openai" or self.embedding.protocol != "openai":
            raise ValueError("对话和 Embedding API 使用 OpenAI 兼容协议")
        if self.rerank_enabled and self.rerank is None:
            raise ValueError("启用重排时请填写 Rerank 模型配置")
        if self.rerank is not None and self.rerank.mode == "ollama" and self.rerank.protocol != "openai":
            raise ValueError("Ollama 不使用 DashScope 协议")
        return self


class ModelTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["llm", "embedding", "rerank"]
    endpoint: ModelEndpoint

    @model_validator(mode="after")
    def validate_protocol(self):
        if self.endpoint.protocol == "dashscope" and (self.role != "rerank" or self.endpoint.mode == "ollama"):
            raise ValueError("DashScope 原生协议仅用于 API Rerank")
        return self

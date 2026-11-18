"""安装环境仅配置基础设施和运行参数；模型连接配置来自每个账号的数据库记录。"""
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # ===== 数据库 (MySQL) =====
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "rag_user"
    MYSQL_PASSWORD: str = "rag_pass_2024"
    MYSQL_DB: str = "rag_qa"

    # ===== Redis =====
    REDIS_URL: str = "redis://localhost:6379/0"

    # ===== JWT =====
    JWT_SECRET: str = "dev-secret-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # ===== 模型加密与生成参数（不包含模型连接默认值） =====
    MODEL_CONFIG_ENCRYPTION_KEY: str = ""  # 为空时使用 JWT_SECRET 派生；API/worker 必须一致
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 8192

    # ===== 检索 =====
    RETRIEVAL_MODE: str = "hybrid"  # hybrid | vector
    VECTOR_TOP_K: int = 10
    BM25_TOP_K: int = 10
    RRF_K: int = 60
    SCORE_THRESHOLD: float = 0.35
    RERANK_TOP_N: int = 5

    # ===== Chroma =====
    CHROMA_MODE: str = "embedded"  # embedded | server
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_TOKEN: str = ""
    CHROMA_PERSIST_DIR: str = "storage/chroma"

    # ===== 文件存储 =====
    STORAGE_DIR: str = "storage/documents"
    MAX_UPLOAD_MB: int = 50

    # ===== 缓存 TTL =====
    EMBED_CACHE_TTL: int = 2592000
    CHAT_CACHE_TTL: int = 3600
    LOGIN_LOCK_SECONDS: int = 900

    # ===== CORS =====
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+asyncmy://{quote(self.MYSQL_USER, safe='')}:{quote(self.MYSQL_PASSWORD, safe='')}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        return BASE_DIR / self.STORAGE_DIR

    @property
    def chroma_persist_path(self) -> Path:
        return BASE_DIR / self.CHROMA_PERSIST_DIR


class ModelSettings(Settings):
    """仅由 runtime_settings.model_construct 构建，不从环境加载模型名称、端点或密钥。"""

    MODEL_CONFIG_REVISION: int = 0
    SHOW_REASONING: bool = True
    EMBEDDING_INDEX_NAMESPACE: str = ""
    LLM_MODE: str = "api"
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    EMBEDDING_MODE: str = "api"
    EMBEDDING_MODEL: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""
    RERANK_ENABLED: bool = False
    RERANK_MODE: str = "api"
    RERANK_PROVIDER: str = "openai"
    RERANK_MODEL: str = ""
    RERANK_BASE_URL: str = ""
    RERANK_API_KEY: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

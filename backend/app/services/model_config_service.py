"""数据库持久化、密钥保护和每次操作固定的配置快照（API/worker 共用）。"""
import base64
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import ModelSettings, get_settings
from app.core.exceptions import BusinessError
from app.models import ModelConfig, UserModelConfig
from app.schemas.model_config_schema import ModelConfigIn

_runtime = ContextVar("model_settings", default=None)
ROLES = {"llm": "LLM", "embedding": "EMBEDDING", "rerank": "RERANK"}


def _cipher():
    secret = get_settings().MODEL_CONFIG_ENCRYPTION_KEY or get_settings().JWT_SECRET
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def empty_config():
    return {"revision": 0, "rerank_enabled": False, **{
        role: {"mode": "api", "model": "", "base_url": "", "api_key": "", "protocol": "openai"}
        for role in ROLES
    }}


async def require_personal_config(db, user_id):
    row = await db.get(UserModelConfig, user_id) if user_id is not None else None
    if row is None:
        raise BusinessError("model_config_required", "请先在「我的模型」配置并保存自己的对话和 Embedding 模型", 428)
    return row


async def read_config(db, user_id=None):
    stmt = select(ModelConfig).where(ModelConfig.id == 1) if user_id is None else select(UserModelConfig).where(UserModelConfig.user_id == user_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return empty_config()
    result = {**row.config, "revision": row.revision}
    # 旧版本未记录命名空间时沿用其模型名索引，避免升级后丢失检索入口。
    result.setdefault("embedding_index_namespace", hashlib.md5(result["embedding"]["model"].encode()).hexdigest()[:8])
    try:
        for role in ROLES:
            endpoint = dict(result[role])
            value = endpoint.get("api_key", "")
            endpoint["api_key"] = _cipher().decrypt(value.encode()).decode() if value else ""
            result[role] = endpoint
    except InvalidToken:
        raise BusinessError("model_config_key", "模型密钥无法解密，请恢复原配置加密密钥", 503)
    return result


def public_config(config):
    result = {"revision": config["revision"], "rerank_enabled": config["rerank_enabled"]}
    for role in ROLES:
        endpoint = {k: v for k, v in config[role].items() if k != "api_key"}
        endpoint["api_key_configured"] = bool(config[role].get("api_key"))
        result[role] = endpoint
    return result


def resolve_endpoint(endpoint, previous):
    result = endpoint.model_dump(exclude={"api_key"})
    result["api_key"] = previous.get("api_key", "") if endpoint.api_key is None else endpoint.api_key.get_secret_value()
    return result


async def save_config(db, data: ModelConfigIn, user_id=None):
    previous = await read_config(db, user_id)
    if data.revision != previous["revision"]:
        raise BusinessError("config_conflict", "配置已在其他窗口修改，请刷新后重试", 409)
    resolved = {"rerank_enabled": data.rerank_enabled}
    for role in ROLES:
        incoming = getattr(data, role)
        endpoint = resolve_endpoint(incoming, previous[role]) if incoming is not None else dict(previous[role])
        if endpoint["mode"] == "api" and not endpoint["api_key"] and (role != "rerank" or data.rerank_enabled):
            raise BusinessError("missing_api_key", f"请填写 {role} 模型的 API Key")
        resolved[role] = endpoint
    changed = previous["revision"] > 0 and embedding_identity(previous) != embedding_identity(resolved)
    # 新配置按完整端点隔离；已有旧配置保留原索引命名空间。
    if changed or previous["revision"] == 0:
        namespace = hashlib.sha256("|".join(embedding_identity(resolved)).encode()).hexdigest()[:16]
    else:
        namespace = previous.get("embedding_index_namespace") or hashlib.md5(previous["embedding"]["model"].encode()).hexdigest()[:8]
    resolved["embedding_index_namespace"] = namespace
    encrypted = {**resolved}
    for role in ROLES:
        ep = dict(resolved[role])
        ep["api_key"] = _cipher().encrypt(ep["api_key"].encode()).decode() if ep["api_key"] else ""
        encrypted[role] = ep
    revision = previous["revision"] + 1
    if previous["revision"] == 0:
        db.add(ModelConfig(id=1, revision=revision, config=encrypted) if user_id is None else UserModelConfig(user_id=user_id, revision=revision, config=encrypted))
    else:
        model = ModelConfig if user_id is None else UserModelConfig
        identity = ModelConfig.id == 1 if user_id is None else UserModelConfig.user_id == user_id
        result = await db.execute(
            update(model).where(identity, model.revision == previous["revision"])
            .values(revision=revision, config=encrypted)
        )
        if result.rowcount != 1:
            await db.rollback()
            raise BusinessError("config_conflict", "配置已更新，请刷新后重试", 409)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise BusinessError("config_conflict", "配置已更新，请刷新后重试", 409)
    return {**public_config({**resolved, "revision": revision}), "embedding_changed": changed}


def get_model_settings():
    return _runtime.get() or runtime_settings(empty_config())


def runtime_settings(config):
    updates = {"RERANK_ENABLED": config["rerank_enabled"], "MODEL_CONFIG_REVISION": config["revision"],
               "EMBEDDING_INDEX_NAMESPACE": config.get("embedding_index_namespace", "")}
    for role, prefix in ROLES.items():
        ep = config[role]
        updates.update({f"{prefix}_MODEL": ep["model"], f"{prefix}_BASE_URL": ep["base_url"],
                        f"{prefix}_API_KEY": ep["api_key"], f"{prefix}_MODE": ep["mode"]})
        if role == "rerank":
            updates["RERANK_PROVIDER"] = ep["protocol"]
    return ModelSettings.model_construct(**get_settings().model_dump(), **updates)


@contextmanager
def model_settings_scope(settings):
    token = _runtime.set(settings)
    try:
        yield
    finally:
        _runtime.reset(token)


async def load_model_settings(user_id=None):
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        await require_personal_config(db, user_id)
        return runtime_settings(await read_config(db, user_id))


def embedding_identity(config):
    ep = config["embedding"]
    return ep["mode"], ep["base_url"].rstrip("/"), ep["model"]


def embedding_namespace():
    s = get_model_settings()
    if s.EMBEDDING_INDEX_NAMESPACE:
        return s.EMBEDDING_INDEX_NAMESPACE
    current = (s.EMBEDDING_MODE, s.EMBEDDING_BASE_URL.rstrip("/"), s.EMBEDDING_MODEL)
    return hashlib.sha256("|".join(current).encode()).hexdigest()[:16]

# API 清单（前缀 /api/v1）

鉴权：`Authorization: Bearer <JWT>`；错误统一格式 `{"detail": {"code": "...", "message": "..."}}`。

所有账号功能一致，认证响应和 JWT 不包含账号角色。知识库、文档、会话、模型配置和统计均限定登录账号；访问他人的资源返回 404。旧 `/admin/*` 地址仅作为个人接口的兼容别名，不授予跨账号权限，也不会修改全局模型配置。

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/register | 注册 `{username, password, email?}` → token+user；限流 3/min/IP |
| POST | /auth/login | 登录 → token+user；限流 5/min，连败 5 次锁 15 分钟 |
| GET | /auth/me | 当前账号（id、username、email、created_at，无角色字段） |
| POST | /auth/change-password | `{old_password, new_password}` |

## 会话 / 消息

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /sessions | 我的会话分页（含最后消息预览、kb 名） |
| POST | /sessions | 新建 `{title?, kb_id?}` |
| PATCH | /sessions/{id} | 重命名 |
| DELETE | /sessions/{id} | 软删除 |
| GET | /sessions/{id}/messages | 历史消息分页（正序） |
| GET | /messages/{id}/citations | 回答的引用详情（chunk 全文 + 来源 + 页码/行号） |
| POST / DELETE | /messages/{id}/feedback | 点赞/点踩 `{rating: like|dislike, comment?}` |

## 问答（SSE）

**POST /chat/stream** `{session_id, question}` → `text/event-stream`：

```
event: citations   data: {"citations":[{id,text,filename,page,row_start,row_end,heading_path,score}], "answer_mode":"knowledge", "mode":"hybrid+rerank"}
event: token       data: {"content":"..."}    (×N)
event: done        data: {"message_id":"..."}
event: error       data: {"message":"..."}
```

限流 10/min/用户；全局并发 4。检索后通过对话模型判断候选片段相关性，只将相关片段用于回答并生成引用。没有相关片段或没有可用知识库时，发送 `citations: []`、`answer_mode: "general"`、`mode: "general"`，使用普通对话模型流式回答。多轮历史保留；检索用改写问题，最终回答用原问题和历史。检索或相关性判断服务故障会明确报错，不当作「资料无关」处理。

历史消息包含 `answer_mode: knowledge|general|null`（旧记录为 null）。回答模式保存在现有 `token_usage` JSON 内，不需要新增数据库列。缓存按模式、原问题、改写问题、最近历史和当前授权片段隔离；重新生成会清理旧引用及模式，跳过答案缓存并重新判断相关性。

## 知识库

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /kbs | 本人的启用知识库；include_inactive=true 返回全部个人知识库及文档/分块/状态统计 |
| POST | /kbs | 新建个人知识库 |
| PATCH | /kbs/{id} | 编辑 / 启停自己的知识库 |
| DELETE | /kbs/{id} | 删除自己的知识库（级联清理向量） |

## 个人文档

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /documents?kb_id= | multipart 上传（pdf/docx/xlsx/csv/md/txt，≤50MB，SHA256 去重） |
| POST | /documents/url?kb_id= | 网页抓取 `{url}` |
| GET | /documents | 分页 + filter(kb_id/status/keyword)，仅本人资料 |
| GET | /documents/{id} | 详情（进度/错误） |
| POST | /documents/{id}/reparse | 重新解析 |
| POST | /documents/{id}/retry | 失败重试 |
| DELETE | /documents/{id} | 删除 |
| GET | /documents/{id}/chunks | 分块预览 |

## 个人统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /me/stats/overview | 本人的会话/消息/知识库/文档/分块/今日问答/解析成功率/反馈，不返回平台用户数 |
| GET | /me/stats/daily-qa | 本人近 30 天每日提问/回答/点赞/点踩 |
| GET | /me/stats/documents | 本人各知识库文档状态分布 |

## 个人模型配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /me/model-config | 返回本人的配置与 revision；密钥仅返回 api_key_configured 状态 |
| PUT | /me/model-config | 整体保存个人配置，新任务生效；revision 冲突返回 409 |
| DELETE | /me/model-config | 清空个人配置和密钥，回到未配置状态 |
| POST | /me/model-config/test | 测试未保存配置 `{role: llm\|embedding\|rerank, endpoint: {...}}`，返回 `{success, message}`；不会写入配置 |

保存请求示例（以下启用了重排；关闭时只需对话和 Embedding 配置）：

```json
{
  "revision": 0,
  "rerank_enabled": true,
  "llm": {"mode": "ollama", "model": "qwen3:8b", "base_url": "http://localhost:11434", "protocol": "openai", "api_key": ""},
  "embedding": {"mode": "ollama", "model": "bge-m3:latest", "base_url": "http://localhost:11434", "protocol": "openai", "api_key": ""},
  "rerank": {"mode": "ollama", "model": "qwen3:8b", "base_url": "http://localhost:11434", "protocol": "openai", "api_key": ""}
}
```

`mode` 为 `api` / `ollama`。`api_key` 省略或 `null` 保留原密钥，`""` 清除；启用的 API 模型需有密钥。`rerank_enabled` 默认 false，关闭时可省略 `rerank` 或传 null，初次保存不会生成虚拟模型或地址。Rerank API 的 `protocol` 为 `openai`（通用 `/rerank`）或 `dashscope`（原生接口）；Ollama 使用本地对话模型做 JSON 相关性评分。保存返回新的 revision 与 embedding_changed；首次保存 embedding_changed 为 false，后续更换 Embedding 时需重新解析已有文档。

## 个人知识空间（需要登录）

以下接口均按登录账号检查资源所有权。未保存个人模型配置时，GET 返回空模型名称、地址、密钥状态 false，revision 为 0、personal 为 false、rerank_enabled 为 false。运行任务不读取任何安装默认模型；遗留模型环境变量不会生效。问答、文档上传/URL 抓取、重试/重解析、含文档的备份恢复返回 HTTP 428、code=model_config_required，客户端提示该操作需要配置模型，保留当前页面，由用户主动打开模型设置。问答在写入消息前检查，上传在写入文件或入队前检查。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST / PATCH / DELETE | /kbs、/kbs/{id} | 新建、修改、删除个人知识库 |
| GET / POST | /documents | 个人文档列表、上传（kb_id 查询参数） |
| GET | /documents/{id}/file | 需 Bearer 认证，下载原文件；inline=true 仅对 PDF 内联预览 |
| GET | /documents/{id}/preview?page=1 | 文本原文分页，每段最多 20000 字符；网页使用已保存快照 |
| GET / PUT / DELETE | /me/model-config | 查看、保存或清空个人模型配置；清空后必须重新配置才能问答和解析 |
| POST | /me/model-config/test | 使用本人的密钥测试连接，不修改配置 |
| GET | /me/onboarding | 个人知识库数、文档解析状态与个人模型配置状态 |
| GET | /me/export | ZIP 原文件与聊天备份，不包含密码或模型密钥 |
| POST | /me/import | multipart file 导入知库 ZIP，添加新资料并重新解析，最大 200MB |
| POST | /me/delete-data | `{password, confirmation:"删除我的全部数据"}`，删除个人内容、缓存和配置，保留账号 |

`POST /chat/stream` 可传 `retry_message_id`，仅允许重新生成本会话最后一条 assistant 回复。后端复用原问题与回复 ID，忽略请求中替换的问题文本，并跳过答案缓存；新增 `event: start` 返回 `{message_id}`。引用事件及引用详情包含 `document_id`，用于受权原文预览。所有检索均限制在当前用户的启用知识库，缓存按用户和实际来源内容隔离。

## 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /healthz | 存活探针 |

`/healthz` 位于 API 前缀之外，只表示进程存活；当前未实现依赖就绪探针。MySQL、Redis、Chroma 和模型连接需分别检查。

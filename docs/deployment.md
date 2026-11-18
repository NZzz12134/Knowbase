# 部署手册

## 一、开发模式（本机，无 Docker）

推荐 Python 3.11、Node.js 22 LTS。先按 README 安装依赖并将 `.env.example` 复制为 `backend/.env`；本机开发使用 MySQL 8.0 + Redis（Windows 可用 Memurai）+ Chroma 嵌入式。

1. **MySQL 8.0**：建库建号（见 README）。修改 root/rag_user 密码时同步改 `backend/.env`
2. **Redis**：Windows 安装 Memurai（服务自启）；Linux/macOS 用系统包管理器
3. **后端**：`cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000`
4. **Worker**：`cd backend && .venv/Scripts/python -m celery -A app.workers.celery_app worker -P solo -l info`
   - ⚠️ Windows 下 Celery 必须 `-P solo`（prefork 不可用）
   - 嵌入式 Chroma 仅用于本机开发，保持单 API 进程、单 worker。需要并发解析或遇到共享目录锁冲突时，改用 `CHROMA_MODE=server`。
5. **前端**：在 `frontend` 目录执行 `npm ci`、`npm run dev`（Vite 已配置 `/api` 代理到 8000，支持 SSE 流式转发）。

以上 `&&` 命令适用于 Bash 或 PowerShell 7；Windows PowerShell 5.1 请将 `cd` 和启动命令分行执行。可选基础设施配置为 `docker-compose.dev.yml`；Chroma 映射为宿主机 8001 → 容器 8000，使用它时设置 `CHROMA_MODE=server`、`CHROMA_HOST=127.0.0.1`、`CHROMA_PORT=8001`。该文件仅用于本机开发。

## 二、生产模式（Docker Compose）

```bash
# 1. 配置
cp .env.example .env
#   - JWT_SECRET：改为随机长字符串（openssl rand -hex 32）
#   - MYSQL_ROOT_PASSWORD：MySQL root 密码
#   - MYSQL_PASSWORD：应用数据库密码，替换示例值
#   - CHROMA_TOKEN：随机长字符串，Chroma 服务认证必填
#   - 模型名称、地址和密钥在每个账号的「我的模型」填写，不通过安装环境设置
#   - CORS_ORIGINS：生产域名（若前端走 nginx 同域反代则无需改）

# 2. 构建并启动
docker compose up -d --build

# 3. 验证
curl http://localhost/healthz          # 经 nginx
docker compose ps                      # 6 个服务 running/healthy
```

生产模式下 Compose 已覆盖 `MYSQL_HOST=mysql`、`REDIS_URL=redis://redis:6379/0`、`CHROMA_MODE=server`、`CHROMA_HOST=chroma`、`CHROMA_PORT=8000`，无需手改这些容器内地址。worker 用 prefork 并发 2。MySQL 的密码和库名仅在空数据卷首次初始化时生效，已有数据库改密需先执行 SQL，再同步 `.env`。

如需访问宿主机 Ollama，Docker Desktop 通常使用 `host.docker.internal`；Linux Docker 需配置可达宿主机网关（例如给 backend 和 worker 添加 `extra_hosts: ["host.docker.internal:host-gateway"]`）。Ollama 也须监听允许容器连接的地址。

### 升级 / 备份

升级前先备份数据库、Chroma 索引、原文件卷以及 `.env` 中的加密密钥。下面是 **Bash / WSL / Linux/macOS** 命令，在项目根目录执行；Windows PowerShell 请使用 WSL，避免 SQL 重定向编码差异。备份目录包含私人资料与密钥，应限制访问。

```bash
mkdir -p backups
# 停止写入方及 Chroma，保证三个数据源处于同一备份窗口；MySQL 保持运行。
docker compose stop frontend backend worker chroma
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -u root --single-transaction --routines --triggers "$MYSQL_DATABASE"' > backups/mysql.sql
docker run --rm -v "$(pwd)/backups:/backup" -v rag_qa_chroma_data:/data:ro alpine tar czf /backup/chroma.tgz -C /data .
docker run --rm -v "$(pwd)/backups:/backup" -v rag_qa_documents_data:/data:ro alpine tar czf /backup/documents.tgz -C /data .
cp .env backups/service.env
chmod 600 backups/service.env
docker compose start chroma backend worker frontend
```

每条备份命令都应成功后再继续，并检查生成文件；不要用失败产生的空 SQL 文件覆盖有效备份。Redis 包含缓存和队列，本流程不复制其运行状态；恢复后检查并重试未完成的解析任务。

恢复到**空数据卷的新部署**，使用备份对应的版本与 `.env`（API / worker 加密密钥必须与备份一致）：

```bash
cp backups/service.env .env
docker compose up -d --wait mysql redis
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root "$MYSQL_DATABASE"' < backups/mysql.sql
docker run --rm -v "$(pwd)/backups:/backup:ro" -v rag_qa_chroma_data:/data alpine tar xzf /backup/chroma.tgz -C /data
docker run --rm -v "$(pwd)/backups:/backup:ro" -v rag_qa_documents_data:/data alpine tar xzf /backup/documents.tgz -C /data
docker compose up -d --build
```

普通代码升级在备份完成后运行 `docker compose up -d --build`，并核对日志与健康检查。不要使用 `docker compose down -v`，该选项会删除数据卷。

### 表结构升级（重要）

启动会自动创建新增表（包括 `model_configs`、`user_model_configs`），并将消息正文的旧 `TEXT` / `TINYTEXT` 列扩容为 `MEDIUMTEXT`，支持超过 64KB 的长回答；扩容保留已有正文，可重复启动，数据库账号需具备 `ALTER` 权限。除此以外，`create_all` 不会修改已有列。当前消息顺序使用微秒时间戳，无需新增 `seq` 列。由更早版本升级时，先用 `SHOW COLUMNS FROM messages LIKE 'created_at';` 检查：若仍为 `datetime`，应在备份后执行 `ALTER TABLE messages MODIFY COLUMN created_at DATETIME(6) NOT NULL;`。已有相同时间的旧消息按角色和 ID 稳定排序，无法完全还原已经丢失的时间精度。回答模式写入现有 `token_usage` JSON，无需新增列。

### 上线检查清单

- [ ] 已注册自己的账号并设置可靠密码（新安装没有默认账号）
- [ ] JWT_SECRET 已替换为随机串
- [ ] MYSQL_ROOT_PASSWORD、MYSQL_PASSWORD、CHROMA_TOKEN 已替换并与服务配置一致
- [ ] API / worker 使用同一 MODEL_CONFIG_ENCRYPTION_KEY（未设置时使用同一 JWT_SECRET）
- [ ] .env 未提交到版本库（.gitignore 已排除）
- [ ] 防火墙仅开放 80/443（Chroma 8001、Redis 6379、MySQL 3306 不对外）
- [ ] 生产启用 HTTPS（nginx 前挂证书或改 compose 端口映射）
- [ ] 定期备份 MySQL、Chroma、documents 卷和加密密钥，并验证恢复

## 三、模型切换（Provider 抽象）

通过「我的知识空间 → 我的模型」设置自己的对话、Embedding、Rerank 模型与 API Key，支持 API 和 Ollama 独立组合。新账号配置为空，注册或登录后正常进入聊天页，不强制跳转配置；可先浏览知识空间，使用问答或解析资料前再配置。对话和 Embedding 必填，Rerank 默认关闭。保存到数据库后，本人的新问答与新解析任务立即读取最新配置，不必重启。安装环境没有默认模型，遗留的模型名称、地址、密钥与重排开关环境变量均被忽略，可以从旧 `.env` 移除。清空个人配置后不能问答或解析，系统不会回退到共享模型。

首次升级须重建前端并重启后端和 worker，后端自动创建 `user_model_configs` 表。密钥使用 `MODEL_CONFIG_ENCRYPTION_KEY`（为空则使用 `JWT_SECRET`）派生密钥加密，API / worker 必须一致；数据库恢复时须同时保留原加密密钥。

Ollama 地址填写后端可达的根地址（本机 `http://localhost:11434`；Docker 访问宿主机通常为 `http://host.docker.internal:11434`），先用 `ollama pull` 安装相应模型。对话通过原生 `/api/chat` 保留 `message.thinking`，向量通过 `/api/embed`，重排通过 `/api/chat` 的 JSON 相关性评分实现，需要支持 JSON 输出的对话模型。专用 Rerank API 使用通用 `/rerank` 或 DashScope 原生协议。

个人输出上限和思考展示开关在「我的模型 → 回答生成设置」修改，保存到已有配置 JSON，无需新增列，保存后新请求立即生效。旧记录缺字段时使用 `LLM_MAX_TOKENS` 默认值和开启的思考展示；个人值一旦保存便覆盖环境默认值。思考保存在现有消息 JSON 中，按会话所有权访问，失败/停止时保留已收到的内容。升级需重新构建前端并重启 API / worker，以加载新增协议处理。

| 场景 | 操作 |
|---|---|
| 换 LLM（如 DeepSeek） | 「我的模型」选择 API，填写服务商模型名称、兼容地址和自己的 API Key |
| 换 Embedding | 在「我的模型」修改模型、部署方式或服务地址后，对已有文档执行「重新解析」。索引与缓存按模型和端点隔离；解析/删除时清理该文档各版本旧向量，避免切回模型后出现过时内容 |
| 关 Rerank | 在「我的模型」关闭「启用重排」 |
| 纯向量检索 | `RETRIEVAL_MODE=vector` |

## 四、统一个人空间版本升级

重建前端并重启 API 和 Celery worker。启动时会自动创建新增 `user_model_configs` 表，不改动已有资料；API 与 worker 必须使用相同的配置加密密钥。

所有账号功能一致，不再区分管理员和普通用户。知识库按 `created_by` 归属个人，原共享库仅其创建账号可见。每个账号均可进入 `/space/library` 上传资料、配置模型并查看自己的统计；每次文档解析使用知识库创建者的模型配置，每次问答使用登录账号的配置。

启动迁移会先将旧 `model_configs` 中的加密配置复制给原管理员账号（已有个人配置则保留），再将旧角色标记归一。保留 `users.role` 列以兼容已有数据库，但应用不再依据它授权，JWT 和认证响应也不再返回账号角色。旧账号密码和资料不变；新安装不创建默认账号。迁移可重复运行；API 与 worker 只使用个人模型配置，未配置时返回明确提示，不读取安装环境或遗留全局模型。旧 `/admin` 页面跳转到个人空间，旧 API 是受同样所有权校验保护的兼容别名。

个人备份入口在 `/space/data`，包括原文件与聊天，不含密码、模型配置或向量索引。恢复会添加新知识库并重建索引，含文档时需先配置模型；部署者仍需定期备份 MySQL、Chroma、documents 卷和加密密钥以完整恢复服务。Nginx 为 200MB 备份上传预留了 multipart 开销，API 限制备份包及解压后内容均不超过 200MB，单份文档仍限 50MB。

删除个人数据需要密码和明确确认；解析/生成任务进行中会返回 409，索引或缓存服务不可用会返回 503，可恢复服务后重试。已损坏或缺失原文件的记录应先重新上传或移除后再导出备份。

## 五、性能调参

| 参数 | 默认 | 说明 |
|---|---|---|
| VECTOR_TOP_K / SCORE_THRESHOLD | 10 / 0.35 | 向量召回数与 cosine 阈值，BGE 系起步值；漏召回调低阈值 |
| BM25_TOP_K / RRF_K | 10 / 60 | BM25 召回数 / RRF 融合常数 |
| RERANK_TOP_N | 5 | 重排后送 LLM 的块数 |
| CHAT_CACHE_TTL | 3600 | 相同问题答案缓存（Redis） |
| EMBED_CACHE_TTL | 2592000 | embedding 去重缓存，省 API 费用核心 |
| worker --concurrency | 2 | 解析并发（受 embedding API 限速约束） |

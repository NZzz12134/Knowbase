# 知库 Knowbase · 知识工作台

基于 **LangChain + FastAPI + Vue 3** 的个人知识助手。上传自己的资料，通过浏览器进行**带引用溯源的多轮流式问答**。所有账号使用同一套个人工作台，可管理知识库、文档、模型和备份；不同账号的资料、会话、模型配置与统计相互隔离。

## ✨ 核心特性

| 特性 | 说明 |
|---|---|
| 流式问答 + 引用溯源 | SSE token 级流式输出；回答标注 `[1][2]` 编号，引用卡片显示片段文本、来源文件、页码/行号/章节，可点击查看全文 |
| 混合检索 | 向量检索（Chroma HNSW）+ BM25 中文分词 + RRF 融合，可选 Rerank 重排，`RETRIEVAL_MODE` 可切换 |
| 多轮对话 | 追问自动改写为独立检索问题（如"那它的续航呢？"→理解指代） |
| 自动回答模式 | 检索后判断片段相关性；相关问题结合资料回答并展示引用，无关问题由模型直接回答；没有知识库时也能普通聊天 |
| 多用户多会话 | 每用户独立会话、服务端持久化、跨设备找回历史；会话可绑定指定知识库或全库检索 |
| 7 类文档解析 | PDF / Word / Excel / CSV / Markdown / TXT / 网页 URL，异步解析 + 进度展示 + 失败重试 |
| 成本优化 | Embedding 去重缓存（30 天）、答案缓存（1 小时）；命中时复用向量或回答，检索与相关性判断仍按当前资料执行 |
| 安全 | JWT + bcrypt、按账号检查资源所有权、上传文件 magic bytes 校验、URL SSRF 防护、登录连败锁定、API 限流 |
| 个人工作台 | 知识库 CRUD、文档上传/解析状态/重试/删除/分块预览、个人使用统计（问答趋势/反馈/文档分布） |
| 模型配置 | 每个账号分别配置对话 / Embedding / Rerank 模型、服务地址和 API Key；支持 API 与 Ollama 混用、连接测试、保存即时生效，密钥加密存储 |
| 专注的工作体验 | 暖白与墨绿主题、统一几何品牌图标；即时流式回答、智能滚动、会话搜索、自适应移动布局、键盘导航与减少动态效果支持 |
| 个人知识空间 | 每个账号独立创建知识库、上传与管理资料；检索、引用、原文件和缓存均按个人范围隔离 |
| 个人模型与数据 | 个人 API / Ollama 配置、加密密钥、可选配置提示、回答重新生成、PDF 原文定位、ZIP 备份恢复与个人数据删除 |

## 🏗 技术栈

| 层 | 选型 |
|---|---|
| RAG 框架 | LangChain 0.3（LCEL 链） |
| 后端 | Python 3.11 / FastAPI / SQLAlchemy 2.0 async / Celery |
| 数据库 | MySQL 8.0（用户/会话/消息/文档/分块/引用/反馈/模型配置） |
| 向量库 | Chroma 0.5（embedded / server 双模式） |
| 缓存/队列 | Redis 7（限流、embedding 去重、答案缓存、Celery broker） |
| 大模型 | 每个账号自行配置 OpenAI 兼容 API 或本地 Ollama，对话、Embedding、Rerank 可独立组合 |
| 前端 | Vue 3 + Element Plus + Pinia + Vite + ECharts |
| 部署 | Docker Compose（全栈）/ 本机开发模式 |

## 📁 目录结构

```
├── backend/                # 后端（FastAPI + LangChain）
│   ├── app/
│   │   ├── api/v1/         # 路由：认证/会话/聊天(SSE)/引用/反馈/知识库/文档/统计
│   │   ├── services/
│   │   │   ├── parsing/    # 7 类文档解析器 + 分块策略 + 解析 pipeline
│   │   │   ├── providers/  # LLM/Embedding/Rerank 抽象层（配置切换）
│   │   │   └── rag/        # Chroma/BM25/混合检索/问答链/缓存
│   │   ├── models/         # SQLAlchemy 模型
│   │   └── workers/        # Celery 文档解析任务
│   ├── tests/              # 认证、数据隔离、解析与问答回归测试
│   └── requirements.txt
├── frontend/               # 前端（Vue 3 + Element Plus）
├── docs/                   # API 文档、部署手册
├── scripts/                # 冒烟测试脚本、示例文档生成
├── docker-compose.yml      # 生产全栈部署
├── docker-compose.dev.yml  # 开发基础设施（可选）
├── start_dev.bat           # Windows 一键启动（本机开发模式）
├── stop_dev.bat            # Windows 一键停止
└── .env.example            # 配置模板（Docker 复制为 .env，本机开发复制为 backend/.env）
```

## 🚀 快速开始

### 环境要求

- **Docker 部署**：Docker Engine / Docker Desktop + Docker Compose v2；宿主机无需安装 Python、Node.js 或数据库。
- **本机开发**：Python 3.11（推荐，与 Docker 镜像一致）、Node.js 22 LTS、MySQL 8.0 和 Redis（Windows 可用 Memurai）。
- 问答与资料解析使用个人模型配置，可选择云端 API 或后端能够访问的 Ollama；新安装不附带模型。

### 方式一：Docker Compose 一键部署（推荐）

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env，必填项：
#   模型在注册登录后通过「我的模型」配置，安装环境不设置模型或 API Key
#   CHROMA_TOKEN      —— 任意随机串（如 openssl rand -hex 32），Chroma 认证用
#   MYSQL_ROOT_PASSWORD —— MySQL root 密码
#   MYSQL_PASSWORD   —— 应用数据库密码（不要保留示例值）
#   JWT_SECRET        —— 任意随机串（如 openssl rand -hex 32）

# 2. 启动（首次构建约几分钟）
docker compose up -d --build

# 3. 访问
# 浏览器打开 http://localhost
```

停止：`docker compose down`（数据保存在卷中，不会丢失）

### 方式二：本机开发模式（不装 Docker）

<details>
<summary>Windows 步骤（Linux/macOS 类比，命令差异见备注）</summary>

**1. 准备数据库与 Redis**

- MySQL 8.0：建库建号（Linux/macOS 用包管理器安装后执行相同 SQL）

```sql
CREATE DATABASE rag_qa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rag_user'@'localhost' IDENTIFIED BY 'replace-with-your-password';
GRANT ALL PRIVILEGES ON rag_qa.* TO 'rag_user'@'localhost';
```

- Redis：Windows 安装 [Memurai](https://www.memurai.com/get-memurai)（Redis 兼容服务）；Linux/macOS 用系统包安装 redis
- ⚠️ 配置里 Redis/MySQL 地址用 `127.0.0.1`，不要用 `localhost`（Python 解析 localhost 优先 IPv6，而多数 Windows 服务只监听 IPv4）

**2. 后端**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item ../.env.example .env
# 编辑 .env，使 MYSQL_PASSWORD 与建号时的密码一致，并替换 JWT_SECRET。
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**3. 文档解析 Worker**（另开一个终端）

```powershell
cd backend
# Windows 必须加 -P solo；Linux/macOS 可去掉
.venv\Scripts\python -m celery -A app.workers.celery_app worker -P solo -l info
```

**4. 前端**（再开一个终端）

```bash
cd frontend
npm ci
npm run dev        # 打开 http://localhost:5173
```

**5. 一键脚本（仅 Windows）**：完成依赖安装与 `backend/.env` 配置后，双击 `start_dev.bat` 启动全部、`stop_dev.bat` 停止全部。

Linux/macOS 将 `Copy-Item` 换为 `cp`，虚拟环境命令改用 `.venv/bin/python`，其余步骤相同。

</details>

## ⚙️ 模型与环境配置

登录后进入「我的知识空间 → 我的模型」（`/space/models`），可分别设置对话、Embedding 和 Rerank 的部署方式、模型名称、Base URL 和 API Key。三个模型可独立使用 API 或 Ollama；支持测试未保存的配置、关闭 Rerank。API 模式使用 OpenAI 兼容的聊天 / Embedding 接口，Rerank 支持通用 `/rerank` 和 DashScope 原生协议。

本地 Ollama 示例（先自行拉取模型）：

```bash
ollama pull qwen3:8b
ollama pull bge-m3
```

对话和 Embedding 的部署方式选「Ollama 本地」，服务地址填 `http://127.0.0.1:11434`，对话模型填 `qwen3:8b`，Embedding 填 `bge-m3:latest`，模型名称应与 `ollama list` 一致。Rerank 可先保持关闭；如需本地重排，可启用并选择支持 JSON 输出的对话模型（如 `qwen3:8b`）。Ollama 没有原生 Rerank API，此处逐文档打分，速度取决于硬件；专用重排服务请选择 API 模式。

地址由后端与 worker 访问。Docker Desktop 访问宿主机通常使用 `http://host.docker.internal:11434`；Linux Docker 需自行配置宿主机网关或可达地址。Ollama 的监听地址须允许容器访问。云端 API 的 Base URL 应包含服务商要求的兼容前缀（例如 `https://api.example.com/v1`）；对话和 Embedding 可以使用不同服务商，所选模型须支持对应接口。

新账号模型配置为空，注册或登录后正常进入聊天页，可先浏览知识空间，再按需配置模型。请填写自己的对话和 Embedding 模型，测试连接后保存；Rerank 默认关闭，可稍后添加。系统没有安装默认模型，不读取 `.env` 中遗留的模型名称、服务地址、API Key 或重排开关。未保存个人配置时，问答、上传、重解析和包含文档的备份恢复返回 428，且不会调用模型。保存后新问答和新解析任务读取个人数据库配置，正在执行的任务保留原配置。API Key 留空保留原值，勾选清除可删除密钥（本地 Ollama 通常无需密钥）。密钥通过 Fernet 加密存储，前端仅收到「已配置」状态。清空模型配置会回到未配置状态，资料与聊天保留。

升级时重建前端，重启后端和 Celery worker，后端启动自动创建新增的 `user_model_configs` 表。可设置独立的 `MODEL_CONFIG_ENCRYPTION_KEY`，为空时由 `JWT_SECRET` 派生；API / worker 必须保持一致，备份数据库时保留对应加密密钥。更换加密密钥前需要迁移已保存的密钥。

安装运行参数：

| 配置项 | 说明 |
|---|---|
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | 回答生成参数，不指定任何模型或密钥 |
| `RETRIEVAL_MODE` | `hybrid`（混合检索，默认）/ `vector`（纯向量） |
| `CHROMA_MODE` | `embedded`（本机开发）/ `server`（生产，compose 已自动配置） |
| `JWT_SECRET` | 生产必改随机串 |
| `SCORE_THRESHOLD` / `VECTOR_TOP_K` / `RERANK_TOP_N` | 检索调优参数 |

> 更换 Embedding 模型、部署方式或地址后，需在「我的文档」对已有文档执行「重新解析」重建向量。

## 📖 使用指南

新安装通过注册创建账号，不生成默认管理员或默认密码。所有账号功能一致。

1. 注册或登录后可先浏览聊天页、创建知识库或管理账号。准备聊天或上传解析资料时，再到「我的模型」配置自己的对话和 Embedding 模型；保存后也可导入示例资料体验。
2. 左侧「我的知识空间」（`/space/library`）管理自己的知识库；「我的文档」上传、查看解析进度、重试失败任务、预览原文和下载原文件。
3. 「我的模型」可填写自己的对话 / Embedding / Rerank API 或 Ollama 配置并测试连接。模型名称、地址和密钥初始为空，不使用共享模型。Ollama 地址由后端访问，远程网站的 localhost 指服务器。「使用统计」展示自己的问答趋势、反馈和文档解析情况。
4. 新会话可检索自己的全部启用知识库或指定其中一个。系统自动判断检索片段与问题的相关性：相关时结合资料回答并保留引用，无相关资料时正常直接回答。回答会标注「结合知识库回答」或「模型直接回答」，重载历史后仍保留。直接回答不会附带知识库引用，也不会推测未提供的私人文档事实。回答中的引用可打开 PDF 对应页；Office、文本及网页显示原文提取内容。可对最后一条回答重新生成或失败重试，不重复创建提问。
5. 「数据与备份」（`/space/data`）导出原文件、聊天 JSON、引用快照和 Markdown，或恢复 ZIP 备份。恢复会添加新知识库并重新解析文档，保留现有数据；旧聊天引用快照保存在备份 JSON 中，不重新绑定新索引。备份不含密码和模型配置，含文档的恢复需先配置模型，只有聊天和空知识库的备份可直接恢复；导入压缩及解压总量均限 200MB。
6. 删除个人全部数据需输入当前密码和确认文字，账号仍保留；解析或回答任务完成后才能执行。删除范围包括个人知识库、上传文件、聊天、引用、缓存和个人模型配置。

升级后，原知识库仍归其 `created_by` 用户所有，旧账号和资料保留。原管理员的全局模型配置会迁入该账号的个人配置（已有个人配置时保留个人配置），随后停用旧角色标记。未配置个人模型的账号可正常进入并浏览，仅在问答或解析资料前需要配置；已有个人配置继续保留。旧 `/admin` 页面会转到个人工作台；旧后台 API 仅作为个人接口别名，无法访问他人的资料或全局配置。`users.role` 列仅为旧数据库兼容保留，认证响应和 JWT 不再包含账号角色。

## 🧪 测试

后端测试需要可连接的 MySQL 和 Redis。先在专用开发/测试实例上建库授权（密码与 `backend/.env` 一致）：

```sql
CREATE DATABASE IF NOT EXISTS rag_qa_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON rag_qa_test.* TO 'rag_user'@'localhost';
```

测试固定使用 `rag_qa_test` 数据库、Redis DB 9 和 `backend/storage/chroma_test`；会重建测试库中的全部表。不要让其他应用共用这些测试资源。模型调用由 mock 替代，无需真实 API Key，测试不验证真实服务商连接。

```powershell
cd backend
.venv\Scripts\python -m pytest tests/       # 认证/数据隔离/会话/解析/安全/RAG 链路/反馈/个人统计
# 生成 HTML 报告
.venv\Scripts\python -m pytest tests/ --html=../docs/test-report.html --self-contained-html
```

前端检查（在 `frontend` 目录执行）：

```bash
npm ci
npm test
npm run build
```

需要验证真实模型与解析 worker 时，可在项目根目录运行 `backend/.venv/Scripts/python scripts/test_api.py` 和 `backend/.venv/Scripts/python scripts/test_chat.py`。脚本会提示输入已保存个人模型配置的账号，调用真实服务并产生测试数据；示例文件可先运行 `scripts/seed_demo.py` 生成。

## ❓ 常见问题

| 问题 | 解决 |
|---|---|
| 扫描版 PDF 解析失败 | 系统仅支持文字型 PDF。扫描件请先 OCR 转换，或转存为 Word/文本格式 |
| 上传后一直「待解析」 | Worker 未启动（开发模式需单独跑 Celery）；或 Redis 不可用——检查 `REDIS_URL` 是否为 `127.0.0.1` |
| 问答报「模型 API 返回错误」 | 在「我的模型」测试连接，检查自己的 API Key、服务地址及额度 |
| 引用排序效果一般 | 在「我的模型」启用可用的 Rerank 服务，或调整 `VECTOR_TOP_K`、`BM25_TOP_K` 和 `RERANK_TOP_N` 后重启 API / worker |
| 部署后访问不了 | 检查 `docker compose ps` 各服务是否 healthy；`curl http://localhost/healthz` 应返回 `{"status":"ok"}` |
| Windows 开发时 Celery 报错 | 必须使用 `-P solo` 参数 |
| 想换大模型厂商 | 在「我的模型」更改模型名称、服务地址和密钥；更换 Embedding 后重新解析资料 |

## 📚 更多文档

- [API 接口清单](docs/api.md) —— 全部路由、参数、SSE 事件协议
- [部署手册](docs/deployment.md) —— 生产部署、备份恢复、模型切换、性能调参、上线检查清单

## 📄 License

MIT

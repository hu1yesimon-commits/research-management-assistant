# Research Management MVP

当前仓库已经落地的是一个后端 MVP：`FastAPI + LangGraph + SQLite`，用于论文候选检索、排序、持久化和实验日志记录。

本文档只同步已经完成的事实，不把计划中的真实 embedding provider、RAG retrieval、前端工作台写成已完成；`Advanced-lite` 目前也只是 deterministic placeholder，不是真实 LLM / RAG research agent。

## Current Scope

目前已经完成：

- FastAPI 入口在 [backend/src/main.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/main.py)
- SQLite 持久化在 [backend/src/services/memory_store.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/services/memory_store.py)
- PDF upload + Phase 2C text extraction/chunking 在 [backend/src/services/knowledge_base.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/services/knowledge_base.py)
- 基础 graph flow 在 [backend/src/graph/builder.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/graph/builder.py) 和 [backend/src/graph/nodes.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/graph/nodes.py)
- API tests、graph tests、store tests 已覆盖当前 MVP 主路径

## Implemented Endpoints

当前可用接口：

- `GET /health`
  返回 `{"status": "ok"}`
- `POST /search`
  输入 `{"mode":"basic"|"advanced","query":"..."}`
  调用 paper discovery graph，返回 ranked candidates，并把 candidate + judgement 写入 SQLite
- `GET /papers/candidates`
  从 SQLite 读取候选论文
- `POST /papers/{paper_id}/accept`
  将已存在论文的状态更新为 `accepted`
- `POST /papers/{paper_id}/upload_pdf`
  接收 multipart PDF 文件，保存到本地 upload 目录，把论文状态更新为 `uploaded`，并记录 `pdf_path`
- `POST /papers/{paper_id}/embed`
  当前是 phase-aware 路由：`uploaded` 论文执行本地 PDF 文本抽取和 chunk 持久化并进入 `chunked`；`chunked` 论文执行 embedding pipeline 并在所有 chunk 获得非空 `vector_ref` 后进入 `embedded`
- `POST /logs`
  写入实验日志
- `GET /logs`
  读取实验日志
- `GET /memory/summary`
  返回 `candidate_count`、`known_dois`、`recent_logs`
- `POST /knowledge/search`
  输入 `{"query":"...","top_k":5}`，对已 `embedded` 的知识块执行 retrieval MVP，返回 chunk / paper 信息；当前只做召回，不做 RAG answer generation 或 LLM 总结
- `POST /knowledge/answer`
  输入 `{"question":"...","top_k":5}`，基于 retrieval 结果返回 grounded answer MVP；当前默认使用 deterministic fake answer generator，不调用真实 LLM
- `POST /research/query`
  输入 `{"query":"...","mode":"basic"|"advanced","include_discovery":true,"include_knowledge":true,"top_k":5}`，把外部 discovery 和内部 knowledge answer 编排到一个响应中；`discovery.candidates` 不是 grounded answer sources，`knowledge.sources` 只来自已 `embedded` 的知识块

## Persistence

当前 SQLite store 负责：

- 初始化本地数据库表
- 保存 candidate paper
- 保存 judge result
- 查询 candidate papers
- 更新 paper 状态
- 保存和查询 experiment logs
- 查询 known DOI
- 保存、查询、删除 `knowledge_chunks`

当前表：

- `papers`
- `paper_judgements`
- `experiment_logs`
- `knowledge_chunks`

`known DOI` 规则当前是：

- 只返回状态为 `uploaded`、`chunked` 或 `embedded` 的 DOI
- `candidate` 状态不会进入强去重集合

## Paper Lifecycle

当前 `paper` 生命周期不应理解为强制线性流程，而应理解为“推荐路径 + 当前允许的可选路径”。

推荐路径：

`candidate -> accept -> accepted -> upload_pdf -> uploaded -> embed -> chunked -> embed -> embedded`

当前代码允许的可选路径还包括：

- `candidate -> upload_pdf -> uploaded`
- `candidate -> accept -> accepted -> upload_pdf -> uploaded`

各状态含义：

- `candidate` = 系统检索、judge、rank 后写入 SQLite 的推荐候选论文
- `accepted` = 可选的人工确认状态，表示用户已经认可这篇论文，但还没有上传 PDF
- `uploaded` = PDF 已保存到本地 upload 目录，`pdf_path` 已记录，DOI 会进入强去重集合
- `chunked` = PDF 文本抽取成功，chunks 已持久化到 `knowledge_chunks`；这仍然不是“真实 embedding 完成”
- `embedded` = embedding pipeline 已完成，且所有目标 chunk 都有可追踪的非空 `vector_ref`

## Knowledge-Base Stub

当前 knowledge-base 已进入 Phase 2C，但这里的状态流是“当前实现允许的路径”，不是强制要求所有 paper 都先经过 `accepted`。

推荐使用路径：

`candidate -> accept -> accepted -> upload_pdf -> uploaded -> embed -> chunked -> embed -> embedded`

当前实际行为：

- `upload_pdf` 只要求 paper 已存在于 SQLite，不要求当前状态必须是 `accepted`
- PDF bytes 会保存到本地 upload 目录
- 文件名会做基础安全归一化
- `upload_pdf` 会把 `papers.status` 更新为 `uploaded`
- `upload_pdf` 会记录本地 `pdf_path`
- 因此当前既支持 `candidate -> upload_pdf -> uploaded`，也支持 `candidate -> accept -> accepted -> upload_pdf -> uploaded`
- `embed` 对 `uploaded` 论文执行 Phase 2C：本地 PDF 文本抽取和 chunk persistence；失败时保持 `uploaded`
- `embed` 对 `chunked` 论文执行 embedding pipeline；只有全部目标 chunk 拿到非空 `vector_ref` 才会进入 `embedded`
- `embed` 在 Phase 2D 重跑时会替换旧 `vector_ref`，失败时保持 `chunked`
- uploaded paper 的 DOI 会进入 `MemoryStore.list_known_dois()`
- chunked paper 继续保留同一个 `pdf_path`

当前已完成但不是默认配置：

- `EMBEDDING_PROVIDER=bge-m3` 时，可选真实 BGE-M3 provider 会参与 Phase 2D embedding
- `VECTOR_BACKEND=chroma` 时，可选真实 Chroma adapter 会把向量写入本地 persist dir
- 手动 smoke 已通过一条真实链路：
  `chunked -> BGE-M3 -> Chroma -> vector_ref -> embedded`

当前还没有做：

- 生产级 RAG answer generation
- `/search` 与 Chroma retrieval 的联动
- PDF 内容和 paper metadata 的一致性校验
- OCR
- 复杂版式恢复

## Search Flow

当前 `/search` 走的是同步后端链路：

`request -> rewrite_query -> multi_source_search -> dedup_papers -> judge_papers -> rank_papers -> persist_candidates`

当前 graph 行为：

- `basic` 模式下 query rewrite 返回原 query
- `advanced` 模式下 query rewrite 是 deterministic placeholder，不是真实 LLM / RAG agent
- dedup 会结合 `MemoryStore.list_known_dois()` 和当前 batch 的 title 弱去重
- judge 仍然是 mock `LLMJudge`
- 排序后会把 candidate 和 judgement 持久化到 SQLite

当前 Advanced-lite placeholder 规则：

- 从 experiment logs 构造 `memory_context`
- 如果上下文包含 `light` / `heavy` / `轻量`，追加 `lightweight`
- 如果上下文包含 `interpret` / `可解释`，追加 `interpretability`
- 如果上下文包含 `module` / `模块`，追加 `modular architecture`
- 如果上下文包含 `loss` / `损失`，追加 `loss function`
- 如果没有命中规则，则回退到 `survey` 和 `recent methods`

## Run

安装依赖：

```bash
uv sync --dev
```

如果本机 `uv` cache 权限有问题，可以这样跑：

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv sync --dev
```

启动 API：

```bash
PYTHONPATH=backend/src ./.venv/bin/uvicorn main:app --app-dir backend/src --port 8000
```

快速检查：

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/memory/summary
```

## Frontend MVP

当前仓库包含一个 Vue 3 + Vite 单页前端 MVP，主入口是 `POST /research/query`。

当前前端范围：

- 页面加载时调用 `GET /health` 显示 backend status
- 查询工作台把 unified workflow 分成 `knowledge` 和 `discovery` 两个 section
- `discovery.candidates` 只表示推荐阅读候选，不等同于 grounded answer sources
- `knowledge.sources` 只表示已 `embedded` 本地知识库证据
- candidates 面板支持调用：
  - `GET /papers/candidates`
  - `POST /papers/{paper_id}/accept`
  - `POST /papers/{paper_id}/upload_pdf`
  - `POST /papers/{paper_id}/embed`

运行方式：

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

默认前后端地址：

- `VITE_API_BASE_URL=http://127.0.0.1:8000`

构建：

```bash
cd frontend
npm run build
```

这个前端目前是工程化工作台 MVP，用于联调当前后端 contract，不应理解为生产级前端。

## Tests

当前推荐测试命令：

运行全部后端测试：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

当前在仓库内执行这条命令，应得到全部测试通过；具体 case 数会随着 Phase 2D 测试增加而变化。

运行当前 MVP 关键测试：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_api_mvp.py \
  backend/src/tests/test_memory_store.py \
  backend/src/tests/test_deduplicator.py \
  backend/src/tests/test_paper_discovery_graph.py \
  -q
```

## Current Limitations

当前明确还没有完成：

- 真实 LLM judging
- 真实的 LLM / RAG query planning agent
- 外网依赖下的稳定 search 集成测试
- 完整 RAG 查询链路，以及 `/search` 到 retrieval 的联动
- 生产级前端界面
- 数据库迁移机制

## Retrieval MVP

当前 Phase 2E 已实现一个 retrieval MVP：

- `POST /knowledge/search` 会先把 query 变成 embedding
- 再向当前配置的 vector store 查询最近 chunks
- 再从 SQLite 补充 `paper_id`、`chunk_index`、`text`、`vector_ref`、`title`

当前返回的是可解释的检索结果，不是答案生成：

- 已实现：chunk retrieval
- 未实现：RAG answer generation
- 未实现：LLM 总结
- 未实现：`/search` 与 Chroma retrieval 联动

## Grounded Answer MVP

当前 Phase 2F 已实现一个 grounded answer MVP：

- `POST /knowledge/answer` 会先调用 `/knowledge/search` 等价的 retrieval 流程
- 再由 deterministic fake answer generator 基于 sources 生成答案
- 返回 `question`、`answer`、`sources`、`mode`

当前仍然不是生产级 RAG：

- 默认不调用真实 LLM
- 真实 answer provider 只在显式配置时启用，不属于默认离线路径
- 未实现多轮 chat
- 未实现 streaming / SSE
- 不保证真实 LLM answer provider 已达到生产级质量

## Unified Research Query Workflow

当前 Phase 2H 已实现一个轻量 orchestration endpoint：

- `POST /research/query` 可在一个响应里同时返回：
  - 外部 discovery candidates
  - 内部 knowledge grounded answer
- `discovery` 和 `knowledge` 会分成两个独立 section
- discovery candidates 不会被当作 grounded answer sources
- `knowledge.answer` 与 `knowledge.sources` 只来自已 `embedded` 的 knowledge chunks

## Vector Backend

当前 embedding pipeline 默认仍使用 fake provider 和 fake vector backend。

embedding provider 当前也支持两种模式：

- `EMBEDDING_PROVIDER=fake`
  默认模式，基础测试和离线 contract 验证都走这个路径
- `EMBEDDING_PROVIDER=bge-m3`
  可选的 BGE-M3 provider，模型名由 `BGE_M3_MODEL_NAME` 控制；只有显式配置时才会加载模型

向量存储 backend 当前支持两种模式：

- `VECTOR_BACKEND=fake`
  默认模式，测试和本地离线 contract 验证都走这个路径
- `VECTOR_BACKEND=chroma`
  可选的真实 Chroma adapter，持久化目录由 `CHROMA_PERSIST_DIR` 控制，collection 名由 `CHROMA_COLLECTION_NAME` 控制

当前已完成的是可选的 BGE-M3 provider 接入和可选的 Chroma adapter 接入，不代表 retrieval、完整 RAG、问答能力或端到端语义检索已经完成。

BGE-M3 运行说明：

- 首次运行 `EMBEDDING_PROVIDER=bge-m3` 时，可能需要下载 `BAAI/bge-m3` 模型
- 这一步不在默认 pytest 和 CI 中执行

Chroma 运行说明：

- `VECTOR_BACKEND=chroma` 时，向量会写入本地 `CHROMA_PERSIST_DIR`
- `embedded` 的严格语义不变：只有所有目标 chunks 都有非空 `vector_ref` 时，paper 才能进入 `embedded`

手动 smoke 结果：

- `EMBED_RESPONSE={"paper_id":"smoke-paper-1","status":"embedded","vector_ref_count":2}`
- `SQLITE_VECTOR_REF_COUNT=2`
- `SQLITE_VECTOR_REFS_OK=true`
- `CHROMA_ID_COUNT=2`
- `CHROMA_WRITE_OK=true`

另外还有几个当前限制需要注意：

- `/search` 的稳定测试目前依赖 fake graph / fake search 输入，不依赖外网
- `/search` 当前还没有与 Chroma retrieval 联动，也没有走向量检索
- `PaperSearchService` 真实路径会访问外部源，受网络和第三方接口状态影响
- `memory/summary` 目前是组合查询，不是单独优化过的 summary read model
- Advanced-lite 目前只消费 experiment logs，不读取历史对话、论文摘要或知识库

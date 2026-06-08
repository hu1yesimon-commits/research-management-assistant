# Research Management MVP

当前仓库已经落地的是一个后端 MVP：`FastAPI + LangGraph + SQLite`，用于论文候选检索、排序、持久化和实验日志记录。

本文档只同步已经完成的事实，不把计划中的 PDF 文本抽取、向量库、前端工作台写成已完成；`Advanced-lite` 目前也只是 deterministic placeholder，不是真实 LLM / RAG research agent。

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
  当前是 Phase 2C chunking 路由：仅允许 `uploaded` 论文执行本地 PDF 文本抽取和 chunk 持久化，成功后把状态更新为 `chunked`，返回 `paper_id`、`status`、`pdf_path`、`chunk_count`
- `POST /logs`
  写入实验日志
- `GET /logs`
  读取实验日志
- `GET /memory/summary`
  返回 `candidate_count`、`known_dois`、`recent_logs`

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

`candidate -> accept -> accepted -> upload_pdf -> uploaded -> embed -> chunked`

当前代码允许的可选路径还包括：

- `candidate -> upload_pdf -> uploaded`
- `candidate -> accept -> accepted -> upload_pdf -> uploaded`

各状态含义：

- `candidate` = 系统检索、judge、rank 后写入 SQLite 的推荐候选论文
- `accepted` = 可选的人工确认状态，表示用户已经认可这篇论文，但还没有上传 PDF
- `uploaded` = PDF 已保存到本地 upload 目录，`pdf_path` 已记录，DOI 会进入强去重集合
- `chunked` = PDF 文本抽取成功，chunks 已持久化到 `knowledge_chunks`；这仍然不是“真实 embedding 完成”
- `embedded` = 预留给未来真实 embedding 阶段；只有当真实 embedding 完成且 `vector_ref` 可追踪时，才应该进入 `embedded`

## Knowledge-Base Stub

当前 knowledge-base 已进入 Phase 2C，但这里的状态流是“当前实现允许的路径”，不是强制要求所有 paper 都先经过 `accepted`。

推荐使用路径：

`candidate -> accept -> accepted -> upload_pdf -> uploaded -> embed -> chunked`

当前实际行为：

- `upload_pdf` 只要求 paper 已存在于 SQLite，不要求当前状态必须是 `accepted`
- PDF bytes 会保存到本地 upload 目录
- 文件名会做基础安全归一化
- `upload_pdf` 会把 `papers.status` 更新为 `uploaded`
- `upload_pdf` 会记录本地 `pdf_path`
- 因此当前既支持 `candidate -> upload_pdf -> uploaded`，也支持 `candidate -> accept -> accepted -> upload_pdf -> uploaded`
- `embed` 当前只做本地 PDF 文本抽取和 chunk persistence，不做真实 embedding
- `embed` 只允许 `uploaded` 论文进入处理；失败时保持 `uploaded`
- `embed` 成功后会删除同一 `paper_id` 的旧 chunks，写入新 chunks，再把状态更新为 `chunked`
- uploaded paper 的 DOI 会进入 `MemoryStore.list_known_dois()`
- chunked paper 继续保留同一个 `pdf_path`

当前还没有做：

- 真实 embedding
- 真实向量库写入
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

## Tests

当前推荐测试命令：

运行全部后端测试：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

当前在仓库内执行这条命令，应得到 `55 passed`。

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
- 向量库 / embedding 入库
- 前端界面
- 数据库迁移机制

另外还有几个当前限制需要注意：

- `/search` 的稳定测试目前依赖 fake graph / fake search 输入，不依赖外网
- `PaperSearchService` 真实路径会访问外部源，受网络和第三方接口状态影响
- `memory/summary` 目前是组合查询，不是单独优化过的 summary read model
- Advanced-lite 目前只消费 experiment logs，不读取历史对话、论文摘要或知识库

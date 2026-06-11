# Research Management MVP

当前仓库已经进入 feature-freeze / interview-polish 收敛状态。已落地的是一个本地优先的 Research Management Assistant MVP：`FastAPI + LangGraph + SQLite` 后端、Vue 3 + Vite Research Workbench、deterministic Idea Assistant MVP、以及 review-gated Memory System MVP。

本文档只同步已经完成的事实。默认路径保持 deterministic/offline，不依赖 DeepSeek、OpenAI、BGE-M3、Chroma、arXiv、OpenAlex 或外网；这些真实 provider / 外部源路径都是显式配置后的 optional smoke。`Advanced-lite` 目前是 deterministic query rewrite，不是真实 LLM / RAG research agent。

## Interview Snapshot

Implemented and demo-ready:

- Research Workbench frontend: unified `/research/query` UI, discovery/knowledge split view, saved candidate lifecycle, PDF upload/embed controls, and Idea Assistant panel.
- Backend MVP endpoints: paper discovery, accept/upload/embed lifecycle, retrieval, grounded answer, unified research query, structured experiment logs, Idea Assistant, and Memory System review APIs.
- Agent Workflow entrypoint: `POST /research/assistant` uses a LangGraph thin orchestration layer to route between `basic_explore`, `advanced_ready`, `advanced_search`, and `research_idea`, while reusing existing discovery, knowledge, memory, and idea services.
- Idea Assistant MVP: structured experiment log in, retrieval-backed evidence lookup, deterministic 3-5 idea options out.
- Memory System MVP: structured logs as episodic evidence, deterministic `semantic_proposal` candidates, user accept/reject review, confirmed semantic memory, and explicit archive.

Default deterministic boundaries:

- `PAPER_JUDGE_PROVIDER=mock`
- `EMBEDDING_PROVIDER=fake`
- `VECTOR_BACKEND=fake`
- `ANSWER_PROVIDER=deterministic`
- `IDEA_PROVIDER=deterministic`

Optional real providers:

- `PAPER_JUDGE_PROVIDER=deepseek` for manual paper-judge smoke.
- `ANSWER_PROVIDER=openai` or `ANSWER_PROVIDER=deepseek` for manual grounded-answer smoke.
- `EMBEDDING_PROVIDER=bge-m3` plus `VECTOR_BACKEND=chroma` for local real embedding/vector smoke.
- arXiv/OpenAlex discovery paths are live external integrations and can be affected by network, API, and rate-limit behavior.

## Current Scope

目前已经完成：

- FastAPI 入口在 [backend/src/main.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/main.py)
- SQLite 持久化在 [backend/src/services/memory_store.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/services/memory_store.py)
- PDF upload + Phase 2C text extraction/chunking 在 [backend/src/services/knowledge_base.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/services/knowledge_base.py)
- 基础 graph flow 在 [backend/src/graph/builder.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/graph/builder.py) 和 [backend/src/graph/nodes.py](/Users/nuonuohu/Developer/graphReconstruction/backend/src/graph/nodes.py)
- Vue 3 + Vite Research Workbench 在 [frontend/src/components/ResearchWorkbench.vue](/Users/nuonuohu/Developer/graphReconstruction/frontend/src/components/ResearchWorkbench.vue)
- Idea Assistant panel 在 [frontend/src/components/IdeaAssistantPanel.vue](/Users/nuonuohu/Developer/graphReconstruction/frontend/src/components/IdeaAssistantPanel.vue)
- API tests、graph tests、store tests 已覆盖当前 MVP 主路径

## Implemented Endpoints

当前可用接口：

- `GET /health`
  返回 `{"status": "ok"}`
- `POST /search`
  输入 `{"mode":"basic"|"advanced","query":"..."}`
  调用 paper discovery graph，返回 ranked candidates；discovery results 默认不写入 SQLite
- `GET /papers/candidates`
  从 SQLite 读取候选论文
- `POST /papers/{paper_id}/accept`
  Discovery 主路径下接收 `paper` 和可选 `judgement` payload，首次把 paper 保存到 SQLite 并标记为 `accepted`；如果 paper 已存在，也兼容无 body 的状态更新路径
- `POST /papers/{paper_id}/upload_pdf`
  接收 multipart PDF 文件，保存到本地 upload 目录，把论文状态更新为 `uploaded`，并记录 `pdf_path`
- `POST /papers/{paper_id}/embed`
  当前是 phase-aware 路由：`uploaded` 论文执行本地 PDF 文本抽取和 chunk 持久化并进入 `chunked`；`chunked` 论文执行 embedding pipeline 并在所有 chunk 获得非空 `vector_ref` 后进入 `embedded`
- `POST /logs`
  写入实验日志
- `GET /logs`
  读取实验日志
- `POST /experiments/logs`
  写入结构化实验日志，供 Idea Assistant MVP 使用
- `GET /experiments/logs`
  读取结构化实验日志
- `GET /memory/candidates`
  列出待 review 的长期记忆候选，默认只返回 `pending`
- `POST /memory/candidates/refresh`
  基于结构化实验日志的 deterministic 规则刷新 `semantic_proposal` 候选；不会直接写入 confirmed memory
- `POST /memory/candidates/{candidate_id}/accept`
  用户确认候选后写入 `semantic_memory`，状态为 `confirmed`
- `POST /memory/candidates/{candidate_id}/reject`
  用户拒绝候选，候选标记为 `rejected`，不会写入 `semantic_memory`
- `GET /memory/semantic`
  列出 confirmed semantic memory，支持按 status/category/predicate 过滤
- `POST /memory/semantic/{memory_id}/archive`
  用户显式归档一条 semantic memory；系统不会仅凭时间自动归档
- `GET /memory/summary`
  返回 `candidate_count`、`known_dois`、`recent_logs`
- `POST /knowledge/search`
  输入 `{"query":"...","top_k":5}`，对已 `embedded` 的知识块执行 retrieval MVP，返回 chunk / paper 信息；当前只做召回，不做 RAG answer generation 或 LLM 总结
- `POST /knowledge/answer`
  输入 `{"question":"...","top_k":5}`，基于 retrieval 结果返回 grounded answer MVP；当前默认使用 deterministic fake answer generator，不调用真实 LLM
- `POST /ideas/recommend`
  输入一条结构化实验日志，构造 retrieval query，检索本地已 `embedded` 的知识块，并返回 3-5 条结构化 idea options；默认 deterministic/offline，不默认调用真实 provider 或外部 discovery
- `POST /research/query`
  输入 `{"query":"...","mode":"basic"|"advanced","include_discovery":true,"include_knowledge":true,"top_k":5}`，把外部 discovery 和内部 knowledge answer 编排到一个响应中；`discovery.candidates` 不是 grounded answer sources，`knowledge.sources` 只来自已 `embedded` 的知识块
- `POST /research/assistant`
  输入 `query` 和可选 `intent`、`experiment_log`、`top_k`、`idea_count`、`save_log`、`include_discovery`，经过 LangGraph assistant workflow 路由后返回 `mode`、`route`、`coverage_score`、`assistant_message`、`next_action`、`discovery`、`knowledge`、`ideas`、`errors`

## Persistence

当前 SQLite store 负责：

- 初始化本地数据库表
- 保存 candidate paper
- 保存 judge result
- 查询 candidate papers
- 更新 paper 状态
- 保存和查询 legacy/simple `experiment_logs`
- 保存和查询结构化 `experiment_log_entries`
- 保存、查询、review `memory_candidates`
- 保存、查询、归档 `semantic_memory`
- 查询 known DOI
- 保存、查询、删除 `knowledge_chunks`

当前表：

- `papers`
- `paper_judgements`
- `experiment_logs`
- `experiment_log_entries`
- `memory_candidates`
- `semantic_memory`
- `knowledge_chunks`

## Memory System MVP

后端现在有一个 lightweight / deterministic 的 Memory System MVP：

- `experiment_log_entries` 是 episodic memory 主证据层。
- `memory_candidates` 是系统自动提议但需要用户确认的 review buffer。
- `semantic_memory` 是用户确认后的长期事实层，默认只有 `confirmed` 进入使用路径。
- `MemoryStore.build_memory_context()` 组装 `confirmed semantic memory + 最近 3 条 structured experiment logs`。
- `/search` advanced query rewrite 通过 graph node 读取这个 `memory_context`。
- `/ideas/recommend` 的 retrieval query 会附加 compact memory context，但仍以当前新提交的 structured log 为最强上下文。

当前 candidate extraction 是 deterministic/offline：

- object 会做小写、去首尾空格、连字符/空格归一、多空格压缩。
- 同一 `category + subject + predicate + normalized object` 全局累计出现 3 次后，才生成 `semantic_proposal`。
- `refresh` 只生成或更新 pending candidate，不会直接创建 confirmed semantic memory。

当前 stale/conflict 边界：

- stale/conflict 在 MVP 中是 review-gated contract，不是自动事实修改器。
- confirmed semantic memory 不会因为时间流逝或一次 refresh 自动变成 archived。
- 归档必须通过 `POST /memory/semantic/{memory_id}/archive` 显式触发。
- 当前没有把 memory 写入 Chroma，也没有做 graph/vector memory retrieval。

## Idea Assistant MVP

后端现在已经支持一个 deterministic 的 Idea Assistant MVP：

- `POST /experiments/logs` 保存结构化实验日志
- `GET /experiments/logs` 列出结构化实验日志
- `POST /ideas/recommend` 基于单条结构化日志构造 retrieval query，检索本地已 `embedded` 的知识块，并返回 3-5 条结构化 idea options

默认行为保持 deterministic 和 offline。默认测试路径不会真实调用 DeepSeek、OpenAI、BGE-M3、Chroma、arXiv 或 OpenAlex；这些真实 provider / 外部源路径如果将来需要启用，应走显式配置和单独的手动 smoke。

Idea 的 `supporting_evidence` 只能来自 retrieval / discovery 返回对象，generator 不应编造 papers、chunks、citations 或 source details。

`known DOI` 规则当前是：

- 只返回状态为 `uploaded`、`chunked` 或 `embedded` 的 DOI
- `candidate` 状态不会进入强去重集合

## Paper Lifecycle

当前 `paper` 生命周期不应理解为强制线性流程，而应理解为“推荐路径 + 当前允许的可选路径”。

Discovery entry 推荐路径：

`discovery candidate -> accepted -> upload_pdf -> uploaded -> embed -> chunked -> embed -> embedded`

Future manual entry 预留语义：

`manual PDF upload -> uploaded -> chunked -> embedded`

当前代码允许的已实现路径还包括：

- `accepted -> upload_pdf -> uploaded`

各状态含义：

- `discovery candidate` = `/search` 或 `/research/query` 返回的临时检索结果，默认不写入 SQLite
- `accepted` = 用户点击 `Accept` 后保存到 SQLite 的论文，还没有上传 PDF
- `uploaded` = PDF 已保存到本地 upload 目录，`pdf_path` 已记录，DOI 会进入强去重集合
- `chunked` = PDF 文本抽取成功，chunks 已持久化到 `knowledge_chunks`；这仍然不是“真实 embedding 完成”
- `embedded` = embedding pipeline 已完成，且所有目标 chunk 都有可追踪的非空 `vector_ref`

## Knowledge-Base Stub

当前 knowledge-base 已进入 Phase 2C，但这里的状态流是“当前实现允许的路径”，不是强制要求所有 paper 都先经过 `accepted`。

推荐使用路径：

`discovery candidate -> accepted -> upload_pdf -> uploaded -> embed -> chunked -> embed -> embedded`

未来可能新增但当前尚未实现的新入口语义：

`manual PDF upload -> uploaded -> chunked -> embedded`

当前实际行为：

- `upload_pdf` 只要求 paper 已存在于 SQLite，不要求当前状态必须是 `accepted`
- PDF bytes 会保存到本地 upload 目录
- 文件名会做基础安全归一化
- `upload_pdf` 会把 `papers.status` 更新为 `uploaded`
- `upload_pdf` 会记录本地 `pdf_path`
- 因此当前支持 `accepted -> upload_pdf -> uploaded`
- `embed` 对 `uploaded` 论文执行 Phase 2C：本地 PDF 文本抽取和 chunk persistence；失败时保持 `uploaded`
- `embed` 对 `chunked` 论文执行 embedding pipeline；只有全部目标 chunk 拿到非空 `vector_ref` 才会进入 `embedded`
- `embed` 在 Phase 2D 重跑时会替换旧 `vector_ref`，失败时保持 `chunked`
- uploaded paper 的 DOI 会进入 `MemoryStore.list_known_dois()`
- chunked paper 继续保留同一个 `pdf_path`

当前代码已预留但不是默认配置：

- `EMBEDDING_PROVIDER=bge-m3` 时，可选真实 BGE-M3 provider 会参与 Phase 2D embedding
- `VECTOR_BACKEND=chroma` 时，可选真实 Chroma adapter 会把向量写入本地 persist dir

当前还没有做：

- 生产级 RAG answer generation
- `/search` 与 Chroma retrieval 的联动
- PDF 内容和 paper metadata 的一致性校验
- OCR
- 复杂版式恢复

## Search Flow

当前 `/search` 走的是同步后端链路：

`request -> rewrite_query -> multi_source_search -> dedup_papers -> judge_papers -> rank_papers`

当前 graph 行为：

- `basic` 模式下 query rewrite 返回原 query
- `advanced` 模式下 query rewrite 是 deterministic placeholder，不是真实 LLM / RAG agent
- dedup 会结合 `MemoryStore.list_known_dois()` 和当前 batch 的 title 弱去重
- `PAPER_JUDGE_PROVIDER=mock` 是默认离线路径，`PAPER_JUDGE_PROVIDER=deepseek` 是显式开启的可选真实 judge provider
- LLM judge 只输出 `decision`、`reason`、`tags`、`llm_relevance_score`、`quality_score`
- `embedding_relevance_score` 和 `novelty_score` 由本地规则函数计算，`final_score` 由 `ScoreUtils` 按固定权重 `0.40 / 0.15 / 0.25 / 0.20` 合成
- 单篇 judge 失败时会降级为 `judge_failed` 的 fallback result，不会阻止其他 candidates 返回
- 排序后只返回 discovery candidates，不会自动持久化到 SQLite
- endpoint 级真实 smoke 可能受 arXiv / OpenAlex 搜索超时影响；当前更稳定的验收方式是直连 paper judge provider smoke

当前 Advanced-lite placeholder 规则：

- 从 `confirmed semantic memory + 最近 3 条 structured experiment logs` 构造 `memory_context`
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
- `discovery` 只表示 current query results，只有点击 `Accept` 后才会进入 SQLite saved lifecycle
- `discovery.candidates` 只表示推荐阅读候选，不等同于 grounded answer sources
- `knowledge.sources` 只表示已 `embedded` 本地知识库证据
- candidates 面板支持调用：
  - `GET /papers/candidates`
  - `POST /papers/{paper_id}/accept`
  - `POST /papers/{paper_id}/upload_pdf`
  - `POST /papers/{paper_id}/embed`
- Idea Assistant panel 支持提交结构化实验日志并调用 `POST /ideas/recommend`

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

运行默认离线 smoke：

```bash
bash backend/scripts/smoke_offline_mvp.sh
```

该 smoke 使用临时 SQLite 和 in-process FastAPI HTTP requests，覆盖 `GET /health`、`POST /experiments/logs`、`POST /memory/candidates/refresh`、`POST /ideas/recommend`，并额外证明 Idea Assistant 的 `supporting_evidence` 可以来自已 `embedded` 的 retrieval chunk。

## Interview Demo Script

推荐面试演示顺序：

1. 启动后端：

```bash
PYTHONPATH=backend/src ./.venv/bin/uvicorn main:app --app-dir backend/src --port 8000
```

2. 启动前端：

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

3. 打开 Research Workbench，提交一个 query，说明 `/research/query` 把 discovery 和 knowledge 拆成两个独立 section。
4. 在 discovery 中 accept 一个 candidate，说明 discovery result 默认不入库，只有用户确认后进入 SQLite lifecycle。
5. 对 saved candidate 上传 PDF，然后调用 embed/advance，说明推荐路径是 `accepted -> uploaded -> chunked -> embedded`。
6. 用 Idea Assistant 提交 structured experiment log，说明 ideas 默认 deterministic，sources 只能来自 retrieval/discovery 返回对象。
7. 用后端 smoke 或 curl 演示 memory candidate review：先写入多条 structured logs，再 `POST /memory/candidates/refresh`，然后 accept/reject candidate。
8. 讲清楚 optional provider 边界：真实 DeepSeek/OpenAI/BGE-M3/Chroma 都是显式配置后的手动 smoke，不属于默认 demo 依赖。

## Current Limitations

当前明确还没有完成：

- 真实的 LLM / RAG query planning agent
- 外网依赖下的稳定 search 集成测试
- 完整 RAG 查询链路，以及 `/search` 到 retrieval 的联动
- 生产级前端界面
- 数据库迁移机制
- stale/conflict 自动判断和自动处理；当前只保留 review-gated future-work contract
- `/research/assistant` does not implement multi-turn checkpointing, SSE trace streaming, MCP integration, or automatic stale/conflict memory handling.
- Memory 写入 Chroma 或 graph/vector memory retrieval
- 多轮 chat memory、streaming / SSE、生产级评测闭环

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
- Advanced-lite 目前只消费 confirmed semantic memory 和最近 3 条 structured experiment logs，不读取历史对话、论文摘要或知识库

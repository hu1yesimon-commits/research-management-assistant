# 长期科研管理助手 MVP 设计

日期：2026-06-07

## 1. 项目愿景

本项目目标是搭建一个长期科研管理助手，帮助用户持续完成文献发现、实验日志管理、科研方向整理、论文知识库沉淀和后续 idea 探索。

系统不是一次性问答工具，而是围绕用户长期科研过程形成记忆：

- 用户对话会沉淀为科研偏好、研究问题和阶段性目标。
- 实验日志会沉淀为 block、失败尝试、有效设置和可继续探索的问题。
- 已阅读论文会沉淀为可复用的背景知识、方法线索和优化方向。
- 新检索论文会经过去重、质量评估和人工确认，再进入知识库。

LangGraph 的作用是把这些步骤组织为可追踪、可暂停、可人工确认的工作流。后续可以逐步加入 human-in-loop，让用户在关键节点参与判断，例如确认搜索方向、筛选候选论文、决定是否上传 PDF 入库。

## 2. MVP 边界

第一阶段目标是跑通最小闭环：

用户输入 query 或选择 Advanced-lite 生成 query，系统检索 arXiv 和 OpenAlex，去重后用 LLM Judge 给候选论文打分排序，用户根据 title、doi 或 pdf_url 手动选择论文并上传 PDF，后端将 PDF 向量化并写入本地知识库。

MVP 包含：

- Basic 模式：根据用户 query 直接探索可用高质量文献。
- Advanced-lite 模式：根据历史对话、实验日志、已读论文摘要和后续知识库上下文，识别用户当前研究中的 block、失败尝试和待解决痛点，生成 2-5 个可探索方向和搜索 query。
- 论文检索：优先使用 arXiv，使用 OpenAlex 补全 DOI、引用量、venue、openalex_id 等信息。
- 论文去重：只根据已确认入库论文的 DOI 去重，不把“检索到但未确认”的论文提前登记为已知论文。
- 论文评估：LLM Judge 输出多维分数和 final_score。
- 论文候选池：保存检索到且经过评估的候选论文，供用户后续确认。
- PDF 入库：用户手动上传 PDF，并绑定论文 title、doi 或 paper_id。
- 长期记忆：保存用户对话、实验日志、已读论文、候选论文、已入库论文。
- 简单 Vue 前端：支持检索、查看候选论文、上传 PDF、写实验日志。

MVP 暂不包含：

- SSE 流式进度展示。
- 完整异步任务队列。
- 复杂多智能体科研规划。
- 自动下载 PDF。
- 精细权限、多用户协作和部署级认证。
- 完整论文全文问答体验。

SSE 可以在 MVP 跑通后作为第二阶段增强，用来展示 LangGraph 节点进度，例如正在改写 query、正在检索、正在评估、等待用户确认、正在入库。

## 3. 推荐架构

项目按后端、前端和本地数据层组织。

后端使用 FastAPI，负责 API 入口、文件上传、数据库读写和 LangGraph 调用。

LangGraph 负责科研工作流编排，第一阶段只承载文献发现和候选论文评估流程。

服务层保留现有 `services` 方向：

- `paper_search`：统一调用 arXiv、OpenAlex 等多源检索工具。
- `normalizer`：把不同来源结果整理成统一的 `PaperMetadata`。
- `deduplicator`：根据已入库 DOI 过滤重复论文。
- `LLMJudge`：对论文进行相关性、质量、新颖性和最终分数评估。
- `memory_store`：保存用户对话、实验日志、论文状态和知识库索引。
- `knowledge_base`：负责 PDF 文本抽取、切块、embedding 和向量库写入。

前端使用 Vue，第一版只需要工作台式界面，不做复杂视觉设计：

- 检索页：选择 Basic 或 Advanced-lite，输入 query，展示候选论文。
- 文献页：查看候选论文，按 title、doi 或 paper_id 上传 PDF 入库。
- 日志页：记录实验日志，查看历史日志。

本地数据层建议：

- SQLite：保存结构化长期记忆和论文状态。
- Chroma：作为当前项目结论，保存 PDF 切块向量；后续如有规模或部署约束变化，再评估是否迁移。
- 本地文件目录：保存用户上传的 PDF 原文件。

## 4. LangGraph MVP 流程

第一阶段建议使用一个主图：`paper_discovery_graph`。

状态字段建议包含：

- `mode`：`basic` 或 `advanced`
- `user_query`：用户原始查询
- `rewritten_queries`：Advanced-lite 生成的搜索 query
- `raw_results`：多源检索原始结果
- `normalized_papers`：标准化论文列表
- `deduped_papers`：去重后的新论文
- `judge_results`：LLM Judge 评估结果
- `ranked_candidates`：排序后的候选论文
- `memory_context`：从历史对话、实验日志、已读论文提取的上下文

节点顺序：

1. `load_memory_context`
   - Basic 模式可跳过或只加载少量用户偏好。
   - Advanced-lite 模式读取历史对话、实验日志、已读论文摘要。

2. `rewrite_query`
   - Basic 模式直接使用 `user_query`。
   - Advanced-lite 模式用 Query Rewriter 生成可检索方向。目标形态是由智能体综合实验日志中的关键 block、历史对话、已读论文摘要和知识库中相似问题的处理方法，先给出解决痛点的方向建议，再生成更适合检索的 query，例如轻量化、可解释性、模块结合、损失函数改造、数据增强等。
   - MVP 早期可以先使用 deterministic rewriter 作为可测试占位：根据日志和上下文中的稳定关键词生成 query，例如 `heavy`、`light`、`轻量` 映射到 lightweight，`interpret`、`可解释` 映射到 interpretability。这个规则层不是最终智能能力，而是为了在没有真实 LLM、没有完整知识库时先验证工作流、API 和测试边界。

3. `multi_source_search`
   - 使用 arXiv 检索。
   - 使用 OpenAlex 补全 DOI、引用数、venue 等信息。

4. `dedup_papers`
   - 查询已入库 DOI。
   - 过滤重复论文。
   - 不在此步骤登记新 DOI。

5. `judge_papers`
   - 使用 LLM Judge 或先用 mock 规则返回结构化评分。
   - 输出 `llm_relevance_score`、`embedding_relevance_score`、`quality_score`、`novelty_score`、`final_score`、`reason` 和 `tags`。

6. `rank_papers`
   - 按 `final_score` 排序。
   - 保存前若干候选论文。

7. `persist_candidates`
   - 把候选论文保存到 SQLite。
   - 状态为 `candidate`，等待用户确认或上传 PDF。

### Advanced-lite Query Rewriter 设计边界

Advanced-lite 的最终目标不是简单关键词扩展，而是一个面向科研过程的 query planning agent。它会读取用户最近的实验日志、历史对话、已读论文摘要和知识库中相似问题的处理方法，识别当前研究最需要解决的 block 或待验证 idea，并把这些痛点转化为可检索的论文方向。

第一阶段实现时，可以先保留一个 deterministic rewriter 作为稳定占位。它只负责把少量明确关键词映射成检索方向，用于验证 `memory_context -> rewritten_queries -> search -> judge -> rank` 这条链路是否稳定。后续接入真实 LLM Rewriter 时，应保持相同输入输出契约：输入仍是 `mode`、`user_query` 和 `memory_context`，输出仍是 2-5 个搜索 query。这样可以替换内部智能实现，而不破坏 FastAPI、LangGraph 和测试结构。

## 5. Human-in-loop 设计

MVP 阶段的人机协同先保持简单：

- 用户手动选择候选论文是否值得读。
- 用户手动上传 PDF。
- 用户写实验日志时，可以人工标记 block、idea、done、question。

后续增强时再把 human-in-loop 接入 LangGraph：

- query 改写后暂停，等待用户确认搜索方向。
- LLM Judge 后暂停，等待用户确认候选论文。
- PDF 入库前暂停，等待用户确认 DOI/title 是否匹配。
- Advanced 科研规划时暂停，等待用户选择要深入的 idea。

## 6. 数据持久化设计

SQLite 表建议先保持少量核心表：

- `conversations`
  - 保存用户和助手的历史对话。

- `experiment_logs`
  - 保存实验日志、block、阶段性结论和下一步问题。

- `papers`
  - 保存论文 metadata。
  - 字段包含 `paper_id`、`title`、`doi`、`source`、`abstract`、`citation_count`、`venue`、`pdf_path`、`status`。
  - `status` 可为 `candidate`、`accepted`、`uploaded`、`chunked`、`embedded`、`rejected`。

- `paper_judgements`
  - 保存 LLM Judge 的评分和理由。

- `knowledge_chunks`
  - 保存 PDF 切块和向量库中的 chunk id 映射。

去重原则：

- `candidate` 状态不代表已入库。
- 只有 `uploaded`、`chunked` 或 `embedded` 状态的论文 DOI 才进入强去重集合。
- DOI 需要统一小写、去空格，并去除 `https://doi.org/` 前缀。
- 没有 DOI 的论文可以用 title 归一化做弱去重，但不能阻止用户手动入库。

## 7. API MVP

FastAPI 第一阶段接口建议：

- `POST /search`
  - 输入：`mode`、`query`
  - 输出：排序后的候选论文列表

- `GET /papers/candidates`
  - 输出：历史候选论文

- `POST /papers/{paper_id}/accept`
  - 作用：把候选论文标记为用户认可，等待 PDF 上传

- `POST /papers/{paper_id}/upload_pdf`
  - 输入：PDF 文件
  - 输出：入库状态

- `POST /logs`
  - 输入：实验日志文本和可选标签
  - 输出：保存结果

- `GET /logs`
  - 输出：历史实验日志

- `GET /memory/summary`
  - 输出：用户当前科研记忆摘要，供调试和前端展示

## 8. Vue MVP

前端优先实现工作流，不追求复杂交互。

页面一：检索工作台

- 模式选择：Basic / Advanced-lite。
- Query 输入框。
- 检索按钮。
- 候选论文表格：title、authors、year、venue、citation_count、final_score、reason、doi、pdf_url。
- 操作按钮：接受、拒绝、上传 PDF。

页面二：实验日志

- 日志输入框。
- 标签选择：block、idea、done、question。
- 保存按钮。
- 历史日志列表。

页面三：知识库

- 已上传论文列表。
- 入库状态：uploaded / chunked / embedded。
- 后续可扩展为论文问答入口。

## 9. 实现顺序

第一步：修正后端可运行骨架。

- 让 `backend/src/main.py` 成为真正的 FastAPI 入口。
- 让 `graph/builder.py`、`graph/nodes.py`、`graph/state.py` 名称一致。
- 保证一次 Basic 搜索可以从 API 跑到候选论文返回。

第二步：加入 SQLite 持久化。

- 保存 query、候选论文、评估结果、实验日志。
- 把去重逻辑改为读取已确认入库论文 DOI。

第三步：跑通 Basic LangGraph。

- `search -> dedup -> judge -> rank -> persist_candidates`
- 先允许 LLM Judge 使用 mock 分数，避免模型调用阻塞主流程。

第四步：加入 Advanced-lite。

- 从实验日志、历史对话、已读论文摘要中整理上下文。
- 用 LLM Rewriter 生成搜索方向和搜索 query。
- 复用 Basic 的后续检索和排序流程。

第五步：加入 PDF 上传和知识库分阶段处理。

- 用户上传 PDF。
- 后端保存文件。
- Phase 2C: 抽取文本、切块、持久化 `knowledge_chunks`，更新论文状态为 `chunked`。
- Phase 2D: 再做真实 embedding 和向量库写入。
- 只有真实 embedding 完成后才更新论文状态为 `embedded`。

第六步：实现 Vue 简单前端。

- 检索工作台。
- 实验日志页。
- 知识库页。

第七步：MVP 验证。

- 输入一个 query 能返回候选论文。
- 候选论文能被保存。
- 已入库 DOI 不会重复出现。
- 能写实验日志。
- 能上传 PDF 并完成 `uploaded -> chunked` 的文本抽取与切块持久化。

第八步：MVP 后增强 SSE。

- FastAPI 增加 SSE 端点。
- LangGraph 节点执行时输出进度事件。
- 前端展示实时状态。

## 10. 后续扩展路线

MVP 跑通后再逐步扩展：

1. SSE 进度流
   - 展示长任务状态，降低用户等待焦虑。

2. 完整 Advanced 模式
   - 从实验日志 block 和已读文献中总结可探索 idea。
   - 自动生成搜索范式和 query 组合。
   - 对方向进行可行性、创新性和资源成本评估。

3. 论文全文理解
   - 对已入库论文做结构化总结。
   - 提取方法、实验设置、数据集、指标、局限和可复用模块。

4. 科研路线推荐
   - 结合用户历史实验和论文知识库，推荐下一步实验。
   - 输出轻量化、可解释性、模块组合、训练策略、数据策略等方向。

5. 更强 human-in-loop
   - 在关键节点暂停工作流。
   - 用户确认后继续执行。
   - 支持回滚、重试和分支探索。

6. 多源扩展
   - Semantic Scholar、Crossref、PubMed、Google Scholar 替代源。
   - 根据领域动态选择检索源。

7. 远程推理与双机协同
   - MacBook 负责调度和前端。
   - GPU 节点负责 embedding、本地模型推理和批处理任务。

## 11. 当前工程判断

当前最重要的不是完善所有智能体，而是先跑通一个可用闭环：

`query -> candidate papers -> judge/rank -> user accepts -> PDF upload -> vector DB -> memory persisted`

只要这个闭环成立，后面的 Advanced、SSE、科研路线推荐、多智能体协作都可以自然接上。反过来，如果第一阶段就同时做完整长期记忆、完整多智能体规划和 SSE，很容易让项目卡在架构复杂度里。

因此第一阶段应坚持：

- REST 优先，SSE 后置。
- Basic 先完整，Advanced 先轻量。
- 用户手动上传 PDF，自动下载后置。
- SQLite 和本地向量库优先，复杂部署后置。
- mock LLM Judge 可接受，先保证流程闭环。

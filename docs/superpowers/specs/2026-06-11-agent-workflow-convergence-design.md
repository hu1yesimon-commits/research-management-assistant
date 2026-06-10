# Agent Workflow 收敛设计

日期：2026-06-11

> 本文档是 Research Management Assistant 的 Agent Workflow 收敛设计说明，不表示功能已经实现。后续实现应以本文档为范围边界，并继续保持默认离线、可解释、可测试、可降级。

## 1. 当前理解

当前项目已经具备几条相对独立但可复用的能力线：

- `discovery`
  - 通过 LangGraph `paper_discovery_graph` 执行 memory context 读取、query rewrite、多源搜索、去重、paper judge 和 rank。
- `knowledge`
  - 通过本地已 `embedded` 的 knowledge chunks 执行 retrieval 和 grounded answer。
- `memory`
  - 通过结构化实验日志承载 episodic memory。
  - 通过 `memory_candidates` 和 `semantic_memory` 承载 review-gated long-term memory。
  - 通过 `MemoryStore.build_memory_context()` 输出 confirmed semantic memory 和 recent episodic memory。
- `idea`
  - 通过用户提交的结构化实验日志触发 Idea Assistant，结合 retrieval evidence 生成 idea options。
- `/research/query`
  - 当前是 discovery + knowledge 的薄服务编排入口，保持 partial failure，不应膨胀成 full planner。

本阶段目标不是新增一个不可控的 autonomous agent，也不是把所有 service 推翻重写成大图。

本阶段目标是新增一个 **LangGraph 主图薄编排层**，把现有能力收敛成一个可讲、可测、可扩展的 Research Assistant Agent Workflow：

```text
user request
  -> load memory context
  -> assess query coverage
  -> route by mode / intent
  -> run selected workflow node
  -> format assistant response
```

主图负责 State 和 route，节点内部复用现有 service / sub-workflow。

## 2. Goals And Non-Goals

### 2.1 Goals

- 新增一个清晰的 Agent Workflow 后端入口：`POST /research/assistant`。
- 保留 `/research/query` 当前薄编排语义，避免破坏既有前端、测试和 demo 路径。
- 使用 LangGraph 主图管理：
  - query
  - optional experiment log
  - memory context
  - coverage score
  - mode
  - route
  - discovery output
  - knowledge output
  - idea output
  - assistant message
  - next action
  - errors
- 第一版返回对话友好的后端结构，为后续前端重构成问答式 Research Workbench 做准备。
- 第一版不做真正多轮 interrupt / checkpoint，只返回 `next_action`，由下一次请求继续 workflow。
- 第一版 coverage 使用 deterministic heuristic，不让 LLM 主观评分直接控制 route。
- 后续版本允许引入 LLM coverage judge，但只能作为辅助信号，建议权重约 `0.3`。
- 节点复用现有能力，不复制 discovery、knowledge、idea 的内部实现。

### 2.2 Non-Goals

- 不在本阶段重构前端。
- 不把 `/research/query` 改成 Agent Workflow 总入口。
- 不实现 SSE、streaming node trace、LangGraph checkpoint 或 interrupt。
- 不实现通用 chat memory。
- 不新增 MCP server。
- 不把 stale / conflict 自动处理纳入主路径。
- 不让 discovery candidates 自动写入 SQLite。
- 不让 knowledge answer 或 idea generator 编造 sources。
- 不把所有小步骤都拆成主图节点；主图节点可以是粗粒度 workflow node。

## 3. 推荐入口

新增：

- `POST /research/assistant`

理由：

- `/research/query` 当前是稳定的 discovery + knowledge 薄编排入口。
- Agent Workflow 会引入 `mode`、`route`、`coverage_score`、`route_reason`、`assistant_message`、`next_action`、`ideas` 等新语义。
- 如果复用 `/research/query`，旧接口会被迫承担两套语义，增加前端和测试改动。
- 新入口更适合作为面试和 demo 中的“LangGraph 主图入口”。

本阶段不删除、不替换 `/research/query`。

## 4. 主图设计

### 4.1 主图名称

推荐命名：

- `research_assistant_graph`

推荐构建函数：

- `build_research_assistant_graph(...)`

推荐服务包装：

- `ResearchAssistantWorkflowService`

服务层负责把 FastAPI request 转成 graph initial state，并把 graph result 转成 response schema。

### 4.2 主图节点

第一版推荐节点：

1. `load_memory_context`
   - 调用 `MemoryStore.build_memory_context()`。
   - 输出 `memory_context`。

2. `assess_query_coverage`
   - 使用 deterministic heuristic 评估当前 query 是否属于已探索领域。
   - 输出 `coverage_score` 和 `route_reason`。

3. `route_request`
   - 根据 request 中的 intent、是否包含 experiment log、coverage score 决定 `mode` 和 `route`。

4. `run_basic_explore`
   - 用于新领域探索。
   - 调用现有 discovery graph。
   - 调用 `KnowledgeQAService.answer()` 获取当前本地知识库回答。
   - 如果没有 sources，保留明确 no-source fallback。
   - 返回 top_k discovery candidates 和当前 knowledge section。
   - 输出鼓励用户筛选论文、上传 PDF、扩充本地知识库的 assistant message。

5. `run_advanced_ready`
   - 用于 coverage 足够但用户未明确 search 或 research intent 的情况。
   - 不强行执行多轮对话。
   - 返回 `next_action`，询问用户是否有新的实验日志，或是否只想基于现有知识继续搜索 / 问答。

6. `run_advanced_search`
   - 用于已有领域上的搜索和问答。
   - 基于 query + memory context 调用现有 discovery graph 和 knowledge answer。
   - 返回上下文增强后的论文推荐和本地知识库回答。

7. `run_research_idea`
   - 用于用户提交结构化实验日志的情况。
   - 调用现有 `IdeaRecommendationService`。
   - 返回 idea options、supporting evidence 和下一步建议。

8. `format_assistant_response`
   - 汇总 route、message、next action、各 section 输出和 errors。
   - 保证前端未来可以按统一结构渲染。

### 4.3 节点粒度原则

主图采用粗粒度节点：

- `run_basic_explore` 可以内部调用现有 `paper_discovery_graph`。
- `run_advanced_search` 可以内部调用 `KnowledgeQAService` 和 discovery graph。
- `run_research_idea` 可以内部调用 `IdeaRecommendationService`。

这样可以让主图体现 Agent Workflow 编排，同时避免复制和破坏已有 service 边界。

## 5. State 设计

第一版 state 建议只包含必要字段：

```python
class ResearchAssistantState(TypedDict):
    query: str
    intent: Literal["auto", "search", "research"]
    experiment_log: ExperimentLogRequest | None
    memory_context: str
    coverage_score: float
    mode: Literal["basic", "advanced"]
    route: Literal[
        "basic_explore",
        "advanced_ready",
        "advanced_search",
        "research_idea",
    ]
    route_reason: str
    discovery: dict
    knowledge: dict
    ideas: list[dict]
    assistant_message: str
    next_action: dict | None
    suggested_user_actions: list[str]
    errors: list[dict]
```

设计说明：

- `mode` 表示领域覆盖程度：
  - `basic`：新领域或本地覆盖不足。
  - `advanced`：已有 memory / knowledge 支撑。
- `route` 表示本次请求实际执行路径。
- `intent` 表示用户本次输入意图：
  - `auto`：由系统判断。
  - `search`：用户想基于已有知识继续搜索 / 问答。
  - `research`：用户提交结构化实验日志，希望生成 ideas。
- `next_action` 用来表达下一步交互，但不在第一版里实现多轮挂起。
- `errors` 用于局部失败隔离。

不建议使用 `status` 命名该字段，避免和 paper lifecycle 的 `candidate / accepted / uploaded / chunked / embedded` 混淆。

## 6. Routing 设计

第一版支持 4 条 route：

### 6.1 `basic_explore`

触发条件：

- `intent=auto`
- `coverage_score` 低于阈值

行为：

- 调用 discovery graph 获取 top_k discovery candidates。
- 调用 `KnowledgeQAService.answer()`；如果没有 sources，返回明确 no-source 信息。
- 返回 assistant message：
  - 说明当前更像新领域探索。
  - 已推荐 top_k 篇候选文献。
  - 建议用户筛选候选、上传 PDF、完成 embedding，以便后续获得更好的科研辅助。

### 6.2 `advanced_ready`

触发条件：

- `intent=auto`
- `coverage_score` 高于或等于阈值
- request 未包含结构化 experiment log，也未显式指定 search intent

行为：

- 不强行替用户继续规划。
- 返回 assistant message 和 `next_action`：
  - 是否有新的实验日志需要分析？
  - 如果没有，可以继续执行 search / question answering。

### 6.3 `advanced_search`

触发条件：

- `intent=search`
- 或 `intent=auto` 但后续请求明确用户不提交新实验，只希望继续搜索 / 问答

行为：

- 使用 memory context 增强 query rewrite。
- 调用 discovery graph。
- 调用 knowledge answer。
- 返回上下文相关的候选论文和本地知识库回答。

### 6.4 `research_idea`

触发条件：

- `intent=research`
- request 包含结构化 `experiment_log`

行为：

- 调用 Idea Assistant。
- 使用 experiment log + memory context + retrieval evidence。
- 返回 idea options。
- 返回下一步建议：用户可以选择某个 idea 继续搜索或规划后续实验。

### 6.5 暂不进入第一版的 route

暂不实现：

- `search_plus`

原因：

- `search_plus` 依赖用户选择某个 idea 之后继续搜索。
- 这会引入跨请求 working memory、选择状态和后续上下文管理。
- 第一版只通过 `next_action` 暗示该后续路径，不实现真实多轮状态。

## 7. Coverage Score 设计

第一版不使用 LLM 评分控制 route。

推荐 deterministic heuristic：

- `semantic_memory_overlap`
  - query 与 confirmed semantic memory 的关键词重合程度。
- `recent_log_overlap`
  - query 与最近 structured experiment logs 的关键词重合程度。
- `knowledge_source_signal`
  - 本地 knowledge retrieval 是否返回足够 sources。

示例权重：

```text
coverage_score =
  0.4 * semantic_memory_overlap
  + 0.3 * recent_log_overlap
  + 0.3 * knowledge_source_signal
```

推荐阈值：

```text
coverage_score >= 0.5 -> advanced
coverage_score < 0.5  -> basic
```

后续版本可以引入 LLM coverage judge：

```text
coverage_score =
  0.7 * deterministic_score
  + 0.3 * llm_coverage_score
```

LLM 评分只能作为辅助信号，不应单独覆盖 deterministic score。

## 8. API Contract 草案

### 8.1 Request

```json
{
  "query": "How should I improve graph reconstruction precision?",
  "intent": "auto",
  "experiment_log": null,
  "top_k": 5
}
```

`intent` 可选值：

- `auto`
- `search`
- `research`

当 `intent=research` 时，`experiment_log` 应包含与 `/ideas/recommend` 一致的结构化实验日志字段。

### 8.2 Response

```json
{
  "query": "How should I improve graph reconstruction precision?",
  "mode": "advanced",
  "route": "advanced_ready",
  "coverage_score": 0.72,
  "route_reason": "Confirmed memory and recent logs overlap with the query.",
  "assistant_message": "I found this query is related to your existing research context. Do you have a new experiment log to analyze, or should I continue with contextual search?",
  "next_action": {
    "type": "choose_intent",
    "options": ["research", "search"]
  },
  "suggested_user_actions": [
    "Submit a structured experiment log if you want idea recommendations.",
    "Continue with search if you want contextual paper recommendations and knowledge-base answers."
  ],
  "discovery": {
    "enabled": false,
    "candidates": [],
    "error": null
  },
  "knowledge": {
    "enabled": false,
    "answer": null,
    "sources": [],
    "error": null,
    "mode": null
  },
  "ideas": [],
  "errors": []
}
```

### 8.3 Error Semantics

- 空 query 返回 `400`。
- `intent=research` 但缺少 `experiment_log` 返回 `400`。
- 单个 section 失败时尽量写入 `errors` 并保留其他 section。
- 如果本次 route 的核心能力完全失败，可以返回 endpoint-level error。
- error message 不应泄露 API key 或 provider secrets。

## 9. 与现有能力的关系

### 9.1 `/research/query`

保持现状：

- discovery + knowledge 薄编排。
- discovery 和 knowledge section 彼此独立。
- 支持 partial failure。

不在本阶段替换为主图。

### 9.2 `paper_discovery_graph`

保持现状：

- 继续负责 query rewrite、search、dedup、judge、rank。
- 可作为 `research_assistant_graph` 的粗粒度节点内部依赖。

### 9.3 `KnowledgeQAService`

保持现状：

- 继续负责 retrieval + grounded answer。
- sources 只能来自已 `embedded` 的本地 knowledge chunks。

### 9.4 `IdeaRecommendationService`

保持现状：

- 继续负责 structure experiment log -> retrieval query -> evidence -> idea options。
- `research_assistant_graph` 的 `research_idea` route 复用它。

### 9.5 Memory System

保持现状：

- `confirmed semantic memory` 才能进入正式 memory context。
- `memory_candidates` 仍需用户 review。
- stale / conflict 自动处理不进入第一版。

## 10. 前端策略

第一版不改前端。

理由：

- 当前重点是后端 Agent Workflow 边界收敛。
- 新 response 已经包含对话型字段，可以为后续前端重构准备。
- 前端后续更适合整体改成问答式 Research Workbench，而不是为了第一版后端设计做临时 UI。

后续前端方向：

- 一个主要 query / conversation 输入区。
- 根据 `route` 渲染不同 section。
- 根据 `next_action` 提供明确按钮：
  - 提交结构化实验日志
  - 继续 search
  - 上传 PDF
  - 选择 idea 后继续探索

## 11. 测试与验证

第一版应至少覆盖：

- `POST /research/assistant` 空 query 返回 `400`。
- low coverage query 走 `basic_explore`。
- high coverage query 走 `advanced_ready`。
- `intent=search` 走 `advanced_search`。
- `intent=research` + structured experiment log 走 `research_idea`。
- `intent=research` 但缺少 experiment log 返回 `400`。
- discovery 失败时错误进入 `errors`，不泄露 secrets。
- knowledge 无 sources 时返回明确 no-source fallback，不编造 evidence。
- Idea route 的 supporting evidence 仍来自 retrieval / discovery，不由 generator 编造。
- 默认测试不依赖外网、真实 LLM、真实 Chroma 或真实 BGE-M3。

推荐验证命令继续使用当前后端测试模式：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests
```

如实现范围较小，可先跑相关 focused tests，再跑完整后端测试。

## 12. 面试叙事边界

可以这样表述：

> 我在原有 paper discovery graph、RAG、memory system 和 Idea Assistant 之上，新增了一个 LangGraph 主图薄编排层。主图不替代已有 service，而是用 State 管理 query、memory context、coverage score、route、results 和 next action。它通过 conditional edge 决定当前请求是新领域探索、已有领域搜索、等待用户提交实验日志，还是进入 idea recommendation。这样既保留了可测试的工程边界，也把项目从功能集合收敛成一个可解释的 Research Assistant Agent Workflow。

不能这样表述：

- 已经实现完整 autonomous multi-agent system。
- 已经实现多轮 memory checkpoint。
- 已经实现 stale / conflict 自动处理。
- 已经实现 MCP integration。
- 已经实现 production-grade agent platform。

## 13. 推荐实现顺序

1. 新增 schema：
   - `ResearchAssistantRequest`
   - `ResearchAssistantResponse`
   - `ResearchAssistantNextAction`
   - `ResearchAssistantError`
2. 新增 state：
   - `ResearchAssistantState`
3. 新增 coverage helper：
   - deterministic score
   - route reason
4. 新增 graph builder：
   - `build_research_assistant_graph`
5. 新增 workflow service：
   - `ResearchAssistantWorkflowService`
6. 新增 FastAPI endpoint：
   - `POST /research/assistant`
7. 新增 focused tests。
8. 更新 README / demo docs，仅声明已实现事实。

## 14. Implementation Plan 需要细化的点

当前已收敛的决定：

- 第一版采用新增 `/research/assistant`。
- 第一版采用后端总图 + 对话型返回。
- 第一版不改前端。
- 第一版不做真实多轮 interrupt / checkpoint。
- 第一版不实现 `search_plus`。
- 第一版 coverage 不接入 LLM 评分。

以下不是设计分歧，而是实现计划需要落到文件和测试的细节：

- deterministic overlap 的具体 tokenizer / normalize 规则。
- `advanced_search` 的 discovery 和 knowledge failure 是否完全沿用 `/research/query` 的 partial failure 语义。
- response schema 是否直接复用现有 `ResearchDiscoverySection` / `ResearchKnowledgeSection`，还是新增 assistant 专用 section schema。

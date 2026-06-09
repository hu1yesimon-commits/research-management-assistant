# Idea Assistant MVP 设计

日期：2026-06-09

> 本文档是 Idea Assistant MVP 的正式设计说明，不表示功能已经实现。后续实现应以本文档为范围边界，并继续保持默认离线、确定性、可测试。

## 1. 当前理解

本阶段目标是在现有 Research Management Assistant 之上，新增一个由用户主动提交结构化实验日志触发的 Idea Assistant MVP。

用户提交的实验日志不是普通聊天记忆，而是一条明确的实验问题记录，例如：

- `task`: defect classification
- `model`: 1D-CNN
- `dataset`: bearing fault dataset
- `metric_problem`: minority class PRAUC is low
- `tried_methods`: class weighting, focal loss
- `observation`: recall improves but precision collapses
- `goal`: improve PRAUC without making model too heavy

系统基于这条日志执行：

1. 将结构化日志保存到 SQLite。
2. 把日志转成 retrieval query，检索本地已 `embedded` 的 knowledge chunks。
3. 可选触发 external discovery，用于补充推荐阅读候选。
4. 生成 3-5 个 evidence-grounded idea options。
5. 每个 idea 给出可执行的下一小实验，但不进入 full execution planner。

本阶段仍保持现有核心原则：

- 默认 provider 走 deterministic/fake 路径。
- 默认测试不访问 DeepSeek、OpenAI、BGE-M3、Chroma 或外网。
- sources 永远来自 retrieval 或 discovery 结果，不由 LLM 编造。
- discovery candidates 仍是临时结果，不自动入库。
- idea recommendation 不是多轮 chat memory，也不是生产级 agent planner。

## 2. 修改计划

### 2.1 结构化实验日志

推荐新增实验日志专用入口：

- `POST /experiments/logs`
- `GET /experiments/logs`

保留现有 `/logs`：

- `/logs` 继续作为 legacy/simple notes，用于早期 experiment log 文本和 Advanced-lite memory context。
- `/experiments/logs` 承载结构化实验日志，服务 Idea Assistant。

这样可以避免把 `/logs` 改成多义接口，也避免破坏当前前端、README 和测试中已有的简单日志契约。

### 2.2 Idea Assistant API

推荐新增：

- `POST /ideas/recommend`

该 endpoint 是本阶段主入口。它接收一条结构化实验日志，可以选择是否保存日志、是否启用 external discovery，并返回结构化 ideas。

### 2.3 服务层

推荐新增服务：

- `ExperimentLogService` 或直接扩展 `MemoryStore` 的结构化日志方法。
- `IdeaRecommendationService`
- `IdeaGenerator` protocol
- `DeterministicIdeaGenerator`
- 可选 `LLMIdeaGenerator`
- `IdeaPromptBuilder`

`IdeaRecommendationService` 负责 workflow orchestration：

1. 校验并标准化实验日志。
2. 根据日志构造 retrieval query。
3. 调用 `KnowledgeRetrievalService.search()` 获取本地 evidence。
4. 可选调用 discovery graph 获取 external candidates。
5. 调用 `IdeaGenerator` 生成结构化 ideas。
6. 返回 ideas、knowledge sources、discovery candidates 和 mode。

### 2.4 实现优先级

推荐实现顺序：

1. schema 和 SQLite store。
2. deterministic idea generator。
3. `IdeaRecommendationService`。
4. `POST /ideas/recommend`。
5. README 和测试文档更新。
6. 可选前端小入口。

## 3. 风险与假设

### 3.1 风险

- 当前 `/logs` 只有 `content + tags`，强行扩展成结构化实验日志会污染既有语义。
- `KnowledgeQAService` 当前返回单个 grounded answer，不适合直接返回多个结构化 ideas。
- External discovery 依赖 arXiv/OpenAlex，真实路径可能受网络、限流、第三方响应影响。
- DeepSeek/OpenAI 输出结构化 JSON 需要额外解析和降级策略，不能进入默认测试路径。
- 如果 evidence 为空，系统仍然可以生成 deterministic fallback ideas，但必须标明 `supporting_evidence=[]`，不能假装有文献支持。

### 3.2 假设

- MVP 每次只处理一条结构化实验日志。
- MVP 返回一次性 recommendation，不保存多轮 chat state。
- MVP 的 idea 数量默认 3，允许 3-5。
- `top_k` 默认 5，范围继续与 knowledge retrieval 保持一致。
- SQLite 仍是唯一持久化层。
- 前端大改后置，后端 API contract 先稳定。

## 4. 诊断结果

当前仓库中已经具备可复用基础：

- FastAPI 入口在 `backend/src/main.py`。
- `POST /knowledge/search` 已通过 `KnowledgeRetrievalService` 检索已 `embedded` chunks。
- `POST /knowledge/answer` 已通过 `KnowledgeQAService` 返回 grounded answer。
- `POST /research/query` 已经把 discovery 和 knowledge 分成独立 section，并保留 partial failure。
- `MemoryStore` 已有 `experiment_logs` 和 `knowledge_chunks` 表。
- `AnswerGenerator` 已有 deterministic 和 LLM provider seam。
- DeepSeek 已按 OpenAI-compatible client 方式接入 answer provider。

当前不足：

- `/logs` 不是结构化实验日志。
- 没有 idea recommendation endpoint。
- 没有 idea-specific schema。
- 没有 idea-specific generator。
- 没有保存结构化 idea request/response 的专用表。
- 没有前端 Idea Assistant workflow。

结论：

- 复用 `KnowledgeRetrievalService` 是合适的。
- 复用 `KnowledgeQAService` 的整体 response 不合适。
- 复用 `AnswerGenerator` 的 provider seam 思路合适，但应新增 idea 专用 generator protocol。
- 保留 `/logs`，新增 `/experiments/logs`，再新增 `/ideas/recommend` 是推荐方案。

## 5. 推荐设计

### 5.1 Endpoint 设计

#### `POST /experiments/logs`

请求：

```json
{
  "task": "defect classification",
  "model": "1D-CNN",
  "dataset": "bearing fault dataset",
  "metric_problem": "minority class PRAUC is low",
  "tried_methods": ["class weighting", "focal loss"],
  "observation": "recall improves but precision collapses",
  "goal": "improve PRAUC without making model too heavy",
  "tags": ["imbalanced-learning", "lightweight"]
}
```

响应：

```json
{
  "id": 12,
  "created_at": "2026-06-09T10:20:30+00:00"
}
```

#### `GET /experiments/logs`

响应：

```json
[
  {
    "id": 12,
    "task": "defect classification",
    "model": "1D-CNN",
    "dataset": "bearing fault dataset",
    "metric_problem": "minority class PRAUC is low",
    "tried_methods": ["class weighting", "focal loss"],
    "observation": "recall improves but precision collapses",
    "goal": "improve PRAUC without making model too heavy",
    "tags": ["imbalanced-learning", "lightweight"],
    "created_at": "2026-06-09T10:20:30+00:00"
  }
]
```

#### `POST /ideas/recommend`

请求：

```json
{
  "experiment_log": {
    "task": "defect classification",
    "model": "1D-CNN",
    "dataset": "bearing fault dataset",
    "metric_problem": "minority class PRAUC is low",
    "tried_methods": ["class weighting", "focal loss"],
    "observation": "recall improves but precision collapses",
    "goal": "improve PRAUC without making model too heavy",
    "tags": ["imbalanced-learning", "lightweight"]
  },
  "save_log": true,
  "include_discovery": false,
  "top_k": 5,
  "idea_count": 3
}
```

响应：

```json
{
  "log_id": 12,
  "query": "defect classification 1D-CNN bearing fault dataset minority class PRAUC is low recall improves but precision collapses improve PRAUC without making model too heavy",
  "knowledge": {
    "sources": [
      {
        "paper_id": "paper-1",
        "title": "Paper title",
        "chunk_index": 0,
        "distance": 0.12,
        "text": "retrieved chunk text",
        "vector_ref": "chroma:research_chunks:paper-1:0:hash"
      }
    ],
    "error": null
  },
  "discovery": {
    "enabled": false,
    "candidates": [],
    "error": null
  },
  "ideas": [
    {
      "title": "Tune a precision-aware threshold after imbalance training",
      "rationale": "Use the retrieved evidence and the logged observation to separate representation learning from operating-point selection.",
      "supporting_evidence": [
        {
          "source_type": "knowledge",
          "paper_id": "paper-1",
          "title": "Paper title",
          "chunk_index": 0,
          "distance": 0.12,
          "text": "retrieved chunk text"
        }
      ],
      "expected_benefit": "May improve minority-class PRAUC while avoiding a heavier model.",
      "risk": "Threshold tuning may overfit if validation data is too small.",
      "suggested_validation_metric": "minority-class PRAUC with a precision floor",
      "next_small_experiment": "Run a fixed 1D-CNN checkpoint and sweep decision thresholds on the validation split."
    }
  ],
  "mode": "deterministic"
}
```

### 5.2 Schema 建议

新增 Pydantic schema：

- `ExperimentLogRequest`
- `ExperimentLogEntry`
- `ExperimentLogCreateResponse`
- `IdeaRecommendRequest`
- `IdeaSupportingEvidence`
- `IdeaOption`
- `IdeaKnowledgeSection`
- `IdeaDiscoverySection`
- `IdeaRecommendResponse`

字段约束：

- `task`、`model`、`dataset`、`metric_problem`、`observation`、`goal` 必须非空。
- `tried_methods` 默认空列表。
- `tags` 默认空列表。
- `top_k` 范围为 1-20。
- `idea_count` 范围为 3-5。

### 5.3 SQLite 设计

推荐新增表：

```sql
CREATE TABLE IF NOT EXISTS experiment_log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    model TEXT NOT NULL,
    dataset TEXT NOT NULL,
    metric_problem TEXT NOT NULL,
    tried_methods_json TEXT NOT NULL,
    observation TEXT NOT NULL,
    goal TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

本阶段不强制保存 idea responses。原因：

- MVP 首要目标是稳定生成 recommendation。
- 保存 response 会引入版本、provider、prompt、evidence snapshot 等追踪字段。
- 可以在下一阶段新增 `idea_recommendations` 表。

如果用户希望记录推荐历史，可以在实现计划中新增轻量表，但不作为本设计的默认范围。

### 5.4 Retrieval query 构造

推荐先使用 deterministic query builder：

```text
{task} {model} {dataset} {metric_problem} {observation} {goal} {tried_methods joined by space}
```

规则：

- 去掉空白字段。
- `tried_methods` 保持用户原词。
- query 只用于 retrieval 和可选 discovery，不写回为日志正文。
- 不使用 LLM rewrite，避免把本阶段扩成 planner。

### 5.5 Idea generator

推荐新增 protocol：

```python
class IdeaGenerator(Protocol):
    def generate(
        self,
        experiment_log: ExperimentLogRequest,
        retrieved_chunks: list[KnowledgeSearchResult],
        discovery_candidates: list[dict],
        idea_count: int,
    ) -> list[IdeaOption]:
        ...
```

默认实现：

- `DeterministicIdeaGenerator`

可选实现：

- `LLMIdeaGenerator`

默认 deterministic 行为：

- 基于日志字段生成 3-5 个模板化 idea。
- 有 retrieval sources 时，每个 idea 至少挂载 1 个 knowledge evidence。
- 没有 sources 时，`supporting_evidence=[]`，并在 rationale 中说明本地知识库未找到直接证据。
- 不声称文献支持不存在的事实。

LLM provider 行为：

- 使用 idea 专用 prompt builder。
- LLM 只生成 idea 文本和结构化字段。
- `supporting_evidence` 仍由服务层从 retrieval/discovery 对象映射，不接受 LLM 自造引用。
- 解析失败时返回 502 或降级 deterministic，具体策略在 implementation plan 中定。

### 5.6 DeepSeek 复用边界

DeepSeek 复用当前 OpenAI-compatible client 配置：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`

推荐新增配置：

- `IDEA_PROVIDER=deterministic|deepseek|openai`
- `IDEA_MODEL`
- `IDEA_TEMPERATURE`

默认：

- `IDEA_PROVIDER=deterministic`

这样不会影响现有：

- `ANSWER_PROVIDER`
- `PAPER_JUDGE_PROVIDER`

也不会让 `/knowledge/answer`、paper judge 和 idea generator 三类 provider 相互污染。

### 5.7 Discovery 复用边界

`/ideas/recommend` 可以支持：

- `include_discovery=false` 默认
- `include_discovery=true` 可选

当 `include_discovery=true`：

- 调用现有 discovery graph。
- 使用同一个 query builder 产出的 query。
- discovery failure 写入 `discovery.error`。
- 如果 knowledge retrieval 成功，discovery failure 不阻断 ideas。
- discovery candidates 仍不自动入库。

默认测试不启用真实 discovery。API tests 应通过 fake graph 或 dependency override 覆盖 discovery section。

### 5.8 Error handling

推荐规则：

- 空日志核心字段返回 422 或 400，由 Pydantic/服务层约束。
- 空 retrieval query 返回 400。
- retrieval 失败且 discovery 未启用时，返回 400 或对应 retrieval error。
- retrieval 无结果不算失败，返回空 sources 和 deterministic fallback ideas。
- discovery 失败只写入 `discovery.error`，除非请求只启用了 discovery 且无可生成 ideas。
- LLM provider 失败不影响默认测试；真实 provider smoke 单独手动验证。

## 6. Subagent 可执行任务

### Task 1: Schema 和 store

Subagent 可执行：

- 新增结构化实验日志 schema。
- 新增 `experiment_log_entries` 表。
- 新增 `add_experiment_log_entry()`。
- 新增 `list_experiment_log_entries()`。
- 写 `test_memory_store.py` 覆盖保存和读取。

你需要亲自 review：

- 结构化日志字段是否反映真实实验思考方式。
- 是否需要额外字段，例如 `baseline`、`constraints`、`failure_mode`。

### Task 2: Idea generator contract

Subagent 可执行：

- 新增 `idea_service.py` 或 `idea_generator.py`。
- 实现 `DeterministicIdeaGenerator`。
- 写单元测试覆盖有 sources 和无 sources 两种情况。

你需要亲自 review：

- idea 文案是否简历项目可解释。
- `supporting_evidence` 是否足够严格。
- fallback ideas 是否过度声称效果。

### Task 3: Recommendation orchestration

Subagent 可执行：

- 实现 `IdeaRecommendationService`。
- 复用 `KnowledgeRetrievalService`。
- 可选接入 discovery graph dependency。
- 覆盖 partial failure tests。

你需要亲自 review：

- retrieval query builder 是否简单但够用。
- discovery 默认关闭是否符合产品演示路径。
- no-source 场景是否应该返回 ideas。

### Task 4: FastAPI endpoints

Subagent 可执行：

- 新增 `POST /experiments/logs`。
- 新增 `GET /experiments/logs`。
- 新增 `POST /ideas/recommend`。
- 新增 API tests，并通过 dependency override 保持离线。

你需要亲自 review：

- endpoint 命名是否稳定。
- `/logs` 和 `/experiments/logs` 的文档区分是否清楚。

### Task 5: Docs 和 smoke notes

Subagent 可执行：

- 更新 README 的已实现 endpoint 列表。
- 更新测试说明。
- 可选新增手动 smoke plan。

你需要亲自 review：

- README 是否只写已经完成的事实。
- 是否避免声称真实 DeepSeek idea provider 已通过测试。

### Task 6: 前端小入口

Subagent 可执行：

- 在现有 Vue Research Workbench 中新增一个简洁 Idea Assistant panel。
- 新增 API helper。
- 展示 ideas、sources、discovery error。

你需要亲自 review：

- 是否仍是工作台，不是 landing page。
- 是否避免前端大改和 chat UI 化。

## 7. 我需要掌握的核心解释

### 为什么保留 `/logs`

`/logs` 当前是简单文本日志接口，并且 Advanced-lite query rewriting 已经消费它构造 memory context。把它改成结构化实验日志会破坏现有契约，也会让一个 endpoint 同时承担 simple note、实验记录和 idea trigger 三种语义。

### 为什么新增 `/experiments/logs`

结构化实验日志是 Idea Assistant 的核心输入，字段需要可验证、可持久化、可复现。单独 endpoint 能让后续 idea recommendation、实验计划拆解、结果回填都围绕同一条实验记录演进。

### 为什么新增 `/ideas/recommend`

Idea recommendation 是新的 workflow。它不等同于 `/knowledge/answer`，因为它返回的是多个结构化 options，而不是一个自然语言 answer。它也不等同于 `/research/query`，因为主目标不是文献发现，而是基于当前实验问题生成下一步实验方向。

### 为什么不直接复用 `KnowledgeQAService`

`KnowledgeQAService` 的职责是：

```text
question -> retrieval -> grounded answer
```

Idea Assistant 的职责是：

```text
structured experiment log -> retrieval/discovery -> structured idea options
```

二者都依赖 retrieval，但输出契约不同。复用 `KnowledgeRetrievalService`，新建 `IdeaRecommendationService`，边界更清楚。

### 为什么默认 deterministic

默认 deterministic 能保证：

- API tests 离线稳定。
- 简历项目演示可复现。
- provider 错误不会污染核心 contract。
- 后续 DeepSeek/OpenAI 接入可以作为增强项，而不是 MVP 的前置条件。

### 什么叫 evidence-grounded

`supporting_evidence` 只能来自：

- `KnowledgeRetrievalService` 返回的 knowledge chunks。
- 可选 discovery graph 返回的 candidate metadata。

LLM 可以组织 `title`、`rationale`、`expected_benefit`、`risk`、`next_small_experiment`，但不能自己生成不存在的 paper、chunk、citation 或 source。

## 8. 下一步建议

建议下一步写 implementation plan：

`docs/superpowers/plans/2026-06-09-idea-assistant-mvp-implementation.md`

计划应按以下顺序组织：

1. 结构化实验日志 schema/store/tests。
2. deterministic idea generator/tests。
3. recommendation orchestration/tests。
4. FastAPI endpoints/API tests。
5. README 更新。
6. 可选前端小入口。

默认验证命令继续使用：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest backend/src/tests -q
```

如果实现阶段只改后端 Idea Assistant，可优先跑：

```bash
PYTHONPATH=backend/src ./.venv/bin/python -m pytest \
  backend/src/tests/test_memory_store.py \
  backend/src/tests/test_api_mvp.py \
  backend/src/tests/test_retrieval_service.py \
  -q
```

真实 DeepSeek idea provider、真实 BGE-M3、真实 Chroma、真实 external discovery 都应保持为手动 smoke，不进入默认 pytest。

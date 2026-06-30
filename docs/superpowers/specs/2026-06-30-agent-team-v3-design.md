# Agent Team V3 Design

日期：2026-06-30

> 本文档定义 `graphReconstruction` V3 的冻结设计：先建立正确的 Candidate 生命周期和单个永久 Session，再实现同步、逻辑持久化的 Agent Team。多 Session、异步 SQLite Mailbox、后台 Worker 和更全面的上下文管理属于后续演进，不进入第一版实现范围。

## 1. Problem Statement

当前系统存在两个直接影响产品闭环的问题：

1. Candidate 缺少明确的会话生命周期。推荐结果和已保存论文的概念容易混淆，旧推荐还可能持续占据可操作区域，阻碍用户看到和管理新推荐。
2. `/research/assistant` 是 single-turn workflow。系统没有 Session、消息历史、上下文窗口、会话摘要或 Agent 运行记录，因此不能支持持续研究管理。

用户希望进一步把现有能力组织为一个 Agent Team：

- `Leader Agent`：唯一面向用户，负责理解目标、规划、委派和最终回复。
- `Research Agent`：负责新论文搜索、筛选、排序和 Candidate 生成。
- `Idea Agent`：负责根据实验记录、已有知识和按需提供的新论文证据生成研究 Idea。

V3 必须保持当前项目的真实边界：这是可解释、受约束的 Agent/RAG workflow，不是允许自由循环、动态新增 Agent 或任意执行动作的 autonomous agent。

## 2. Goals And Non-Goals

### 2.1 Goals

- 将临时推荐 Candidate 与全局 Saved Papers 明确分离。
- 新一轮用户消息提交时，使上一轮未接受 Candidate 退出可操作区。
- 使用单个默认永久 Session 实现第一版多轮对话。
- 持久化完整消息历史，但只加载会话摘要和最近消息进入上下文。
- 实现 `Leader + Research + Idea` 的同步 Agent Team。
- 为每个 Agent 持久化身份、上下文摘要、运行记录和错误状态。
- 使用有界 LLM Planner、Typed Plan 和确定性 Validator 约束 Leader。
- 保持 Saved Papers、向量知识库和 Confirmed Memory 跨 Session 共享。
- 保持 `/research/assistant` 暂时兼容，为新 Session API 提供迁移窗口。
- 为后续多 Session 和异步 SQLite Mailbox 预留稳定接口。

### 2.2 Non-Goals

- 第一版不实现多个 Session 的创建、切换、重命名和归档 UI。
- 不实现自由 ReAct 循环。
- 不允许运行时动态新增 Agent。
- 不实现 Agent 常驻后台进程。
- 不实现 SQLite Mailbox、消息租约、Worker 调度或死信队列。
- 不实现 SSE、流式输出、interrupt 或恢复执行。
- 不把全部聊天历史放入每次 LLM 请求。
- 不把普通聊天自动升级为 Confirmed Memory。
- 不让 Agent 自动 Accept 论文或执行其他需要用户确认的持久化动作。
- 不把临时 Candidate 或普通聊天写入全局向量知识库。

## 3. Design Decisions

### 3.1 Single Default Session First

第一版只使用固定 Session：

```text
session_id = "default"
```

数据库、服务和 API 从第一天保留 `session_id`。后续增加多 Session 时，只扩展 Session 管理和 UI，不重写消息、Candidate、Agent Run 或上下文模型。

### 3.2 Logical Persistence, Not Resident Processes

第一版 Agent 是逻辑持久化的：

- Agent 名称、职责和 System Prompt 固定。
- Agent 上下文摘要和运行记录保存在 SQLite。
- 每次收到任务时恢复所需上下文并同步执行。
- 执行结束后释放运行资源，但保留状态。

持久化 Agent 不等于始终运行的后台进程。常驻 Worker 和异步收件箱属于后续阶段。

### 3.3 Leader Is The Only User-Facing Agent

用户只与 Leader 交互。Research 和 Idea 是内部专业 Agent，不争夺对话控制权，也不直接生成最终用户回复。

前端可以显示调用轨迹、阶段状态和证据来源，但第一版不提供三个独立聊天窗口。

### 3.4 Bounded LLM Planner

System Prompt 和 few-shot 用于改善 Leader 的规划倾向，但不能承担硬约束。Leader 必须生成 Typed Plan，并由确定性 Validator 校验后才能执行。

允许的第一版计划类型：

```text
direct_reply
knowledge_qa
research
idea
research_then_idea
clarify
```

禁止：

- 自由循环。
- 动态创建 Agent。
- 调用未注册 Agent 或 Action。
- Agent 自动 Accept Candidate。
- 在缺少必要输入时猜测执行。

### 3.5 On-Demand Research Before Ideas

Idea Agent 始终可以使用：

- 当前请求的结构化实验记录。
- Session 内相关实验背景。
- Confirmed Memory。
- 现有向量知识库证据。
- Leader 显式传入的新论文证据。

是否先搜索新论文取决于知识覆盖：

```text
覆盖充分
  -> Idea Agent

覆盖不足，或用户明确要求最新论文
  -> Research Agent
  -> Idea Agent
```

Research Agent 是新论文发现和 Candidate 生成的唯一所有者。Idea Agent 不再内部复制完整 Discovery workflow。

## 4. Target Architecture

```text
User Message
  -> Session Turn API
      -> ConversationService
          -> CandidateLifecycleService
          -> ContextBuilder
          -> LeaderAgent
              -> PlanValidator
              -> DirectAgentDispatcher
                  -> Knowledge QA
                  -> ResearchAgent
                      -> existing Discovery Subgraph
                  -> IdeaAgent
                      -> existing Idea Service capabilities
          -> AgentRunStore
          -> MessageStore
          -> SessionSummaryService
  -> Structured Turn Response
```

### 4.1 ConversationService

Responsibilities:

- 创建和完成 Turn。
- 保存 user/assistant messages。
- 在新 Turn 开始时过期旧 Candidate Batch。
- 构建 Leader 上下文。
- 调用 Leader Planner、Validator 和 Dispatcher。
- 聚合 Agent 结果并保存最终回复。
- 管理幂等、Session Busy 和部分失败。

ConversationService 不实现论文搜索、向量检索或 Idea 生成细节。

### 4.2 LeaderAgent

Responsibilities:

- 理解当前用户目标。
- 基于受控上下文生成 Typed Plan。
- 在 Agent 结果返回后生成最终用户回复。
- 在输入不足时提出澄清问题。

Leader 不直接实现 Discovery pipeline，也不能绕过 Validator 执行动作。

### 4.3 PlanValidator

Responsibilities:

- 校验 Plan Schema。
- 校验 Agent 和 Action 白名单。
- 限制步骤数量和依赖拓扑。
- 校验 Idea 所需实验或证据输入。
- 校验 Candidate 只能由 Research Agent 生成。
- 阻止自动 Accept 或未授权持久化动作。
- 对非法计划返回安全、可解释的失败结果。

第一版只允许单步计划，或固定的两步 `research -> idea` 计划，不允许任意 DAG 或循环。

### 4.4 ResearchAgent

Responsibilities:

- 接收研究问题和受控 Research Context。
- 复用现有 Discovery Subgraph 执行 query rewrite、multi-search、postprocess、judge 和 rank。
- 输出结构化 Research Result。
- 在需要推荐时创建 Candidate Batch。

Research Agent 不保存论文到全局 `papers`。只有用户 Accept 后才进入 Saved Papers。

### 4.5 IdeaAgent

Responsibilities:

- 接收当前结构化实验记录。
- 使用相关 Session Context、Confirmed Memory 和知识证据。
- 接收可选的 Research Agent 结果作为新证据。
- 输出结构化 Idea Result 和 supporting evidence。

Idea Agent 不自行运行完整 Discovery pipeline，也不创建 Candidate Batch。

### 4.6 ContextBuilder

ContextBuilder 为不同 Agent 构建不同上下文视图：

- Leader Context：Session Summary、最近消息、当前用户消息、当前业务状态。
- Research Context：当前研究问题、必要研究背景、已接受论文和重复搜索线索。
- Idea Context：当前实验记录、相关历史实验背景、知识证据和已选研究方向。

Agent 不默认读取完整消息历史或其他 Agent 的全部内部记录。

### 4.7 DirectAgentDispatcher

第一版使用同步接口：

```python
AgentDispatcher.dispatch(task) -> AgentResult
```

实现类为 `DirectAgentDispatcher`。后续异步化时替换为 `SQLiteMailboxDispatcher`，Leader、Validator 和专业 Agent 的业务契约不变。

## 5. Persistence Model

### 5.1 Sessions

```text
sessions
- id TEXT PRIMARY KEY
- title TEXT
- summary TEXT
- summary_through_message_id INTEGER NULL
- status TEXT NOT NULL
- created_at TEXT NOT NULL
- updated_at TEXT NOT NULL
```

第一版初始化 `default` Session。`status` 第一版使用 `active`，为后续 `archived` 预留枚举。

### 5.2 Conversation Turns

```text
conversation_turns
- id TEXT PRIMARY KEY
- session_id TEXT NOT NULL
- idempotency_key TEXT NOT NULL
- status TEXT NOT NULL
- plan_json TEXT NULL
- error_json TEXT NULL
- created_at TEXT NOT NULL
- completed_at TEXT NULL
- UNIQUE(session_id, idempotency_key)
```

Turn 状态：

```text
running | completed | failed
```

同一 Session 第一版最多有一个 `running` Turn。

### 5.3 Messages

```text
messages
- id INTEGER PRIMARY KEY AUTOINCREMENT
- session_id TEXT NOT NULL
- turn_id TEXT NOT NULL
- role TEXT NOT NULL
- agent_name TEXT NULL
- content_json TEXT NOT NULL
- created_at TEXT NOT NULL
```

允许的 `role`：

```text
user | assistant | agent | system
```

完整消息持久化用于历史展示和审计，但不代表全部进入 LLM 上下文。

### 5.4 Candidate Batches

```text
candidate_batches
- id TEXT PRIMARY KEY
- session_id TEXT NOT NULL
- turn_id TEXT NOT NULL
- query TEXT NOT NULL
- status TEXT NOT NULL
- created_at TEXT NOT NULL
- expired_at TEXT NULL
```

Batch 状态：

```text
active | expired
```

同一 Session 同时最多一个 `active` Batch。

### 5.5 Candidate Items

```text
candidate_items
- id TEXT PRIMARY KEY
- batch_id TEXT NOT NULL
- paper_key TEXT NOT NULL
- paper_snapshot_json TEXT NOT NULL
- judgement_json TEXT NULL
- status TEXT NOT NULL
- accepted_paper_id TEXT NULL
- created_at TEXT NOT NULL
- updated_at TEXT NOT NULL
- UNIQUE(batch_id, paper_key)
```

Item 状态：

```text
active | accepted | expired
```

`paper_snapshot_json` 保存历史展示需要的只读快照。它不等于全局 Saved Paper。

### 5.6 Agent Contexts

```text
agent_contexts
- session_id TEXT NOT NULL
- agent_name TEXT NOT NULL
- summary TEXT NOT NULL
- updated_through_message_id INTEGER NULL
- updated_at TEXT NOT NULL
- PRIMARY KEY(session_id, agent_name)
```

Agent Context 是 Session 内运行上下文，不会自动升级为 Confirmed Memory。

### 5.7 Agent Runs

```text
agent_runs
- id TEXT PRIMARY KEY
- session_id TEXT NOT NULL
- turn_id TEXT NOT NULL
- agent_name TEXT NOT NULL
- action TEXT NOT NULL
- status TEXT NOT NULL
- input_json TEXT NOT NULL
- output_json TEXT NULL
- error_json TEXT NULL
- started_at TEXT NOT NULL
- completed_at TEXT NULL
```

Run 状态：

```text
running | completed | failed | skipped
```

### 5.8 Global Shared Data

以下数据保持跨 Session 共享：

- `papers`
- `paper_judgements`
- `knowledge_chunks`
- 向量数据库中的已嵌入论文
- `semantic_memory` 中已确认条目

临时 Candidate、普通消息、Session Summary 和 Agent Context 不进入全局向量库。

### 5.9 Migration Strategy

V3 不继续依赖“启动时只执行 `CREATE TABLE IF NOT EXISTS`”作为完整迁移机制。实施时应增加轻量、可排序、可重复执行的 SQLite migration：

- 使用 `schema_migrations` 记录已应用版本。
- 为现有数据库创建 `default` Session。
- 新表和索引通过增量 migration 添加，不要求删除或重建用户数据库。
- 现有 `papers.status='candidate'` 记录不自动转换为 Session Active Candidate，因为它们缺少来源 Turn 和明确的当前操作语义。
- Legacy candidate rows 暂时保留用于审计，但从新 Active Candidate API 和 Saved Papers API 中排除；后续通过单独、可确认的清理流程处理。
- Saved Papers API 只返回 `accepted | uploaded | chunked | embedded`。

迁移必须在现有数据副本上测试，并验证重复启动不会重复插入默认 Session 或破坏已有论文、知识块和 Memory。

## 6. Candidate Lifecycle

### 6.1 Core State Machine

```text
Research recommendation
  -> active Candidate Item

User Accept
  -> accepted Candidate Item
  -> upsert global Paper with status=accepted
  -> uploaded -> chunked -> embedded

Next user Turn starts
  -> previous active Candidate Items become expired
  -> previous active Batch becomes expired
  -> items disappear from active operation area
  -> historical message snapshots remain read-only
```

### 6.2 Expiration Timing

旧 Candidate 在新 Turn 成功创建时立即过期，而不是等新 Research 结果成功后再过期。这符合“下一次提问前未 Accept 就退出可操作区”的产品语义。

如果新 Turn 后续失败：

- 旧 Candidate 不恢复为 active。
- 历史仍可查看。
- 前端提供 Retry。

### 6.3 Accept Rules

- 只有 `active` Candidate Item 可以 Accept。
- `expired` Item 返回 HTTP `409 Candidate expired`。
- Accept 在同一事务中完成 Candidate 状态更新和全局 Paper 写入。
- Accept 请求必须幂等；重复请求返回已经完成的结果。
- Agent 不能替用户执行 Accept。

### 6.4 API Naming Cleanup

当前 `/papers/candidates` 实际混合了已保存论文的多种状态，名称与语义不一致。V3 分离为：

- Session Active Candidates API：仅当前可操作推荐。
- Saved Papers API：全局已接受、上传、分块或嵌入论文。

旧接口在迁移窗口内保留，但不得继续作为新前端的 Candidate 数据源。

### 6.5 Refresh And Suppression Policy

Candidate 过期解决“旧结果仍可操作”的问题；Research 输出过滤解决“下一次仍返回同一批论文”的问题。第一版采用有限抑制，而不是永久黑名单：

- 排除已经存在于全局 Saved Papers 中的论文，包括 `accepted | uploaded | chunked | embedded`。
- 排除同一 Session 最近一个已过期 Candidate Batch 中的论文。
- Research pipeline 应扩大候选池后再过滤，尽量补足请求的 `top_k`。
- 如果过滤后没有足够的新论文，允许返回少于 `top_k`，并明确说明没有找到足够的新候选；不能用旧结果静默填满。
- 更长时间的遗忘、冷却窗口或用户手动恢复机制属于后续阶段。

该策略保证刷新是数据层语义，而不只是前端清空数组。最近一批过期论文在更后的推荐中仍可重新出现，为后续遗忘策略保留空间。

## 7. Context Management

### 7.1 First-Version Context Window

每次 Leader 调用使用：

```text
Leader System Prompt
+ Session Summary
+ 最近 6 个完整 Turn
+ 当前用户消息
+ 当前业务状态
+ 相关 Confirmed Memory
+ 当前问题召回的知识证据
```

Agent 使用 ContextBuilder 生成的更窄视图，不直接继承 Leader 的全部上下文。

### 7.2 Rolling Summary

- 完整消息始终持久化。
- 当未摘要消息达到 12 条时，在成功 Turn 结束后更新 Session Summary。
- `summary_through_message_id` 标记摘要覆盖边界。
- 摘要更新失败不影响主 Turn 成功状态。
- 失败时保留旧 Summary，并在后续 Turn 重试。
- 摘要不直接写入 Confirmed Memory。

### 7.3 Long-Term Memory Boundary

- 普通会话历史：Session 内持久化。
- Agent Context：Session 内角色上下文。
- Confirmed Memory：跨 Session 共享，继续保持 review-gated。
- 向量知识：只来自已接受并完成嵌入的论文。

这些层不能因为“都属于上下文”而合并为一个无边界 Memory。

## 8. Planning And Execution Contracts

### 8.1 Typed Plan

计划至少包含：

```text
goal
plan_type
steps[]
needs_clarification
clarification_question
```

每个 Step 至少包含：

```text
id
agent
action
input
depends_on[]
```

### 8.2 Allowed First-Version Actions

```text
leader.direct_reply
leader.clarify
knowledge.answer
research.recommend_papers
idea.generate_ideas
```

`research_then_idea` 是两个受控 Step 的组合，不是新的 Agent。

### 8.3 Few-Shot And Eval Cases

few-shot 与 Planner Eval 应覆盖：

- 明确找论文 -> Research。
- 基于当前实验提出方向且知识充分 -> Idea。
- 知识不足或要求最新论文 -> Research then Idea。
- 解释已保存论文 -> Knowledge QA。
- 输入不足 -> Clarify。
- 仅闲聊或产品说明 -> Direct Reply。
- 要求自动 Accept -> 拒绝自动执行并请求用户确认。
- 要求创建未知 Agent -> Validator 拒绝。

few-shot 改善模型倾向；Typed Schema、Validator 和 Eval 才形成工程约束。

## 9. API Design

### 9.1 Turn API

```text
POST /sessions/{session_id}/turns
```

第一版使用：

```text
POST /sessions/default/turns
```

请求包含：

```text
message
experiment_log optional
idempotency_key
```

响应包含：

```text
turn_id
status
assistant_message
plan summary
active_candidates
ideas
knowledge result
agent run summaries
errors
```

### 9.2 Read APIs

```text
GET /sessions/{session_id}/messages
GET /sessions/{session_id}/candidates/active
GET /papers
```

消息历史必须分页，不能一次返回永久 Session 的全部内容。

### 9.3 Candidate Action API

```text
POST /sessions/{session_id}/candidates/{candidate_id}/accept
```

Accept 成功后返回 Candidate 状态和 Saved Paper 状态。

### 9.4 Compatibility

- `/research/assistant` 暂时保持 stateless。
- 新聊天前端只使用 Session Turn API。
- `/research/query` 继续作为显式低层入口。
- 旧 `/papers/candidates` 在迁移窗口保留，但标记为 legacy。
- 移除兼容接口需要单独设计和用户确认。

## 10. Turn Transaction And Failure Semantics

### 10.1 Turn Start

在一个短事务中：

1. 根据 `idempotency_key` 检查重复请求。
2. 检查 Session 是否已有 `running` Turn。
3. 创建新 Turn。
4. 保存 User Message。
5. 过期旧 Candidate Batch 和未接受 Item。

LLM 或外部搜索调用不能持有 SQLite 写事务。

### 10.2 Execution

- Planner 非法：不执行专业 Agent，返回 Clarification 或安全错误。
- Research 失败：依赖它的 Idea Step 标记 `skipped`。
- Research 成功、Idea 失败：保留新 Candidate Batch，返回部分成功。
- Knowledge QA 失败：保留其他成功结果，并区分无证据与 Provider 故障。
- Summary 更新失败：Turn 仍可成功。
- 每个 Agent Step 有独立超时，整个 Turn 有总超时。

### 10.3 Turn Completion

成功或部分成功时：

- 保存 Assistant Message。
- 保存 Plan、Agent Runs 和结构化结果。
- 更新 Turn 状态。
- 更新 Agent Context。
- 达到阈值时尝试更新 Session Summary。

失败时保存结构化错误，避免只留下无法诊断的 HTTP 500。

### 10.4 Concurrency And Idempotency

- 同一 Session 第一版只允许一个运行中 Turn。
- 并发 Turn 返回 `409 session busy`。
- 相同 `idempotency_key` 返回原 Turn。
- Candidate Accept 必须幂等。
- SQLite 启用 WAL、`busy_timeout` 和短事务。

## 11. Frontend Behavior

第一版聊天页面至少包含：

- 默认 Session 的消息历史。
- 当前输入框和运行状态。
- Leader 最终回复。
- 可折叠的计划摘要和 Agent Run 状态。
- 当前 active Candidate 操作区。
- 历史消息中的只读 Candidate 快照。
- Saved Papers / lifecycle 独立区域。
- Knowledge sources 和 Idea results。

新 Turn 提交后，旧 Candidate 立即从可操作区消失。历史快照可以保留，遗忘机制后置。

第一版不做多 Session 侧边栏，也不做三个 Agent 的独立聊天窗口。

## 12. Verification Strategy

### 12.1 Unit Tests

- Candidate Batch/Item 状态机。
- ContextBuilder 的角色隔离。
- Session Summary 覆盖边界。
- Typed Plan Schema。
- PlanValidator 白名单、依赖和禁止动作。
- Agent Result 映射和错误分类。

### 12.2 Store And Transaction Tests

- 新 Turn 原子创建并过期旧 Candidate。
- Accept 原子更新 Candidate 和 Paper。
- Expired Candidate 返回 409。
- 重复 Turn 和 Accept 的幂等。
- 同一 Session 并发 Turn 返回 409。
- Agent Run 和 Message 的关联完整性。

### 12.3 Workflow Tests

- Direct Reply 不调用专业 Agent。
- Knowledge QA 不创建 Candidate。
- Research 创建 active Batch。
- Research 排除 Saved Papers 和最近一个过期 Batch，并在候选不足时诚实返回较少结果。
- Idea 在覆盖充分时不重复 Discovery。
- Research then Idea 正确传递证据。
- Research 失败时 Idea 跳过。
- Research 成功、Idea 失败时保留 Candidate。
- Summary 失败不影响 Turn 主结果。

### 12.4 Planner Eval

建立 10-20 个初始代表性案例，至少覆盖：

- 正常路由。
- 模糊请求。
- 证据不足。
- 最新论文需求。
- 自动持久化越权请求。
- 未知 Agent 请求。
- 多步骤顺序。

Eval 同时检查 Plan 类型、Step 顺序、禁止动作和澄清行为，不能只检查自然语言是否相似。

### 12.5 End-To-End Verification

- Backend 全量 pytest。
- Frontend component tests。
- Frontend production build。
- Offline MVP smoke。
- Session Turn offline smoke。
- `git diff --check` 和文档/API 契约检查。

默认测试使用 fake/deterministic providers；真实外部 Provider 只做独立手动 smoke。

## 13. Implementation Phases

### Phase 0: Baseline Convergence

- 核对 `codex/agent-system-v1-refactor` 的最终提交和测试。
- 将 Agent V1 后端与当前 assistant-first 前端收敛到统一干净基线。
- 运行 backend、frontend 和 offline smoke。

### Phase 1: Candidate Lifecycle

- 初始化默认 Session。
- 新增 Candidate Batch/Item persistence。
- 分离 Active Candidates 与 Saved Papers API。
- 实现过期、Accept、409 和幂等。
- 暂不改变 Agent 路由。

### Phase 2: Permanent Session And Context

- 新增 Turns、Messages 和 Session Summary。
- 实现最近 6 Turn + 滚动摘要。
- 增加 Session Busy、历史分页和 Turn 幂等。
- 前端切换到基本聊天记录和当前 Candidate 操作区。

### Phase 3: Synchronous Agent Team

- 实现 Leader Typed Planner 和 Validator。
- 包装现有 Discovery Subgraph 为 Research Agent。
- 收敛现有 Idea Service 为 Idea Agent。
- 实现按需 Research then Idea。
- 持久化 Agent Context 和 Agent Runs。

### Phase 4: Quality Convergence

- 建立 few-shot 和 Planner Eval 数据集。
- 增加 Trace、超时和部分失败验证。
- 前端展示计划摘要、Agent Run 状态和证据来源。
- 完成兼容接口和文档收敛。

### Later Phases

- 多 Session 管理。
- Candidate 历史遗忘策略。
- SQLite Mailbox 和异步 Worker。
- Streaming、后台执行、恢复和中断。

## 14. SQLite Mailbox Evolution Boundary

后续 Mailbox 必须复用 `AgentDispatcher` 契约，而不是重写 Leader 或专业 Agent。

建议状态机：

```text
queued -> leased -> acknowledged
            |
            -> failed -> retry -> dead_letter
```

建议字段：

```text
id
session_id
from_agent
to_agent
message_type
payload_json
status
attempt_count
available_at
lease_until
idempotency_key
created_at
acknowledged_at
```

Mailbox 消息不能“读取后直接删除”。Worker 在短事务中领取消息，成功后 ACK；租约超时未 ACK 的消息可以重试，超过次数进入 dead letter。

SQLite 适合当前本地单机作品集项目。若未来进入多主机或高并发 Worker 场景，再评估 PostgreSQL 或专用消息队列。

## 15. User Review And Delegation Boundary

用户应重点参与并能够解释：

- Leader 的规划动作和安全边界。
- few-shot 与 Planner Eval 案例。
- Candidate、Session Context、Confirmed Memory 的区别。
- Research 与 Idea Agent 的职责边界。
- 覆盖充分与不足时的按需策略。
- 状态机、持久化和部分失败语义。
- 从同步 Dispatcher 演进到异步 Mailbox 的原因。

可由实现执行流程直接完成：

- SQLite schema 和 store CRUD。
- API 接线和兼容层。
- 事务、幂等和分页样板。
- 前端状态管理和常规组件接线。
- 测试夹具、fake providers 和文档同步。

## 16. Success Criteria

V3 第一版完成时必须满足：

1. 用户可以在默认永久 Session 中连续多轮对话。
2. 完整历史持久化，但模型上下文只使用摘要和最近窗口。
3. 新 Turn 会使上一轮未接受 Candidate 退出可操作区。
4. Active Candidates 与 Saved Papers 在 API、数据库语义和 UI 上分离。
5. Leader 是唯一用户入口，并通过 Typed Plan 和 Validator 调用固定 Agent。
6. Research 是新论文发现和 Candidate 的唯一所有者。
7. Idea 根据覆盖按需使用现有知识或 Research 新证据。
8. Agent 身份、上下文和运行记录可恢复、可审计。
9. 系统不允许自由循环、动态 Agent 或自动 Accept。
10. Backend、frontend、offline smoke 和 Planner Eval 全部通过。

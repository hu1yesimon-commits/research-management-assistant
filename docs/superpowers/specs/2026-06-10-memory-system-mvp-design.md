# Memory System MVP 设计

日期：2026-06-10

> 本文档是 Research Management Assistant 的 Memory System MVP 正式设计说明，不表示功能已经实现。后续实现应以本文档为范围边界，并继续保持默认离线、可解释、可确认、可测试。

## 1. 当前理解

当前项目已经完成：

- `/research/query` 统一研究入口，返回彼此独立的 `discovery` 和 `knowledge` section。
- discovery candidates 是临时检索结果，不自动写入 SQLite。
- 用户 `Accept` 后才把论文保存到 SQLite。
- knowledge sources 只来自已 `embedded` 的本地 chunk。
- LLM 不应编造 sources。
- 当前已有 `/logs`、`/experiments/logs`、`/ideas/recommend`，但还没有完整长期 memory system。
- Idea Assistant MVP 由用户主动提交结构化实验日志触发，而不是自动对话记忆。

本阶段要设计的不是“保存聊天历史”，而是一个可以支撑多个 workflow 的长期 memory layer：

- query rewrite
- idea recommendation
- experiment tracking
- personalized research assistant
- long-term context management

本设计采用三层半模型：

- `Working Memory`
  - 单次请求 / 单次 workflow 的临时上下文。
  - 默认不持久化。
- `Episodic Memory`
  - 用户明确提交的结构化实验日志。
  - 直接使用 `experiment_log_entries` 作为主证据层。
- `Semantic Memory`
  - 从多条 episodic memory 中提炼出的长期稳定事实。
  - 使用严格枚举的三元组表达。
  - 只允许 `confirmed` 状态进入正式长期记忆。
- `Memory Candidates`
  - 系统自动提议、但尚未确认的长期记忆候选。
  - 用于防止 memory pollution。

## 2. Goals And Non-Goals

### 2.1 Goals

- 在现有 `SQLite + knowledge chunk retrieval` 基础上，设计一个轻量、可解释、可确认的 memory system。
- 让 query rewrite 可以读取：
  - `confirmed semantic memory`
  - 最近 3 条用户实验日志
- 让 Idea Assistant 可以复用同一套长期记忆边界，而不是自己维护一套隐式记忆。
- 让长期记忆支持：
  - 重复出现的研究主题
  - 重复出现的实验对象
  - 明确记录的实验结果趋势
  - 反复出现的 block
- 引入 `memory_candidates` 作为自动提议与人工确认之间的缓冲层。
- 使用软遗忘，而不是物理删除。

### 2.2 Non-Goals

- 不把所有聊天历史保存为 memory。
- 不把 discovery candidates 保存为长期记忆。
- 不把 knowledge chunks 当作用户长期记忆本身。
- 不引入多用户协作、权限系统或复杂审核后台。
- 不在 MVP 阶段引入 Neo4j、Qdrant 或新的主持久化后端。
- 不在 MVP 阶段让系统自动修改 `confirmed semantic memory` 的事实状态。
- 不在 MVP 阶段做通用聊天代理式 memory。

## 3. 风险与假设

### 3.1 风险

- 如果把原始聊天历史直接持久化为 memory，噪声会非常高，长期记忆会迅速污染。
- 如果没有 `memory_candidates`，系统很容易把一次性猜测或临时现象直接写成长期事实。
- 如果 `semantic memory` 不是严格枚举，后续会出现大量语义近似但无法归并的 object / predicate。
- 如果 stale / conflict 直接自动落库，用户将很难理解系统为什么修改了长期记忆。
- 如果 query rewrite 读取过多历史日志，会造成上下文膨胀和旧阶段信息干扰。

### 3.2 假设

- 当前项目是单用户个人研究管理项目，长期记忆规模有限，允许统一表内用 `category` 区分不同语义。
- 结构化实验日志是最可靠的 episodic memory 来源。
- MVP 阶段长期记忆以 deterministic 规则提取为主，不依赖真实 LLM 才能工作。
- `confirmed semantic memory` 才能参与 query rewrite 和长期个性化。
- semantic proposal 的重复计数使用全局累计。
- query rewrite 的最近日志窗口固定为 3。

## 4. 当前项目记忆相关诊断

当前仓库已经具备与 memory system 相关的基础设施，但尚未形成真正的长期记忆层。

已经具备的能力：

- `POST /logs`
  - legacy/simple notes，当前主要服务轻量日志记录。
- `POST /experiments/logs`
  - 保存结构化实验日志。
- `GET /experiments/logs`
  - 读取结构化实验日志。
- `POST /ideas/recommend`
  - 接收单条结构化实验日志，生成 ideas。
- `POST /research/query`
  - 统一编排 discovery 与 knowledge。
- `MemoryStore.build_memory_context()`
  - 当前只把最近 simple logs 拼成文本，用于 Advanced-lite query rewrite。

当前不足：

- 还没有显式的 `semantic_memory`。
- 还没有 `memory_candidates`。
- 还没有确认机制来把 episodic evidence 提炼为长期记忆。
- 还没有 stale / conflict 的显式状态机。
- 还没有“软遗忘”的检索规则。
- 还没有把 query rewrite 读取的 memory source 从 `simple logs only` 升级到“confirmed semantic + recent episodic”。

结论：

- 当前项目适合在 `SQLite` 上增量实现 memory system。
- 不需要推翻 `experiment_log_entries`。
- 不需要把 `/logs` 升级成正式长期记忆主表。
- 不需要立即引入新数据库。

## 5. Memory Taxonomy

### 5.1 Working Memory

定义：

- 当前一次请求 / 一次 workflow 的临时上下文。

典型内容：

- 当前用户 query
- 当前新提交的 structured experiment log
- 当前 retrieval 结果
- 当前提议的 memory candidates
- 当前 prompt / rewrite context pack

策略：

- 默认不持久化。
- 生命周期以请求结束或 workflow 结束为界。

### 5.2 Episodic Memory

定义：

- 用户明确记录的实验事件、尝试、结果、观察和目标。

当前主载体：

- `experiment_log_entries`

理由：

- 结构清晰。
- 与 Idea Assistant 当前主输入完全对齐。
- 比聊天历史更可靠。
- 更适合作为长期语义提炼的证据源。

### 5.3 Semantic Memory

定义：

- 从多条日志中提炼出的长期稳定事实。

形式：

- 严格枚举的三元组：
  - `subject`
  - `predicate`
  - `object`

要求：

- 默认不自动生成正式事实。
- 只有用户确认后，才进入 `confirmed semantic memory`。

### 5.4 Memory Candidates

定义：

- 系统自动提议但尚未确认的长期记忆对象。

作用：

- 作为 episodic -> semantic 的缓冲层。
- 避免系统直接把临时现象、弱信号、推测结论写成长期事实。
- 承接 stale / conflict 这类需要 review 的状态变化。

## 6. 数据模型设计

## 6.1 `experiment_log_entries`

MVP 阶段继续直接使用当前结构化实验日志表作为 episodic 主表，不再额外引入 `episodic_memory` 表。

核心原因：

- 现有主输入已经稳定。
- Idea Assistant 已围绕该结构工作。
- 再抽一层只会增加复杂度，不增加解释性。

当前关键字段：

- `task`
- `model`
- `dataset`
- `metric_problem`
- `tried_methods`
- `observation`
- `goal`
- `tags`
- `created_at`

MVP 结论：

- `experiment_log_entries` 是长期记忆的原始证据层。
- 旧日志保留，不物理删除。
- 旧日志是否参与 query rewrite 由软遗忘策略控制。

## 6.2 `semantic_memory`

推荐新增表：

```sql
CREATE TABLE IF NOT EXISTS semantic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence REAL NOT NULL,
    support_count INTEGER NOT NULL,
    supporting_log_ids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

字段说明：

- `category`
  - 语义大类，使用严格枚举。
- `subject`
  - 研究主体，如具体 task、model line、研究方向实体。
- `predicate`
  - 严格枚举的关系。
- `object`
  - 归一化后的事实对象。
- `summary`
  - 给用户看的自然语言解释。
- `confidence`
  - 当前候选或已确认事实的置信度分数。
- `support_count`
  - 支持该事实的日志条数。
- `supporting_log_ids_json`
  - 证据日志 id 列表。
- `status`
  - MVP 阶段只建议保留：
    - `confirmed`
    - `archived`

MVP 原则：

- 正式长期记忆只允许 `confirmed` 进入主使用路径。
- stale / conflict 不直接改写主表，而是先进入 `memory_candidates`。

## 6.3 `memory_candidates`

推荐新增表：

```sql
CREATE TABLE IF NOT EXISTS memory_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_type TEXT NOT NULL,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_log_ids_json TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    score REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
```

字段说明：

- `candidate_type`
  - 候选类型，使用严格枚举。
- `category / subject / predicate / object`
  - 与 `semantic_memory` 保持同构，方便确认后迁移。
- `summary`
  - 候选解释文本。
- `source_log_ids_json`
  - 证据来源日志 id。
- `evidence_count`
  - 支持次数。
- `score`
  - 候选分数。
- `status`
  - 候选审核状态。

## 7. 严格枚举设计

MVP 阶段建议对 `category`、`predicate`、`candidate_type`、`status` 都使用严格枚举。

### 7.1 `category`

建议枚举：

- `research_topic`
- `experiment_target`
- `result_trend`
- `recurring_block`
- `user_preference`

定义：

- `research_topic`
  - 重复出现的研究方向或问题域。
- `experiment_target`
  - 重复出现的实验对象、模型线、数据对象或被优化对象。
- `result_trend`
  - 明确记录的效果趋势。
- `recurring_block`
  - 多次出现的阻塞点。
- `user_preference`
  - 稳定偏好，例如轻量化、可解释、避免重模型。

### 7.2 `predicate`

建议枚举：

- `focuses_on`
- `uses_object`
- `shows_trend`
- `blocked_by`
- `prefers`
- `avoids`

说明：

- `focuses_on`
  - 研究主体长期聚焦于某主题。
- `uses_object`
  - 实验主体反复围绕某实验对象。
- `shows_trend`
  - 结果趋势。
- `blocked_by`
  - 长期阻塞因素。
- `prefers`
  - 用户稳定偏好。
- `avoids`
  - 用户稳定回避项。

### 7.3 `candidate_type`

建议枚举：

- `semantic_proposal`
- `stale_proposal`
- `conflict_proposal`

### 7.4 Candidate `status`

建议枚举：

- `pending`
- `accepted`
- `rejected`
- `expired`

## 8. Object 归一化规则

MVP 阶段，语义等价但表面拼写略有差异的 object 应归一为同一 object。

例如：

- `focal loss`
- `focal-loss`

在进入 semantic candidate 计算前，应视为同一 `object`。

建议归一化规则：

- 小写化
- 去首尾空格
- 连字符与空格归一
- 多空格压缩为单空格
- 可维护少量 deterministic alias 表

MVP 原则：

- 先做 deterministic normalization。
- 不依赖 LLM 才能完成 object 合并。

## 9. Result Trend 表达规范

`result_trend` 不应只写短标签式 object，例如：

- `minority PRAUC low`

更推荐固定使用“方法 -> 影响 -> 指标变化”的清晰表达，例如：

- `focal loss improves recall but hurts precision`

这样做的原因：

- 语义更完整。
- 关系更清晰。
- 更适合做 stale / conflict 判断。
- 更适合直接展示给用户 review。

MVP 结论：

- `result_trend` 的 object 表达采用固定模板化自然语言。

## 10. Candidate 生成规则

## 10.1 `semantic_proposal`

生成条件：

- 同一候选事实在全局累计的用户日志中重复出现 3 次。

“同一候选事实”定义为：

- 相同 `category`
- 相同 `subject`
- 相同 `predicate`
- 归一化后相同 `object`

提议范围重点覆盖：

- 重复出现的研究主题
- 重复出现的实验对象
- 明确记录的实验结果趋势
- 反复出现的 block

策略：

- 系统可以自动提议。
- 系统不能自动写入 `semantic_memory.confirmed`。
- 必须先写入 `memory_candidates`，等待用户确认。

## 10.2 `stale_proposal`

系统可以生成 stale candidate 的场景：

- 用户明确废弃某长期记忆
- 新 confirmed 记忆替代旧 confirmed 记忆
- 项目阶段变化
- 长期缺少相关日志支持

处理规则：

- `用户明确废弃`
  - 可以生成高置信 stale candidate。
- `新 confirmed 替代旧 confirmed`
  - 可以生成高置信 stale candidate。
- `项目阶段变化`
  - 只能生成 candidate，必须用户确认。
- `长期缺少相关日志支持`
  - 只能生成 candidate，必须用户确认。

MVP 边界：

- 系统不能仅凭时间流逝自动把 `confirmed semantic memory` 改成 stale。

## 10.3 `conflict_proposal`

只有下列场景才生成 conflict candidate：

- 新的用户确认记录，与已有 `confirmed semantic memory` 在同一 `category + subject + predicate` 下出现互斥 `object`
- 用户明确纠正旧记忆

不应生成 conflict candidate 的情况：

- 新日志只是补充细节
- object 表达不同但归一化后等价
- 只是近期 evidence 强度变化，但不构成事实互斥

## 11. 确认、替代、冲突与归档流程

### 11.1 确认流程

1. 用户持续记录结构化实验日志。
2. 系统基于 deterministic 规则提取候选事实。
3. 当某事实全局累计出现 3 次，生成 `semantic_proposal`。
4. 用户 review 候选事实。
5. 用户确认后，写入 `semantic_memory`，状态为 `confirmed`。

### 11.2 替代流程

1. 新的 confirmed 事实与旧事实形成明确替代关系。
2. 系统生成 `stale_proposal`。
3. 用户确认后：
   - 旧 semantic memory 标记为 `archived`
   - 新 semantic memory 保持 `confirmed`

### 11.3 冲突流程

1. 系统检测到同一 `category + subject + predicate` 下存在互斥 object。
2. 生成 `conflict_proposal`。
3. 用户 review 后决定：
   - 保留旧事实
   - 用新事实替代旧事实
   - 两者都不采纳

## 12. 写入策略

### 12.1 `user-confirmed`

必须用户确认后才持久化为正式长期记忆的内容：

- `semantic_memory`
- stale / conflict 的最终处理结果

### 12.2 `auto-suggested but requires confirmation`

系统可以自动生成但不能直接生效的内容：

- `memory_candidates`
- semantic proposal
- stale proposal
- conflict proposal

### 12.3 `never persist`

以下内容不应作为 memory 持久化：

- 原始聊天历史 transcript
- 临时 query rewrite 过程文本
- 一次性的 discovery candidate 排名
- 未确认的模型推断
- 未 accept 的 discovery candidates
- retrieval 中间过程

## 13. 软遗忘策略

MVP 阶段的遗忘采用软遗忘，而不是物理删除。

定义：

- 旧日志继续保留为历史证据。
- 但旧日志不一定继续参与 query rewrite 的实时上下文。

具体规则：

- query rewrite 默认只读取最近 3 条日志。
- 更早日志默认不直接进入 rewrite context。
- 更早日志仍可用于：
  - semantic proposal 的全局累计
  - stale / conflict 的证据判断

MVP 原则：

- episodic retrieval 会降权。
- confirmed semantic truth 不因时间自动失效。

## 14. 检索策略

## 14.1 Query Rewrite

query rewrite 只读取：

- `confirmed semantic memory`
- 最近 3 条 `experiment_log_entries`

建议的 context assembly 顺序：

1. 先读取 `confirmed semantic memory`
2. 再读取最近 3 条日志
3. 组装成一个小而稳定的 `memory_context`

这样做的好处：

- 避免上下文膨胀
- 避免旧阶段日志过度影响当前 query
- 保留用户长期偏好和长期研究主题

## 14.2 Idea Assistant

Idea Assistant 推荐读取顺序：

1. 当前新提交的结构化实验日志
2. `confirmed semantic memory`
3. 必要时补最近 3 条日志

说明：

- 当前日志始终是最强上下文。
- semantic memory 提供长期方向和稳定 block。
- recent logs 提供最近阶段补充信息。

## 14.3 Long-Term Context Management

长期管理优先使用 SQLite 结构化过滤：

- 按 `category`
- 按 `predicate`
- 按 `status`
- 按 `support_count`
- 按 `updated_at`

MVP 阶段不要求 memory retrieval 先向量化。

## 14.4 Chroma Retrieval

当前 Chroma 或向量后端继续只服务：

- paper knowledge chunks 的 retrieval

不建议在 MVP 阶段把所有 memory 都写入向量库。

原因：

- 当前更缺的是可解释的数据模型和确认机制，不是向量召回能力。
- 把 memory 与 knowledge chunks 混存会增加语义混淆。

## 15. 为什么当前阶段不建议直接上 Neo4j / Qdrant

## 15.1 不建议直接上 Qdrant

原因：

- 当前已经有知识块向量检索能力。
- memory 的主要缺口不是向量库，而是：
  - 记忆对象模型
  - candidate 提议机制
  - 用户确认机制
  - 软遗忘策略
- 在这些基础没定型前更换向量库收益很小。

## 15.2 不建议直接上 Neo4j

原因：

- 当前长期记忆关系 schema 还在收敛中。
- 过早引入图库会把“潜在关系”过早固化成“结构事实”。
- 单用户个人研究管理场景下，SQLite 足以承载 MVP。
- 图查询的真实高价值需求还没有被证明频繁出现。

## 15.3 未来迁移路径

如果后续真的出现高频复杂关系查询，再考虑可选 graph store：

1. 先在 SQLite 中稳定：
   - episodic
   - candidates
   - confirmed semantic memory
2. 再统计真实查询模式。
3. 只有当跨实体关系遍历频繁成为瓶颈时，才引入 graph DB。

## 16. 阶段计划

### Phase M1: Structured Episodic Memory

目标：

- 明确 `experiment_log_entries` 就是 episodic memory 主体。
- 保留 `/logs` 为 legacy/simple notes。
- 引入 query rewrite 的最近 3 条日志窗口。

产物：

- episodic memory contract
- recent-log retrieval policy

### Phase M2: Memory Candidate Extraction

目标：

- 新增 `memory_candidates`。
- 用 deterministic 规则提取：
  - research topic
  - experiment target
  - result trend
  - recurring block

规则：

- 同一事实全局累计出现 3 次时生成 `semantic_proposal`。

### Phase M3: Semantic Memory With Confirmation

目标：

- 新增 `semantic_memory`。
- 支持用户确认 candidate 成为正式长期记忆。
- 只让 `confirmed semantic memory` 进入 query rewrite 和长期个性化。

### Phase M4: Advanced Hybrid Retrieval

目标：

- 继续使用：
  - SQLite filters
  - confirmed semantic pack
  - recent episodic pack
- 视真实需求再评估：
  - 向量化 memory retrieval
  - graph store

原则：

- 没有真实瓶颈，不新增新数据库。

## 17. Subagent 可执行任务

- 把本 spec 拆成实现计划。
- 定义 `semantic_memory` 与 `memory_candidates` 的 schema 迁移草案。
- 设计 object normalization 规则。
- 设计 deterministic candidate extraction 规则。
- 设计 query rewrite context assembly 规则。
- 设计 stale / conflict 的 review contract。

## 18. 需要用户亲自 Review 的设计点

以下设计点应继续由用户亲自 review 和解释：

- `category` 与 `predicate` 的最终枚举边界
- `result_trend` 的固定表达模板
- 哪些 stale candidate 可以视为高置信
- “项目阶段变化”的判断信号
- “长期缺少相关日志支持”的阈值
- conflict 的互斥判定规则

## 19. 最终结论

当前项目的 Memory System MVP 最合理的方向不是“保存全部聊天历史”，也不是“立刻换更复杂的数据库”，而是：

- 以 `experiment_log_entries` 作为 episodic 主证据层
- 以 `memory_candidates` 作为自动提议与用户确认之间的缓冲层
- 以严格枚举的三元组 `semantic_memory` 作为正式长期事实层
- 以“confirmed semantic + 最近 3 条日志”作为 query rewrite 的最小长期上下文包
- 以软遗忘控制上下文污染，而不是靠删除历史

这样可以在不重构现有系统的前提下，为 query rewrite、Idea Assistant、experiment tracking 和长期个性化提供统一、可解释、可控的 memory foundation。

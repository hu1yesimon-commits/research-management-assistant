# Stable Research Workflow And Evaluation Design

日期：2026-07-28

> 本文档定义稳定研究工作流、上下文边界和统一 Gold Scenario 评测合同。第一阶段只建立实现无关的设计与案例基线，不修改当前 V3 运行代码，也不声称现有 Agent 已完成这些能力。

## 1. Goal

系统需要把用户自然、口语化、可能跨多轮的研究表达压缩成可追溯的结构化研究状态，并在确定性边界内完成：

1. 新论文检索与 Candidate 管理；
2. 基于已嵌入论文的 Grounded Answer；
3. 基于 Experiment Log、Session Summary 和用户偏好的实验改进；
4. 证据不足时降级到 Discovery；
5. 需要持久化的动作始终由用户确认。

Gold Set 的目标不是只评价一段回答，也不是只给整个 Agent 一个不可诊断的总分。它使用统一 Scenario Schema 描述用户旅程，再由组件、单工作流和端到端评估器分别读取同一案例的相关字段。

## 2. Design Principles

### 2.0 Repository Name Is Not A Research Domain

`graphReconstruction` 表示使用 LangGraph 重构项目的历史命名，不表示用户研究 Graph Reconstruction。

研究领域只能来自：

- 用户当前明确表达；
- 已确认的 Session Summary；
- 已确认的项目或偏好记忆；
- 用户提供的数据和实验记录。

仓库名、目录名、分支名、框架名和历史测试 Fixture 不得被提取为 `research_goal`、`task`、Query 扩展词或长期记忆。首版 Gold Set 的主领域是用户确认的一维时序模型分类与定位；跨领域泛化应使用单独标记的测试集。

### 2.1 LLM Proposes; Code Authorizes

LLM 可以：

- 将自然表达提议为结构化 Research State；
- 识别模糊意图；
- 改写检索 Query；
- 根据允许的上下文合成 Grounded Answer；
- 提议待确认的长期记忆。

确定性代码必须控制：

- Route 和 Action 白名单；
- 输入完整性；
- Candidate、Paper 和 Memory 的状态转换；
- Evidence Sufficiency Gate；
- Citation 是否来自允许的 Chunk；
- Warning、Fallback 和停止条件；
- Accept、Dismiss、Upload、Chunk、Embed 等人工边界。

### 2.2 Context Is Not Evidence

上下文和证据具有不同权限：

| 输入 | 作用 | 能否支持论文事实 |
| --- | --- | --- |
| Current Query / Experiment Log | 当前任务和最高优先级约束 | 否 |
| Session Summary | 当前研究主线、尝试、决定和未解决问题 | 否 |
| Confirmed Preference Memory | 回答风格和方案筛选偏好 | 否 |
| Retrieved Chunks | 论文事实和 Citation | 是 |
| Discovery Candidates | 待用户审查的新论文 | 否，直至 Accept、Upload、Chunk、Embed |

冲突优先级：

```text
Current Query / Experiment Log
  > Retrieved Chunks 对论文事实的描述
  > Session Summary 对用户研究状态的描述
  > Confirmed Preference Memory 对回答方式的影响
```

### 2.3 One Scenario Corpus, Multiple Evaluation Views

统一案例可以标记多个 `scope`：

```text
state
route
retrieval
answer
e2e
```

每个评估器只读取自己需要的字段。不是每个案例都必须覆盖全部层级。

## 3. Stable Routes

第一版允许的业务 Route：

```text
direct_reply
clarify
discovery
knowledge_qa
discovery_with_knowledge
experiment_improvement
experiment_discovery_fallback
memory_command
```

### 3.1 Discovery

适用于寻找新论文、最新论文或扩大资料覆盖。

输出：

- Discovery Candidates；
- 排序和推荐理由；
- Candidate 生命周期操作提示。

禁止：

- 自动 Accept；
- 把 Candidate 摘要当成 Grounded Citation；
- 自动 Upload、Chunk 或 Embed。

### 3.2 Knowledge QA

适用于用户明确要求根据已保存、已嵌入论文回答。

流程：

```text
Query Rewrite
  -> Hybrid Retrieval
  -> Evidence Sufficiency
  -> Grounded Answer | Warning
```

如果用户明确要求不要搜索新论文，则证据不足时只返回 Warning，不自动 Discovery。

### 3.3 Discovery With Knowledge

同时返回两条严格分离的结果：

- Grounded Answer：只引用本地 Retrieved Chunks；
- Discovery Candidates：作为后续资料建议。

### 3.4 Experiment Improvement

输入应能表达：

- `task`
- `model`
- `dataset`
- `metric_problem`
- `tried_methods`
- `observation`
- `goal`

流程：

```text
Natural Messages / Experiment Log
  -> Research State Extraction
  -> Hybrid Retrieval
  -> Evidence Sufficiency Gate
      -> sufficient: Grounded Improvement Answer
      -> insufficient: Experiment Discovery Fallback
```

## 4. Structured Research State

建议的最小状态：

```json
{
  "intent": "experiment_improvement",
  "research_goal": "",
  "current_hypothesis": "",
  "attempted_methods": [],
  "observed_results": [],
  "decisions": [],
  "unresolved_problems": [],
  "constraints": [],
  "preference_candidates": [],
  "source_message_ids": [],
  "updated_through_message_id": 0
}
```

要求：

- 每个非空状态项必须能追溯到 Message；
- 不得把闲聊或模型推断写成用户事实；
- 当前用户请求可以覆盖旧 Summary；
- 已否决的方法不得继续保持为 Active Decision；
- Preference Candidate 在确认前不得作为长期记忆注入 Prompt。

## 5. Session Summary Contract

Session Summary 不是普通对话摘要，而是有界的研究状态：

```json
{
  "research_goal": "",
  "current_hypothesis": "",
  "attempted_methods": [],
  "observed_results": [],
  "decisions": [],
  "unresolved_problems": [],
  "current_constraints": [],
  "updated_through_message_id": 0
}
```

Grounded Answer 的上下文顺序：

```text
System Policy
  -> Confirmed Preference Memory
  -> Session Summary
  -> Current Query / Experiment Log
  -> Retrieved Chunks
  -> Grounded Answer Output Schema
```

Session Summary 可以：

- 帮助 Query Rewrite；
- 避免重复建议已经尝试或否决的方法；
- 让回答围绕当前未解决问题组织；
- 让论文事实映射到用户正在进行的实验。

Session Summary 不可以：

- 作为论文事实来源；
- 覆盖当前用户明确表达；
- 绕过 Citation 和 Evidence Sufficiency Gate。

## 6. Hybrid Retrieval And Evidence Sufficiency

BM25 和 Dense Embedding 是检索策略，不是结构化抽取正确性的主要指标。

Hybrid Retrieval 第一版建议：

```text
Sparse Results
  + Dense Results
  -> Rank Fusion / Deduplication
  -> Retrieved Chunks
```

评估使用：

- ID-based Precision@k；
- ID-based Recall@k；
- MRR 或 nDCG；
- Noise Sensitivity。

不要直接把不同 Query 下的原始 BM25 Score 与 Cosine Score 相加后作为质量分数。融合分数需要归一化或 Rank Fusion，最终检索质量仍以 Gold Relevant Chunk IDs 判断。

Evidence Sufficiency 至少检查：

- 是否存在相关 Chunk；
- 是否覆盖当前 unresolved problem；
- 是否存在可引用的 supporting evidence；
- 是否只有噪音或过于宽泛的背景；
- 是否存在关键冲突。

第一版阈值是待 Gold Set 校准的参数，不把 `0.5` 视为事实标准。

## 7. Grounded Answer Contract

Grounded Answer 定义：

```text
evidence-grounded facts
  + session-aware reasoning
  + preference-aligned presentation
```

建议输出：

```json
{
  "answer": "",
  "evidence_status": "sufficient",
  "covered_facets": [],
  "missing_facets": [],
  "citations": [],
  "warning": null
}
```

硬约束：

- 论文事实只能来自 Retrieved Chunks；
- 关键 Claim 必须带有效 Citation；
- Summary 和 Preference 不得伪装成论文证据；
- 证据不足必须输出 Warning；
- 不重复推荐 Summary 中已经失败或明确否决的方法，除非新证据明确解释重新尝试的理由。

## 8. Evaluation Layers

### 8.1 State Extraction

硬门槛：

- Schema Validity；
- Hallucinated State Facts = 0；
- Critical Field Recall = 100%；
- Source Message Attribution 正确。

软指标：

- Exact Match；
- Set Precision / Recall / F1；
- 开放文本 Semantic Similarity；
- Temporal Consistency；
- 校准后的 LLM Judge Rubric。

Prompt Few-shot 不进入冻结 Test Set。Prompt Examples、Dev Set、Test Set 和 Human Feedback 必须分开。

### 8.2 Route And Agent Behavior

指标：

- Route Exact Match；
- Clarify Correctness；
- Tool / Action Sequence Accuracy；
- Argument Accuracy；
- Forbidden Action Violation；
- Workflow End-state Accuracy。

任何 Forbidden Action Violation 都视为案例失败，不通过加权总分抵消。

### 8.3 Retrieval And Grounded Answer

检索指标：

- Precision@k；
- Recall@k；
- MRR / nDCG；
- Context Precision / Recall；
- Noise Sensitivity。

回答指标：

- Faithfulness；
- Response Relevancy；
- Citation Validity；
- Citation Coverage；
- Unsupported Claim Count；
- Warning Correctness；
- Session Alignment；
- Preference Adherence；
- `summary_as_evidence_violation`。

### 8.4 Ablation

固定相同 Scenario 和 Retrieval Fixture，对比：

```text
A: query + chunks
B: query + chunks + session_summary
C: query + chunks + preferences
D: query + chunks + session_summary + preferences
E: query + chunks + raw recent messages
```

报告：

- 各指标均值和方差；
- Paired Win Rate；
- Token、Latency 和 Cost；
- 是否减少重复建议；
- 是否改善 unresolved problem alignment；
- 是否增加 unsupported claims。

第一版不把所有指标提前压成单一加权总分。

### 8.5 Human Review

人工使用盲测 Pairwise Comparison，优先评价：

- 是否理解当前研究主线；
- 是否避免重复或冲突建议；
- 是否给出可执行的下一步；
- 在事实同样正确时，哪个回答更有帮助。

人工反馈经审核后进入下一版本 Dev/Test Set，不直接同时写入 Prompt Few-shot 和当前冻结 Test Set。

## 9. Scorecard

先执行硬门槛：

```text
schema_valid
forbidden_action_violation == 0
invalid_citation_count == 0
critical_unsupported_claim_count == 0
route_is_allowed
```

通过后展示指标向量：

```json
{
  "component_scores": {
    "state_extraction": 0.0,
    "retrieval": 0.0,
    "grounded_answer": 0.0
  },
  "workflow_scores": {
    "experiment_improvement": 0.0
  },
  "agent_journey_success_rate": 0.0,
  "efficiency": {
    "avg_tokens": 0,
    "avg_latency_ms": 0
  }
}
```

组件分数用于调试；工作流分数用于交付判断；Agent Journey Success Rate 用于产品整体判断。

## 10. Evaluation Profiles

### Test

- 严格禁止网络；
- Fake / Deterministic Providers；
- 固定 Retrieval Fixtures；
- 临时数据库和目录；
- 执行 Schema、State、Route、Chunk ID、Citation 等确定性检查。

### Offline Eval

- 固定本地模型或显式 Evaluator；
- 执行 Faithfulness、Relevancy、Session Alignment；
- 记录 Judge Provider、Prompt Version 和重复运行结果。

### Real Eval

- 显式启用真实生成模型、Embedding 和 Judge；
- 记录 Token、Latency、Cost 和 Provider Failure；
- 不进入普通 CI。

个人 `.env` 不得覆盖 Test Profile。

## 11. Gold Set Versioning

目录角色必须分离：

```text
prompt_examples/
dev_set/
test_set/
human_feedback/
```

每次案例变更记录：

- Scenario Version；
- Label Change；
- Change Reason；
- Reviewer；
- 是否影响历史基线。

`v0` 是人工审查草案，不作为已经验证的性能结论。

领域标签也必须版本化：

```text
primary_domain: one_dimensional_time_series
primary_tasks:
  - classification
  - localization
repository_name_is_domain_signal: false
```

## 12. First Increment Scope

本次只交付：

- 本设计合同；
- 统一 Gold Scenario Schema；
- Experiment Improvement 首批案例；
- Grounded Answer、Fallback、Summary、Preference 和 Route 的评测标签。

本次不交付：

- V3 Runtime 修改；
- Ragas 依赖或 Evaluator 实现；
- Profile 配置实现；
- 真实模型分数；
- 全 Agent Journey 测试；
- 加权总分。

下一增量应先由用户审查 `v0` 场景和标签，再决定是否实现 Evaluator Harness 或修改 V3。

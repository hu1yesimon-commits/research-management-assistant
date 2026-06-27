# Research Workbench Assistant-First Design

日期：2026-06-27

> 本文档是当前 `Research Workbench` 前端收敛设计说明，不表示功能已经实现。后续实现应以本文档为范围边界：在保持 `Idea Assistant` 独立的前提下，把首页收敛成 assistant-first 的研究工作台，而不是重构成完整聊天式 agent UI。

## 1. 当前理解

当前仓库已经具备可运行的后端闭环和一版可用工作台：

- `POST /research/assistant`
  - 返回 `mode`、`route`、`coverage_score`、`route_reason`
  - 返回 `assistant_message`、`next_action`、`suggested_user_actions`
  - 返回 `discovery`、`knowledge`、`ideas`、`errors`
- `POST /research/query`
  - 作为 discovery + knowledge 的薄编排入口继续可用
- `POST /ideas/recommend`
  - 由结构化实验日志驱动，保持独立的 `Idea Assistant` 语义
- Candidate lifecycle
  - `accepted -> uploaded -> chunked -> embedded`
- Review-gated memory
  - 已有后端能力，但不适合在首页承载完整 review 流程

当前前端已经有这些面板：

- `AssistantWorkflowPanel`
- `QueryForm`
- `KnowledgePanel`
- `DiscoveryPanel`
- `CandidateLifecyclePanel`
- `IdeaAssistantPanel`

本阶段目标不是新增一套“更像 agent”的壳，而是把这些能力收敛成一个更清晰、更易讲、更适合持续演进的 `Research Workbench` 首页。

## 2. Goals And Non-Goals

### 2.1 Goals

- 把首页收敛成 `assistant-first` 的 `Research Workbench`。
- 保持 `POST /research/assistant` 为首页主入口。
- 保持 `POST /research/query` 为次入口 / fallback path。
- 把 assistant 输出拆成清晰的摘要层和结果层：
  - `Assistant Summary`
  - `Knowledge`
  - `Discovery`
- 保持 `Idea Assistant` 独立，不并入 assistant 首页主入口。
- 把 `Saved Candidates / Lifecycle` 改成默认折叠，减少首页噪音。
- 在首页加入轻量 `Memory Summary`，但不承载完整 review 操作。
- 强化“当前研究结果”和“已持久化状态”之间的语义边界。

### 2.2 Non-Goals

- 不做完整 chat UI。
- 不实现多轮对话历史。
- 不实现 SSE / streaming / checkpoint / interrupt UI。
- 不把 `Idea Assistant` 合并到 assistant 主入口。
- 不在首页做完整 memory review 流程。
- 不为了首页统一感而改写后端接口契约。
- 不把 `Saved Candidates` 直接混进当前查询结果区。
- 不把 workbench 包装成 autonomous agent 产品。

## 3. 推荐方案

本次采用 `Assistant-first Research Workbench`：

```text
Research Workbench
  -> Topbar / status
  -> Assistant Workflow (primary entry)
  -> Assistant Summary
  -> Results
       -> Knowledge
       -> Discovery
  -> Research Query (secondary entry)
  -> Saved Candidates / Lifecycle (collapsed by default)
  -> Memory Summary
  -> Idea Assistant
```

原因：

- 与当前后端契约最匹配。
- 能明确表达“assistant 负责定方向，结果区负责给证据，后续面板负责执行动作”。
- 比双入口并列更有主次。
- 比 chat-shell 更稳，更不容易在后端下一阶段重构时返工。

## 4. 信息架构

### 4.1 首页主结构

首页应分成两层：

- 首屏：决策层
- 下半区：操作层

首屏负责回答三个问题：

1. 系统如何理解这次研究请求？
2. 当前有哪些本地证据和推荐论文？
3. 下一步建议用户做什么？

下半区负责承载：

- 备用查询入口
- 论文持久化和 lifecycle 操作
- memory 轻量 summary
- idea recommendation workflow

### 4.2 首屏结构

```text
Topbar
Assistant Workflow
Assistant Summary
Results
  -> Knowledge
  -> Discovery
```

### 4.3 下半区结构

```text
Research Query
Saved Candidates / Lifecycle
Memory Summary
Idea Assistant
```

## 5. 组件职责

### 5.1 页面级编排

第一版建议继续使用当前 `ResearchWorkbench.vue` 作为 shell / page-level orchestrator，而不是在这一轮额外引入新的页面壳组件命名和迁移成本。

推荐职责：

- `ResearchWorkbench.vue`
  - 管理页面级状态
  - 管理当前结果源
  - 管理折叠区展开状态
  - 协调 summary 和独立数据刷新

### 5.2 主入口和结果区

- `AssistantWorkflowPanel`
  - 首页主入口
  - 负责提交 `/research/assistant`
  - 只处理 assistant request lifecycle

- `AssistantSummaryPanel`
  - 只展示 assistant 摘要，不展示大段证据
  - 核心字段：
    - `route`
    - `coverage_score`
    - `assistant_message`
    - `next_action`
    - `suggested_user_actions`
    - `errors`

- `KnowledgePanel`
  - 展示当前激活结果源的 grounded answer 和 knowledge sources

- `DiscoveryPanel`
  - 展示当前激活结果源的 discovery candidates
  - 保留 `Accept` 动作入口

### 5.3 次入口和延迟暴露区

- `ResearchQueryPanel`
  - 保留 `/research/query` 的直接入口
  - 作为 fallback / explicit path，而不是首页第一入口

- `SavedCandidatesDrawer`
  - 默认折叠
  - 需要时再展开处理已保存论文状态

- `MemorySummaryCard`
  - 只展示轻 summary
  - 不承载完整 review 操作

- `IdeaAssistantPanel`
  - 保持独立
  - 继续负责结构化实验日志输入和 idea recommendation

## 6. 数据流与状态边界

### 6.1 两类结果源

页面只维护两类主结果源：

- `assistantResult`
- `queryResult`

以及一个显式状态：

- `activeResultSource = "assistant" | "query"`

### 6.2 切换规则

- assistant 请求成功：
  - 写入 `assistantResult`
  - `activeResultSource -> "assistant"`
- query 请求成功：
  - 写入 `queryResult`
  - `activeResultSource -> "query"`
- 任一请求失败：
  - 不覆盖上一次成功结果

### 6.3 结果消费规则

- `AssistantSummaryPanel`
  - 只读 `assistantResult`
- `KnowledgePanel`
  - 只读当前 `activeResultSource` 对应的 `knowledge section`
- `DiscoveryPanel`
  - 只读当前 `activeResultSource` 对应的 `discovery section`
- `SavedCandidatesDrawer`
  - 独立于当前查询结果
- `MemorySummaryCard`
  - 独立于当前查询结果
- `IdeaAssistantPanel`
  - 独立于当前查询结果

### 6.4 语义边界

前端必须保持两条不同状态线：

- `当前研究结果`
  - 当前 assistant / query 返回的临时结果
- `已持久化对象`
  - candidate papers
  - paper lifecycle
  - memory summary
  - idea logs / idea outputs

这两条状态线不能在首页语义上混成一层。

## 7. 页面布局细化

### 7.1 首屏可见内容

首屏默认应可见：

- `Topbar`
- `Assistant Workflow`
- `Assistant Summary`
- `Knowledge`
- `Discovery`

首屏目标：

> 用户提交一个研究问题后，立刻知道系统怎么理解问题、给了什么证据、推荐了什么论文、下一步该做什么。

### 7.2 首屏不应优先出现的内容

以下内容不应在首屏抢占注意力：

- 大段 saved candidates 列表
- 完整 memory review 操作
- `Idea Assistant` 的大表单
- 过多系统内部状态字段

### 7.3 下半区内容

下半区按顺序放置：

1. `Research Query`
2. `Saved Candidates / Lifecycle`
3. `Memory Summary`
4. `Idea Assistant`

设计意图：

- `Research Query`
  - 作为显式 fallback path
- `Saved Candidates / Lifecycle`
  - 作为持久化和后处理区域
- `Memory Summary`
  - 作为系统状态提示，而不是首页主流程
- `Idea Assistant`
  - 作为结构化研究推进器，而不是通用首页输入

## 8. 展开 / 折叠策略

### 8.1 Saved Candidates / Lifecycle

`Saved Candidates / Lifecycle` 默认折叠。

推荐展开触发方式：

- 用户主动点击展开
- 或用户完成 `Accept` 后，前端可以给出轻提示，引导用户展开继续上传 PDF / embed

推荐文案：

- 折叠标题：`Saved Candidates & Lifecycle`
- 空状态提示：`No saved papers yet. Accept a discovery candidate to start building your local research set.`
- `Accept` 成功后的轻提示：`Paper saved. Open Saved Candidates to upload the PDF and continue embedding.`

默认不自动强制展开，避免首页变成长控制台。

### 8.2 Memory Summary

`Memory Summary` 默认展开，但仅展示轻量内容：

- pending candidate count
- confirmed semantic memory count
- 入口按钮或跳转入口

不展示：

- 详细 candidate 列表
- accept / reject / archive 的首页操作流

## 9. 交互原则

这版 workbench 必须遵守 4 条交互原则。

### 9.1 Assistant 负责定方向

用户首先通过 assistant 入口发起问题。首页先展示：

- route
- coverage
- assistant message
- next action

而不是先把低层接口结果或论文列表堆出来。

### 9.2 证据和动作分开

- `Knowledge / Discovery`
  - 负责展示这次结果
- `Saved Candidates / Lifecycle`
  - 负责后续状态推进动作

不能把这两者混成一个“既是结果又是状态机”的巨型区块。

### 9.3 默认轻量，按需展开

- lifecycle 默认折叠
- memory 只展示 summary
- idea assistant 保持独立

首页优先强调“理解与判断”，不是“所有操作都同时可见”。

### 9.4 失败可降级，不丢上下文

- 部分失败时继续展示可用 section
- 新请求失败时不清空上一次成功结果
- `Partial failure` 应被表达为“仍可继续使用另一部分结果”

## 10. 用户可感知状态

首页建议只保留 4 类用户可感知状态：

- `Ready`
- `Running`
- `Partial failure`
- `Needs action`

解释：

- `Ready`
  - 当前没有进行中的查询，页面可交互
- `Running`
  - assistant 或 query 正在执行
- `Partial failure`
  - discovery / knowledge 任一局部失败，但另一部分仍可展示
- `Needs action`
  - assistant 的 `next_action` 或 lifecycle 状态提示用户下一步操作

这样能减少碎片化状态噪音。

## 11. Memory Summary 范围

首页 `Memory Summary` 第一版建议只展示：

- pending memory candidates 数量
- confirmed semantic memory 数量
- 最近 refresh 时间或简单状态提示
- 进入详细 memory 管理页或面板的入口

数据读取策略：

- 直接读取 `GET /memory/summary`
- 页面初次加载时获取一次
- 当 memory 相关操作完成后显式刷新
- 不与 assistant / query 请求强绑定刷新

第一版不在首页做：

- candidate review list
- accept / reject inline actions
- semantic memory archive inline actions
- stale / conflict 处理入口

## 12. Idea Assistant 边界

`Idea Assistant` 继续保持独立，原因：

- 输入结构比普通 query 重
- 语义是“结构化实验推进”，不是“通用问题入口”
- 当前后端就是独立 endpoint 和独立输入模型
- 保持独立更符合可解释性和后端真实结构

首页只需要表达两点：

- `Idea Assistant` 是研究推进器
- 它不是所有查询的默认第一入口

## 13. Responsive Layout

### 13.1 Desktop

- `Assistant Summary` 独占一行
- `Knowledge` 和 `Discovery` 双栏
- `Saved Candidates` 使用整宽 drawer / accordion
- `Memory Summary` 可放在较轻的位置，不与主结果争抢主视觉

### 13.2 Mobile

全部改为单列，顺序固定为：

1. `Assistant Workflow`
2. `Assistant Summary`
3. `Knowledge`
4. `Discovery`
5. `Research Query`
6. `Saved Candidates`
7. `Memory Summary`
8. `Idea Assistant`

折叠区默认关闭，减少滚动负担。

## 14. 第一版范围

第一版实现建议只覆盖：

- assistant-first 首页结构
- `Assistant Summary` 独立展示层
- `Knowledge / Discovery` 作为主结果区
- `/research/query` 保留为次入口
- `Saved Candidates` 默认折叠
- `Memory Summary` 轻量卡片
- `Idea Assistant` 保持独立

## 15. 第一版明确不做

第一版明确不做：

- 完整 chat UI
- 多轮对话历史
- SSE / 流式响应
- assistant 自动续跑
- `Idea Assistant` 并入 assistant 主入口
- 首页直接承载完整 memory review 流程
- 为视觉统一而重写后端契约

## 16. 测试与验证

前端测试至少应覆盖：

- 首页主顺序变更后的组件渲染
- `Assistant Summary` 的字段展示
- `activeResultSource` 的切换与回退
- 新请求失败时保留上一次成功结果
- `Saved Candidates` 默认折叠
- `Memory Summary` 的轻量展示
- `Idea Assistant` 仍独立存在

验证命令：

```bash
cd frontend
npm test
npm run build
```

手动检查应至少覆盖：

- assistant 首次成功查询
- assistant 部分失败
- query fallback 成功
- Accept 后进入 lifecycle 区域的引导是否清晰
- 折叠区在 mobile 下是否可用

## 17. 面试叙事边界

可以这样表述：

> 这个前端不是完整聊天 agent，而是一个 assistant-first 的 Research Workbench。首页用 assistant 帮用户判断当前问题属于新领域探索、已有领域搜索还是下一步需要结构化实验推进；然后把结果拆成 assistant summary、knowledge evidence、discovery candidates、candidate lifecycle 和 idea assistant 几个清晰区域。这样既能展示 LangGraph workflow，又保留了研究管理工作台的可解释结构。

不应这样表述：

- 已经实现完整多轮对话研究助手
- 已经做完 streaming assistant UI
- 已经把所有研究流程统一成一个 chat shell
- memory review 已经无缝整合到首页主流中

## 18. 本轮确认结果

本轮已确认：

- 首页主入口：`Assistant Workflow`
- assistant 结果组织：`Assistant Summary + Knowledge / Discovery`
- `Idea Assistant`：继续独立
- `Saved Candidates / Lifecycle`：默认折叠
- `Memory`：首页只做轻 summary
- 第一版继续在现有 `ResearchWorkbench.vue` 上收敛，不新增页面壳命名层
- `Memory Summary` 直接使用 `GET /memory/summary`
- `Saved Candidates` 不自动展开，只通过轻提示引导进入

这些结论构成本次实现计划的固定边界。

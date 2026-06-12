# Assistant Workflow 前端展示层设计

日期：2026-06-12

> 本文档是 Research Workbench 的第一版 Assistant Workflow 前端展示设计说明，不表示功能已经实现。后续实现应以本文档为范围边界：只做 `/research/assistant` 的可视化展示层，不重构完整对话式前端。

## 1. 当前理解

当前前端已经是 Vue 3 + Vite 单页 Research Workbench：

- `ResearchWorkbench.vue` 是主页面。
- `QueryForm.vue` 调用 `POST /research/query`。
- `KnowledgePanel.vue` 展示本地知识库 grounded answer 和 sources。
- `DiscoveryPanel.vue` 展示 discovery candidates，并支持 Accept。
- `CandidateLifecyclePanel.vue` 展示 saved candidates、PDF upload、embed lifecycle。
- `IdeaAssistantPanel.vue` 单独调用 Idea Assistant。

后端现在新增了 `POST /research/assistant`：

- 使用 LangGraph 主图薄编排。
- 返回 `mode`、`route`、`coverage_score`、`route_reason`。
- 返回 `assistant_message`、`next_action`、`suggested_user_actions`。
- 返回 `discovery`、`knowledge`、`ideas`、`errors`。

本阶段目标是在现有 Workbench 上方新增一层 Assistant Workflow 展示，让用户能看到后端 Agent Workflow 的 route、coverage、message 和 next action，同时继续复用现有 discovery / knowledge / lifecycle 展示。

## 2. Goals And Non-Goals

### 2.1 Goals

- 新增 `AssistantWorkflowPanel` 作为当前 Workbench 顶部的 assistant 展示区。
- 新增前端 API helper：`researchAssistant(payload)` 调用 `POST /research/assistant`。
- 展示 assistant response 的核心字段：
  - `mode`
  - `route`
  - `coverage_score`
  - `route_reason`
  - `assistant_message`
  - `next_action`
  - `suggested_user_actions`
  - `errors`
- Assistant 查询成功后，将 response 中的 `discovery` 和 `knowledge` 传给现有 `DiscoveryPanel` 与 `KnowledgePanel`。
- 第一版在 `AssistantWorkflowPanel` 内简洁展示 `ideas`，不改 `IdeaAssistantPanel`。
- 保留现有 `/research/query` 查询入口，作为 legacy / current workbench query path。
- 保持前端默认工作台风格，不做 landing page。

### 2.2 Non-Goals

- 不做完整 chat UI。
- 不保存多轮对话历史。
- 不实现 checkpoint / SSE / MCP UI。
- 不重构 Candidate Lifecycle。
- 不删除 `/research/query` 前端入口。
- 不把 `next_action` 按钮做成真实多轮自动续跑。
- 不把 `research_idea` 结构化实验日志表单塞进第一版 assistant panel。

## 3. 推荐设计

采用方案 A：

```text
ResearchWorkbench
  -> topbar
  -> AssistantWorkflowPanel
  -> existing /research/query QueryForm
  -> KnowledgePanel + DiscoveryPanel
  -> CandidateLifecyclePanel
  -> IdeaAssistantPanel
```

Assistant panel 是一个独立的顶部面板，负责展示新的 `/research/assistant` 后端契约；当前 Workbench 其他部分保持可用。

## 4. Interaction 设计

### 4.1 Assistant 输入

`AssistantWorkflowPanel` 第一版包含：

- `query` textarea
- `intent` select：
  - `auto`
  - `search`
  - `research`
- `top_k` number input
- `Run Assistant` button

第一版不提供完整结构化 experiment log 表单。若用户选择 `intent=research`，panel 展示提示：当前 research idea 的结构化日志仍通过下方 `IdeaAssistantPanel` 提交；后续可把结构化日志表单整合进 assistant panel。

理由：

- 结构化实验日志字段较多。
- 现在已有 `IdeaAssistantPanel` 可用。
- 第一版重点是展示 Agent Workflow route，不是重做 Idea Assistant 表单。

### 4.2 Assistant 输出

查询成功后展示：

- `mode` badge：`basic` / `advanced`
- `route` badge：`basic_explore` / `advanced_ready` / `advanced_search` / `research_idea`
- `coverage_score`：百分比或三位小数
- `route_reason`
- `assistant_message`
- `next_action`：
  - type
  - options
  - message
- `suggested_user_actions` 列表
- `errors` 列表

展示 copy 应简洁，不解释所有实现细节。

### 4.3 Discovery / Knowledge 复用

`ResearchWorkbench` 持有两个 response：

- legacy `queryResponse`：来自 `/research/query`
- new `assistantResponse`：来自 `/research/assistant`

第一版推荐显示逻辑：

- 如果最近一次成功调用的是 assistant，则 `KnowledgePanel` 和 `DiscoveryPanel` 使用 `assistantResponse.knowledge` / `assistantResponse.discovery`。
- 如果最近一次成功调用的是 legacy query，则继续使用 `queryResponse.knowledge` / `queryResponse.discovery`。
- panel 顶部可显示当前结果来源：`assistant` 或 `research/query`。

这样可以保留旧入口，同时让新 assistant 结果自然进入现有展示区。

### 4.4 Ideas 展示

`AssistantWorkflowPanel` 内部简洁展示 assistant response 的 `ideas`：

- title
- rationale
- suggested_validation_metric
- next_small_experiment

第一版不做 idea selection、search_plus 或多轮续跑。

## 5. Error Handling

- `researchAssistant()` 请求失败时，在 `AssistantWorkflowPanel` 内显示 endpoint-level error。
- assistant response 中的 `errors` 以 compact list 展示，包含 `section` 和 `message`。
- `discovery.error` 和 `knowledge.error` 仍由现有 panels 展示。
- 不让 assistant error 覆盖 legacy `/research/query` 的结果；只有 assistant 成功返回后才切换结果来源。

## 6. Files

预计新增：

- `frontend/src/components/AssistantWorkflowPanel.vue`
- `frontend/src/components/__tests__/AssistantWorkflowPanel.test.js`

预计修改：

- `frontend/src/api.js`
  - 新增 `researchAssistant(payload)`
- `frontend/src/components/ResearchWorkbench.vue`
  - 引入 `AssistantWorkflowPanel`
  - 增加 assistant state
  - 用 `activeResultSource` 决定 knowledge/discovery panel 使用哪个 response
- `frontend/src/styles.css`
  - 为 assistant 面板补充少量样式，复用现有 `.panel`、`.badge`、`.alert`、`.stack-list`
- 可选修改：
  - `frontend/src/components/__tests__/IdeaAssistantPanel.test.js`
    - 如果 ResearchWorkbench 结构变化影响现有集成测试，只做最小更新。

## 7. Testing

前端测试至少覆盖：

- `researchAssistant(payload)` 调用 `/research/assistant`。
- `AssistantWorkflowPanel` 渲染：
  - mode / route / coverage_score
  - assistant_message
  - next_action
  - errors
  - ideas
- `AssistantWorkflowPanel` submit 时发出或调用 assistant 请求。
- `ResearchWorkbench` 在 assistant 成功后把 `knowledge` / `discovery` 结果切换到 assistant response。
- legacy `/research/query` 入口仍可用。

验证命令：

```bash
cd frontend
npm test
npm run build
```

如果需要手动查看：

```bash
cd frontend
npm run dev -- --host 127.0.0.1
```

## 8. 面试叙事边界

可以这样表述：

> 前端第一版没有做完整聊天系统，而是在现有 Research Workbench 上方新增 Assistant Workflow 展示层。它直接展示后端 LangGraph 主图返回的 mode、route、coverage score、assistant message 和 next action，并把 discovery / knowledge sections 复用到现有面板中。这样既能展示 Agent Workflow，又保留了原有文献管理和知识库工作台的稳定功能。

不能这样表述：

- 已经实现完整多轮对话系统。
- 已经实现 checkpoint / SSE / MCP UI。
- 已经实现 search_plus。
- 已经把 Idea Assistant 完全合并进 assistant panel。

## 9. Open Decisions

已确认：

- 第一版采用方案 A。
- 不重构完整 chat UI。
- 保留 `/research/query` 入口。
- 不动 lifecycle 和现有 Idea Assistant 主路径。
- `ideas` 只做简洁展示。

实现计划需要细化：

- `AssistantWorkflowPanel` 是自己调用 API，还是由 `ResearchWorkbench` 传入 handler。
- `ResearchWorkbench` 如何标记最近结果来源。
- 现有组件测试中哪些需要最小更新。

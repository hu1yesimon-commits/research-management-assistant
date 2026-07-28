# Provider rollout register

日期：2026-07-12  
决策：产品运行以真实 provider 为目标；fake/deterministic 仅作为测试 profile、演示兜底和故障诊断工具。

本文件不是“已可用”声明。任何服务只有通过对应 smoke、失败降级和可观测性验收后，才能被标为稳定。

## 当前接入与待验证项

| 服务 | 当前代码接入 | 已知接口/运行风险 | 上线前验收 |
| --- | --- | --- | --- |
| DeepSeek Judge | `ChatOpenAI` + `DEEPSEEK_BASE_URL` / key | 依赖 OpenAI-compatible 协议、模型名、密钥和网络；单篇 judge 失败会降级，需确认降级在 UI 可见 | 有效/无效 key、429、超时、格式异常各一条真实 smoke；记录 request id、延迟、模型名 |
| DeepSeek Answer | `ANSWER_PROVIDER=deepseek` | 当前没有流式输出；provider 故障必须和“本地没有证据”区别展示 | 以 embedded 文献跑 grounded-answer 真实 smoke；核验 source 引用未被模型伪造；失败返回 typed error |
| DeepSeek Leader response | `LEADER_RESPONSE_PROVIDER=deepseek`，代码默认值为 deepseek | 当前失败后会 deterministic fallback；如果无 timeout，调用可能拖住整条同步 turn | 检查 key/base URL/model；设定 connect/read timeout；UI 显示 fallback/provider failure；测超时返回 |
| OpenAI Answer | `ANSWER_PROVIDER=openai` | 依赖运行环境的 OpenAI credentials；代码未提供独立预检或成本控制 | 明确 API key 来源、模型白名单、成本上限与真实 smoke |
| BGE-M3 | `SentenceTransformer(BAAI/bge-m3)` | 首次下载/模型缓存/CPU 内存与启动时间；模型加载失败会让请求失败 | 固定模型版本与本地缓存策略；用真实 PDF 测 embed、重启后查询和耗时 |
| Chroma | `PersistentClient(CHROMA_PERSIST_DIR)` | SQLite 的 `vector_ref` 与 Chroma 目录/collection 必须一致；目录误切换会造成“已 embedded 但查不到” | 重启后检索 smoke；collection/schema 版本记录；清理/重建流程；磁盘容量告警 |
| arXiv | curl 调用 export API | 依赖系统 curl；限速睡眠发生在同步请求内；网络或 XML 变化会变成空结果 | curl 缺失、超时、限流、空 XML 的 UI/trace；记录 source status，不把空结果误报为无论文 |
| OpenAlex | `requests.get` title enrichment | top-result 可能不是精确匹配；429/网络失败返回 `None`，当前调用方必须保留 source status | 对 exact/weak match 做人工抽样；429/超时 smoke；把 match type/confidence 传给前端/trace |

## 统一验收契约

每个真实 provider 在正式启用前必须满足：

1. 明确环境变量、模型名、base URL 与启动预检；不得靠隐式 shell 状态猜测。
2. 有独立的真实 smoke，不与普通 pytest 混跑。
3. 有 connect/read timeout、可恢复错误类型和用户可见的降级说明。
4. 记录 provider、model、duration、fallback 与错误类别；不记录密钥或完整敏感 payload。
5. 对会改变事实质量的输出保留证据边界：discovery 不能冒充 grounded source，LLM 不得伪造 citation。

## 当前阻塞顺序

1. 先修复同步 timeout 的真实 deadline 语义，再把 Leader/Answer 作为默认真实调用。
2. 建立 `real` 与 `test` 两套显式 profile；test profile 强制 fake/deterministic，real profile 启动时预检全部配置。
3. 为 DeepSeek Leader、Answer、BGE-M3 + Chroma、arXiv/OpenAlex 逐项跑 smoke 并记录结果。
4. 通过后再改 UI 文案为“已接入稳定服务”，否则只称“已接入、待验收”。

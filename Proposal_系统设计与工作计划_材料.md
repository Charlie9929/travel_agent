# AI 旅行助手 Proposal：系统设计与工作计划材料

> 用途：提供给 PPT 制作同学。覆盖课程 Proposal 第二部分中除“技术栈、数据源”以外的内容：AI 的作用、主要风险、缓解方案、验证计划、团队分工、工作计划，以及架构/流程图。
>
> 当前状态：这是 2026 年 10 月 10 日开题展示用的 **proposal baseline**，不是最终执行计划。文末已单列需要在用户调研和功能定稿后更新的部分。

---

## 0. 当前范围假设

根据课程选题要求与团队现有《分工与计划_v4》，Proposal 阶段建议把核心承诺压缩为一条可验证闭环：

```text
输入旅行需求
→ 提取结构化约束
→ 查询并标注外部信息
→ 生成行程草案
→ 用规则检查时间、预算和路线
→ 用户编辑或改变约束
→ 系统解释并更新行程
→ 用户确认
→ 打开地图路线或创建日历事件
→ 返回执行结果
```

建议将以下内容作为 **baseline**：

- 生成、编辑、保存结构化行程；
- 检查时间冲突、预算和路线可行性；
- 用户改变一个约束后重新规划，并展示变化；
- 完成一次真实地图或日历动作；
- 保留信息来源与查询时间，将实时/引用信息和估算信息分开。

建议将以下内容暂列为 **candidate extensions**，不要在 Proposal 中全部承诺为必交：攻略文本导入、天气变化自动重规划、酒店/航班管理、OCR 截图识别、多人协作、附近推荐、详细预算统计、复杂路线优化。

---

# 1. AI 的作用（Role of AI）

## 1.1 一句话定位

**AI is used for understanding, planning, and explanation; deterministic services are used for facts, calculations, validation, storage, and external actions.**

中文解释：AI 负责理解用户意图、生成候选方案和解释修改；地图/天气等工具负责提供事实，规则与代码负责计算和校验，用户负责最终确认。

## 1.2 AI 与确定性模块的职责边界

| 环节 | AI 负责 | 非 AI 模块负责 | 这样划分的原因 |
|---|---|---|---|
| 需求理解 | 从自然语言中提取日期、出发地、预算、人数、兴趣、步行偏好等；缺信息时追问 | 类型、范围、必填项校验 | 自然语言有歧义，但字段合法性可以用代码确定 |
| 攻略理解（候选增强） | 从用户粘贴的文本中提取地点、餐厅、建议时长和标签 | 文本长度限制、恶意内容隔离、地点实体核验 | AI 擅长抽取；外部文本不能被当作系统指令 |
| 行程生成 | 根据结构化约束形成候选日程，给出安排理由 | 时间运算、预算求和、路线时长、营业时间检查 | 模型可以提出方案，但不应自行断言实时事实 |
| 交互修改 | 理解“少走路”“把博物馆换到第二天”等修改，解释前后差异 | 保留版本、计算差异、重新运行规则检查 | AI 负责语义与解释，代码保证结果一致性 |
| 路线优化 | 在多个可行方案之间给出偏好理由 | 地图路线矩阵、排序算法、硬约束校验 | 路线距离和时长应以工具结果为准 |
| 外部动作 | 把确认后的计划转为地图/日历所需参数 | 预览、权限检查、幂等控制、真正调用 API、返回成功/失败状态 | 防止 AI 未经确认执行错误或重复动作 |

## 1.3 AI 不应承担的职责

- 不凭记忆提供营业时间、票价、天气、实时交通等易变化事实；
- 不绕过确定性规则直接宣布“预算可行”或“路线无冲突”；
- 不在用户确认前创建、删除或修改日历事件；
- 不直接执行模型生成的代码、SQL、URL 或任意工具参数；
- 不把估算价格表述为已验证报价；
- 不隐藏缺失信息和不确定性。

## 1.4 PPT 可直接使用的英文文案

**Role of AI**

- Understand natural-language travel needs and convert them into structured constraints.
- Generate a candidate itinerary and explain why each item is included.
- Revise the itinerary when a user changes a preference and summarize the differences.
- AI does not act as the source of truth: maps, weather, calculations, and rule checks verify the plan.
- External actions require an explicit user preview and confirmation.

---

# 2. 推荐架构与完整工作流

## 2.1 架构图（可交给 PPT 同学重绘）

```mermaid
flowchart LR
    U[User] --> UI[Web UI\ninput / edit / confirm]
    UI --> API[Backend API & Trip Store]
    API --> ORC[Agent Orchestrator]
    ORC --> LLM[LLM\nunderstand / plan / explain]
    ORC --> EXT[External Tools\nmaps / places / weather]
    LLM --> VAL[Deterministic Validator\ntime / budget / route / schema]
    EXT --> VAL
    VAL -->|pass| API
    VAL -->|conflict + evidence| ORC
    API --> UI
    UI -->|explicit confirmation| ACT[Action Adapter\nmap or calendar]
    ACT --> LOG[Status & Audit Log]
    LOG --> UI
```

## 2.2 图中必须强调的四个控制点

1. **Source grounding**：外部事实带来源和查询时间；估算值明确标记为 estimate。
2. **Deterministic validation**：预算、时间重叠、路线时长、字段格式等不用 LLM 自我判断。
3. **Human confirmation**：地图/日历动作前展示预览，并由用户确认。
4. **Failure recovery**：API 超时、无结果或模型输出非法时，保留用户输入，显示可恢复错误，不伪造成功。

## 2.3 PPT 可直接使用的英文图注

**The LLM proposes; tools provide current facts; deterministic checks validate; the user confirms; the system records the result.**

---

# 3. 主要风险、缓解方案与验证计划

## 3.1 PPT 主表：六个优先风险

| ID | Main risk | Mitigation | Planned verification / pass criterion |
|---|---|---|---|
| R1 | Hallucinated or stale travel facts | Ground factual fields in tools; show source and query time; label estimates; never let the model invent missing values | 20 representative plans; at least 95% of factual fields traceable to a source; 0 invented opening hours or quoted prices in the test set |
| R2 | The itinerary violates time, budget, route, or user constraints | Convert requests to structured constraints; validate by code; return conflicts to a repair loop; keep hard and soft constraints separate | Boundary and conflict tests; 100% detection of defined hard-constraint violations; at least 90% overall conflict-detection recall on the pilot set |
| R3 | External APIs are slow, unavailable, rate-limited, or return no result | Timeout, retry with backoff, cache where permitted, quota/cost alerts, and a clear degraded mode | Inject timeout, 429, empty-result, and invalid-key failures; 0 crashes; 100% of injected failures show a recoverable status and do not claim success |
| R4 | An incorrect or duplicate external action is executed | Preview + explicit confirmation; least privilege; allowlisted actions; idempotency key; action log; cancel/retry states | 20 action tests; 0 writes before confirmation; 0 duplicate calendar events after repeated clicks/retries; every action has a final status |
| R5 | Prompt injection or unsafe model output from imported guides/web content | Treat external text as untrusted data; separate instructions from content; schema validation; sanitize outputs; validate every tool parameter | Red-team with at least 10 injection/unsafe-output cases; 0 unauthorized tool calls, secret exposure, or executable model output |
| R6 | Scope and integration risk across six members | Freeze the core workflow and shared data contract first; use mock data; integrate one vertical slice early; keep extensions behind priorities | A vertical-slice acceptance test runs end-to-end before optional features; API/schema contract tests pass; each module has an owner and handoff artifact |

> 说明：表中的数字是 Proposal 阶段的“初始验收目标”，不是已经取得的结果。正式开发后应根据试点难度和用户研究结果校准，但任何涉及未经确认的外部动作、泄露密钥或伪造成功的指标仍应保持为 0。

## 3.2 完整风险登记表（答辩与附录用）

### R1. 模型幻觉与信息过期

**风险表现**

- 模型生成不存在的景点、错误地址、错误营业时间或看似精确的价格；
- 将历史信息当成当前信息；
- 用户因自动化偏见而过度相信“看起来完整”的行程。

**缓解方案**

- 把地点 ID、地址、营业时间、路线时长、天气、票价等标为“必须由工具提供或人工输入”的字段；
- 每条易变化事实保留 `source`、`queried_at`、`value_type = quoted | estimated`；
- 无来源时显示“未核实”，不让模型补值；
- UI 显示冲突、不确定性和数据时间；
- 对事实字段做二次校验，必要时要求用户确认。

**验证方法**

- 建立 20 个代表性旅行任务，人工制作事实基准；
- 统计事实可追溯率、错误事实数、过期信息提示率；
- 对 API 返回空值、旧时间戳、互相冲突的来源做异常测试。

**初始通过标准**

- ≥95% 的事实字段可追溯到工具结果或明确的用户输入；
- 测试集中“凭空生成的营业时间/已报价价格”为 0；
- 所有估算价格都有 estimate 标签。

### R2. 行程违反用户约束或现实约束

**风险表现**

- 超预算、活动时间重叠、闭馆后到达；
- 交通时间不足；
- 用户要求少步行，但方案安排了长距离步行；
- 修改一个约束后，旧约束残留或产生新冲突。

**缓解方案**

- 将日期、预算、人数、步行上限等转换为结构化约束；
- 区分 hard constraints（不可违反）和 soft preferences（用于排序）；
- 使用代码计算预算、时间间隔和路线时长；
- 模型输出后运行 validator，冲突信息返回给规划器修复；
- 仍无法满足时，明确告诉用户哪条约束不可同时满足。

**验证方法**

- 单元测试：时间重叠、跨日、零/负预算、缺失地点、营业时间边界；
- 属性/组合测试：随机生成多组日期、预算和活动数量；
- 端到端测试：修改预算、出发时间或步行偏好后重新规划；
- 人工评审软偏好是否得到合理体现。

**初始通过标准**

- 已定义的 hard-constraint 违规检测率 100%；
- 试点集总体冲突检测召回率 ≥90%；
- 无法满足时不输出“已满足全部条件”。

### R3. 地图、天气或其他外部服务失败

**风险表现**

- 超时、429 限流、配额耗尽、认证失败、无搜索结果；
- API 成本失控；
- 某地区或交通方式不受支持；
- 不同时间查询得到不同路线，测试结果不稳定。

**缓解方案**

- 为每次请求设置超时；仅对可重试错误做有限次数重试和指数退避；
- 在许可范围内缓存稳定结果，记录查询时间；
- 设日配额、成本告警和调用日志；
- 提供 degraded mode：保留草案，但明确“未完成路线/天气核验”；
- 自动化测试用 mock 响应，少量端到端测试调用真实服务。

**验证方法与通过标准**

- 注入 timeout、429、401/403、空结果、字段缺失；
- 0 崩溃，0 伪造成功；
- 100% 注入失败显示具体且可恢复的状态；
- 失败后用户输入与已有行程不丢失；
- 记录每次外部调用的类型、耗时、状态和成本估算。

### R4. 外部动作错误、重复或越权

**风险表现**

- 错日期、错时区、错地点被写入日历；
- 用户双击或重试造成重复事件；
- 模型在用户确认前执行动作；
- 工具权限过大，导致超出本项目范围的操作。

**缓解方案**

- 采用 plan → preview → explicit confirm → execute → verify 的动作状态机；
- 外部动作只接受经过 schema 和权限校验的参数；
- 限定可用工具和最小权限；
- 使用 idempotency key 或本地去重记录；
- 写入后读取/检查结果，并显示 success / failure / pending；
- 对删除和覆盖操作要求更强的二次确认。

**验证方法与通过标准**

- 20 个动作场景覆盖取消、重复点击、网络重试、错误时区和权限拒绝；
- 用户确认前外部写入为 0；
- 重复点击/重试产生的重复事件为 0；
- 每次动作都有可追踪的最终状态。

### R5. 提示词注入与不安全输出

**风险表现**

- 攻略文本或网页内容包含“忽略之前指令”等恶意内容；
- 模型把不可信文本转换为工具调用；
- 模型输出未经处理直接进入 HTML、数据库或外部 API。

**缓解方案**

- 把用户/网页内容作为 data，而不是高优先级 instruction；
- 导入文本与系统指令分区，限制长度和允许提取的字段；
- 所有模型输出先做 JSON Schema、枚举、长度、URL 和坐标校验；
- 外部工具采用 allowlist 和最小权限；
- 前端做上下文相关编码，后端使用参数化查询；
- 不在提示词中放 API key、访问令牌或敏感数据。

**验证方法与通过标准**

- 至少 10 个红队样本：忽略指令、诱导泄露密钥、任意 URL、脚本/SQL、伪造工具结果；
- 未授权工具调用、敏感信息泄露、可执行模型输出均为 0；
- 所有拒绝或清洗行为有日志可复现。

### R6. 隐私、密钥和日志泄露

**风险表现**

- 行程可能暴露日期、位置、住宿等敏感信息；
- API key 被放入前端或提交到 Git；
- Prompt/错误日志保存了不必要的个人信息。

**缓解方案**

- 数据最小化：只收集当前流程必需字段；
- API key 仅保存在服务端环境变量，按 API/来源限制权限；
- 日志脱敏，不记录完整令牌或不必要的旅行细节；
- 为样例演示使用合成或去标识数据；
- 明确保存、删除和导出的行为。

**验证方法与通过标准**

- 仓库 secret scan 与前端构建产物检查；
- 日志抽查；未授权读取/修改测试；
- Git 和前端包中有效密钥为 0；
- 日志中完整令牌为 0；
- 删除旅行后，系统不再从普通接口返回该行程。

### R7. 模型输出不稳定、格式错误、延迟或成本过高

**风险表现**

- 同一输入生成结构不同，前后端联调失败；
- 返回非 JSON、缺字段或字段类型错误；
- 长攻略导致响应慢、Token 费用高；
- 模型升级后行为回退。

**缓解方案**

- 使用严格结构化输出与版本化 JSON Schema；
- 对模型/Prompt/Schema 版本做记录；
- 建立固定回归集，在每次 Prompt 或模型变更后重跑；
- 限制输入长度，长文本分块；
- 对超时和格式错误采用有限重试；开发阶段保留 mock 响应；
- 记录延迟、Token 和估算成本。

**验证方法与初始目标**

- 30 个正常、边界和异常输入，每个关键样本重复运行；
- schema-valid rate ≥98%，所有 invalid output 均被捕获；
- 交互修改成功率和约束满足率不低于首轮基线；
- 延迟和单次成本先在 pilot 中测量，再确定正式 p95/预算阈值。

### R8. 范围过大与跨角色集成失败

**风险表现**

- 同时做攻略、天气、酒店、交通、路线优化和日历，导致核心流程未闭环；
- 前端、后端、Agent 和设计各自完成，但接口不一致；
- 到后期才第一次联调。

**缓解方案**

- 先冻结 baseline 和一条主流程；
- 接口与数据结构先行，变更必须留记录；
- 前端、后端、Agent 均用相同 mock fixture 并行开发；
- 尽早做一个 vertical slice，而不是先完成每个模块的全部功能；
- 增强功能按 Must / Should / Could 排序，核心验收通过后才进入。

**验证方法与通过标准**

- 在可选功能前，完成一次从输入到地图/日历动作的端到端验收；
- API contract tests 与 schema tests 自动运行；
- 每周至少一次集成演示；
- 每个模块都有 owner、输入/输出、完成定义和交接材料。

---

# 4. 验证计划（Verification Plan）

## 4.1 测试金字塔

| 层级 | 验证内容 | 示例 | 主要指标 |
|---|---|---|---|
| Unit tests | 确定性规则与数据处理 | 时间重叠、预算求和、日期/时区、schema 校验 | pass rate；边界覆盖 |
| Contract tests | 前端—后端—Agent 的接口一致性 | 请求/响应字段、错误码、版本兼容 | schema-valid rate = 100% for service contracts |
| AI eval set | 模型理解、生成和修改行为 | 缺信息追问、约束提取、改变预算后重规划 | constraint extraction F1；hard-constraint pass rate；human rating |
| Integration tests | 真实模块连接 | 地图/天气查询、保存读取、模型+validator repair loop | success rate；latency；failure recovery |
| End-to-end tests | 完整用户任务 | 输入→生成→修改→确认→地图/日历动作 | task completion rate；no unauthorized action |
| Usability tests | 用户是否看得懂、改得动、敢确认 | 任务观察 + 简短访谈 | completion time；error rate；SUS/简化评分；主要困惑点 |
| Red-team / failure tests | 安全和异常 | prompt injection、429、空结果、重复点击 | unauthorized actions = 0；false success = 0 |

## 4.2 建议的最小评测集

至少准备 20 个固定任务，覆盖：

- 5 个正常任务：不同天数、预算、兴趣；
- 5 个约束冲突任务：预算过低、活动重叠、营业时间不可能、交通不足、步行要求冲突；
- 3 个缺信息任务：缺日期、缺出发地、偏好模糊；
- 3 个修改任务：改预算、改出发时间、改为少步行；
- 2 个外部服务失败任务：超时、无结果/限流；
- 2 个安全任务：恶意攻略文本、重复确认/重复点击。

每条样本保存：输入、预期结构、必须满足的硬约束、允许变化的软偏好、外部工具 fixture、实际输出、失败原因、模型/Prompt/Schema 版本。

## 4.3 核心量化指标

1. **Constraint extraction accuracy**：用户明确表达的约束被正确提取的比例。
2. **Hard-constraint satisfaction rate**：最终行程满足硬约束的比例。
3. **Conflict-detection recall**：测试集中已知冲突被发现的比例。
4. **Source traceability**：易变化事实能追溯到来源及查询时间的比例。
5. **Schema-valid rate**：Agent 输出通过结构校验的比例。
6. **Task completion rate**：用户能否完成生成、修改、确认和动作执行。
7. **Unsafe-action rate**：未确认/越权/重复外部动作比例，目标为 0。
8. **Failure transparency**：失败时是否显示真实状态，而非伪造成功，目标为 100%。
9. **Latency and cost**：p50/p95 响应时间、每次生成的 Token 与成本；先测基线，再定阈值。

## 4.4 一条可在最终展示中复用的验收场景

```text
Given:
  用户从广州出发，旅行 2 天，预算 1500 元，希望少走路。

When:
  系统生成行程；用户将预算改为 1200 元；
  系统解释删改内容并重新检查时间、预算和路线；
  用户确认后选择“打开地图路线”或“创建日历事件”。

Then:
  行程结构完整；硬约束无冲突；事实带来源/时间；
  修改前后差异可见；外部动作只在确认后执行；
  最终状态显示成功或具体失败原因。
```

---

# 5. 团队分工

## 5.1 Proposal 阶段的六人分工

按当前分配，不填写姓名时可在 PPT 中先用角色代称：

| 成员 | Proposal 责任 | 交付物 |
|---|---|---|
| Technical A + Design A | 合作制作与整合 PPT | 英文叙事、统一版式、架构/流程图、引用、排练稿、最终 PDF |
| Technical B | 技术栈与数据源 | 技术栈选择、外部数据/API、成本/配额与可行性依据 |
| Technical C（你的部分） | AI 的作用；主要风险、缓解方案与验证计划 | AI/规则边界、风险主表、测试矩阵、验收指标、答辩备份页 |
| Design B | 用户故事与主业务流程 | 2–3 条用户故事、1 条完整主流程、关键交互节点 |
| Design C | 现实背景与竞品分析 | 目标用户背景、痛点证据、相关工作、竞品差距 |

### 建议的交叉评审

- Technical B 审查风险表中的 API、成本与可行性表述；
- Design B 审查风险和验证是否覆盖真实用户任务；
- Technical C 审查 PPT 中 AI 能力是否有夸大承诺；
- Design A 负责把“失败、确认、来源、可编辑”等信任机制在界面图中可视化；
- 全员都要能解释完整系统，而不仅是自己的页。

## 5.2 开发阶段的长期角色映射

与《分工与计划_v4》保持一致：

- 技术 1：Web 前端与地图/时间轴/编辑交互；
- 技术 2：后端、数据库、地图/天气接口与数据校验；
- 技术 3：LLM、Prompt、结构化输出、规划/解析、冲突检测与 Agent 评测；
- 设计 1：核心页面 UI；
- 设计 2：编辑、拖拽、错误/确认/空状态等交互；
- 设计 3：视觉规范、组件库、地图 Marker 和天气样式。

---

# 6. 工作计划

## 6.1 10 月 10 日 Proposal 前的冲刺计划

| 日期 | 目标 | 具体产物 | 负责人/参与者 |
|---|---|---|---|
| 10/7 | 内容齐套 | 六个部分的材料初稿、来源链接、风险与测试主表 | 各模块负责人 |
| 10/8 上午 | 范围冻结 | Baseline / extensions、2–3 用户故事、主流程、AI 边界、核心数据流达成一致 | 全员 |
| 10/8 下午 | 第一版 PPT | 英文页面、架构/流程图、引用和备注页 | PPT 两位负责人 + 内容负责人 |
| 10/9 上午 | 可行性审查 | 删除无法证明或过度承诺的内容；统一术语和指标 | 三位技术 + 三位设计交叉评审 |
| 10/9 下午 | 彩排与问答 | 控时、英文表达、每人可解释整体；整理评委可能追问 | 全员 |
| 10/10 展示前 | 最终检查 | PDF、字体、图示、引用、备份文件、演示顺序 | PPT 负责人 + 联系人 |

## 6.2 Proposal 后的实施计划（相对阶段，不绑定最终功能）

### Phase 1 — Scope and contract

- 用用户调研结果确定主要用户、场景、地区/旅行类型和 Must/Should/Could；
- 冻结第一版 Trip / Place / ItineraryItem / Constraint schema；
- 定义 API、错误码、Agent 输入输出、评测集与验收指标；
- 设计关键页面和失败/确认状态。

**Exit criterion**：同一份 mock fixture 能被前端、后端和 Agent 使用。

### Phase 2 — Parallel prototypes

- 前端：用 mock data 完成创建、时间轴、编辑、确认和状态界面；
- 后端：完成 Trip/Itinerary CRUD、外部服务 adapter、mock Agent；
- Agent：完成约束提取、结构化行程生成、基础 repair loop；
- 设计：完成核心页面、组件和关键交互状态。

**Exit criterion**：每个模块能独立演示，接口与 schema 通过 contract tests。

### Phase 3 — First vertical slice

- 连接“输入 → 生成 → 校验 → 显示 → 编辑 → 保存”；
- 只支持一个有限地区或旅行类型；
- 同时接入一项真实地图能力。

**Exit criterion**：一条主流程端到端可运行；失败时不丢数据、不伪造结果。

### Phase 4 — Revision and action

- 支持用户改变一个约束并展示前后差异；
- 接入地图或日历中的一个真实动作；
- 加入 preview、confirmation、idempotency 与执行状态。

**Exit criterion**：课程示例场景可完整完成，且未确认动作测试为 0。

### Phase 5 — Verification and user pilot

- 跑固定 AI eval set、单元/接口/集成/端到端与红队测试；
- 让目标用户完成核心任务，记录时间、错误和困惑；
- 根据结果调 Prompt、约束、交互和优先级。

**Exit criterion**：Must-have 验收指标达标；已知限制和失败案例有记录。

### Phase 6 — Extensions and final evidence

- 只有核心流程稳定后才加入天气重规划、攻略导入、OCR、多人偏好等增强项；
- 整理可复现实验、失败处理、成员贡献、AI 使用记录、最终报告和演示视频。

**Exit criterion**：代码、README、运行步骤、测试证据、最终 PPT/报告/视频形成一套可检查交付。

---

# 7. 哪些内容会随用户调研和功能定稿改变

## 7.1 高概率变化：必须在调研后更新

| 当前材料 | 为什么可能变化 | 调研/定稿后要更新什么 |
|---|---|---|
| 目标用户与旅行场景 | 学生自由行、家庭出游、老年用户、商务出差的约束差异很大 | 主要 persona、地区/旅行类型、使用频率与关键痛点 |
| 约束字段 | 用户未必关心同一组参数；“少走路”可能比“预算”更重要，也可能需要无障碍、饮食或儿童约束 | hard/soft constraints、必填项、追问顺序、默认值 |
| 核心输入方式 | 用户可能更愿意粘贴攻略、发截图，或只输入一句话 | 自然语言、文本导入、OCR、表单之间的优先级 |
| 主业务流程 | 用户可能先浏览候选地点再排程，而不是一次生成完整行程 | 页面顺序、编辑方式、确认点与失败恢复路径 |
| 地图还是日历动作 | 真实需求和开发可行性会决定先实现哪一个 | Action adapter、权限、确认文案和动作测试 |
| 天气、酒店、交通的优先级 | 可能是核心痛点，也可能只增加复杂度 | Must/Should/Could、数据字段、界面和测试集 |
| 路线优化目标 | 最短距离、最少步行、最低费用、少换乘的优先级不同 | 优化目标、权重、解释方式和评价指标 |
| 风险优先级 | 功能不同会引入不同风险，例如 OCR 有识别错误，多人协作有冲突与权限 | 风险发生概率、严重度、owner、测试样本 |
| 数值验收阈值 | 目前的 95%、90%、98% 是开题目标，需要用 pilot 建立真实基线 | 指标定义、样本量、阈值、置信度与失败分布 |
| 时间表与人员负荷 | 最终截止日、课程节奏、API 审批与个人技能会影响工期 | 每阶段时长、负责人、依赖、缓冲与降级方案 |

## 7.2 相对稳定：除非项目方向根本改变，否则建议保留

- 以“可检查、可编辑的结构化行程”为核心产物；
- AI 负责理解/生成/解释，代码与工具负责事实/计算/校验；
- 外部事实带来源和查询时间，估算与报价分开；
- 关键输出通过 schema 和确定性规则检查；
- 外部动作先预览、再确认、再验证结果；
- API 失败时透明降级，不伪造成功；
- 接口先行、mock 并行、尽早做 vertical slice；
- 保留固定评测集、版本和失败证据，支持回归测试。

## 7.3 建议在 PPT 上怎样表述“不确定性”

不要说“这些功能都一定会做完”，建议写：

> **Our proposal defines a feasible baseline and several candidate extensions. The baseline will remain stable, while feature priorities and evaluation thresholds will be refined after user research and early prototyping.**

这样既表明团队有完整方向，也不会把尚未调研的功能写成最终承诺。

---

# 8. PPT 页面压缩建议

如果 Proposal 的页数紧张，第二部分可以压成 3 页：

### Slide A — System design and the role of AI

- 左侧：架构图；
- 右侧：AI / deterministic tools / user confirmation 三层职责；
- 底部一句话：The LLM proposes; tools provide facts; rules validate; the user confirms.

### Slide B — Main risks, mitigation, and verification

- 放 R1–R6 主表；
- 每行只保留 risk / mitigation / test；
- 用颜色标出两个“必须为 0”的指标：unauthorized actions、false success。

### Slide C — Team plan and work plan

- 上半：六人 Proposal 分工；
- 下半：Scope & contract → parallel prototypes → vertical slice → revision/action → verification → extensions；
- 角落注明：Baseline fixed; priorities refined after user research.

详细风险 R1–R8、评测集和指标放到 backup slides，供 Q&A 使用。

---

# 9. PPT 英文精简版

## Slide: System design and the role of AI

**AI responsibilities**

- Convert natural-language needs into structured travel constraints.
- Generate and explain a candidate itinerary.
- Revise the plan when the user changes a preference.

**System safeguards**

- Current facts come from external tools with sources and query times.
- Code checks time, budget, route, and output schema.
- The user previews and confirms every external action.

**Key message**

> The LLM proposes; tools provide facts; deterministic checks validate; the user confirms.

## Slide: Risks and planned verification

- **Hallucinated or stale facts** → source grounding and timestamps → traceability test.
- **Constraint violations** → structured constraints and rule checks → conflict and boundary tests.
- **API failure or rate limits** → timeout, retry, quota control, degraded mode → fault injection.
- **Incorrect external actions** → preview, confirmation, least privilege, idempotency → zero unconfirmed or duplicate writes.
- **Prompt injection / unsafe output** → treat imported content as untrusted data; schema and parameter validation → red-team tests.
- **Scope and integration risk** → fixed baseline, shared contracts, mock data, early vertical slice → end-to-end acceptance test.

## Slide: Team and work plan

**Proposal roles**

- Two members: slide integration, English narrative, diagrams, and rehearsal.
- One technical member: technology stack and data sources.
- One technical member: AI role, risks, mitigation, and verification.
- One design member: user stories and the main workflow.
- One design member: background and competitor analysis.

**Work plan**

> Scope & contract → parallel prototypes → first vertical slice → interactive revision and action → verification and user pilot → optional extensions.

---

# 10. 参考资料与引用建议

1. 课程 Project Kick-off PDF：Proposal system design/work plan、Project 3 core modules、scope and demonstration。PPT 中可引用为课程要求，不必把课程文字当成团队已经实现的功能。
2. NIST, *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*：生成式 AI 的 confabulation、information integrity、privacy 和 automation bias 风险。  
   https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
3. NIST AI RMF Core / AIRC：强调可重复、可记录的测试、评估、验证与确认（TEVV），并应在部署前及运行中持续测试。  
   https://airc.nist.gov/airmf-resources/airmf/5-sec-core/
4. OWASP GenAI Security Project, *LLM05:2025 Improper Output Handling*：模型输出进入下游系统前必须验证、清洗和安全处理。  
   https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/
5. OWASP GenAI Security Project, *LLM06:2025 Excessive Agency*：Agent 风险常来自过多功能、过多权限或过多自主权，支持“最小权限 + 人工确认”。  
   https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
6. Google Maps Platform FAQ / Routes documentation：地图服务存在配额、计费、限流和特定模式/地区限制，应做 quota、cost 与 failure handling。  
   https://developers.google.com/maps/faq  
   https://developers.google.com/maps/documentation/routes/
7. Google Maps Platform security guidance：API key 应按应用和 API 做限制。  
   https://developers.google.com/maps/api-security-best-practices
8. OpenAI API documentation（若最终采用 OpenAI）：结构化输出可用 JSON Schema；模型/Prompt 变更应配套 eval regression。具体供应商尚未确定时，不要在 PPT 中写死。  
   https://platform.openai.com/docs/api-reference/evals


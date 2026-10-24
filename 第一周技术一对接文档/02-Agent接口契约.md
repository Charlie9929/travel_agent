# Agent 接口契约 v1.0

> 项目：AI 多人旅行规划助手 ｜ 负责人：技术1（Agent 核心）｜ 版本：v1.0（2026-10-17）｜ 状态：待周日评审
>
> 配套文件：[01-行程数据Schema文档](./01-行程数据Schema文档.md) ｜ [itinerary.schema.json](./schemas/itinerary.schema.json) ｜ [需求理解 Prompt v0.1](./prompts/需求理解Prompt-v0.1.md) ｜ [行程生成 Prompt v0.1](./prompts/行程生成Prompt-v0.1.md)
>
> 阅读对象：技术2（据此实现 Agent 编排器 + 修复循环 + JSON 校验）、技术3（据此理解前端拿到的响应结构）

---

## 1. 定位与边界

- Agent 是**后端内部模块**（FastAPI 进程内调用，不暴露公网 HTTP），由技术2 的服务层编排调度。不引入多 Agent、不引入 MCP（指导书已定案）。
- 技术分工边界：**技术1** 负责 Prompt 效果与输出契约（本文件 §3-§4 + prompts/ 目录）；**技术2** 负责 LLM API 封装、修复循环落地、Prompt 版本管理、重试与降级工程化。本契约是双方共识。
- 数据契约：所有结构化输出以 `itinerary.schema.json v1.0` 为唯一校验基准。

## 2. 通用约定

### 2.1 调用与响应包裹

所有 Agent 接口统一返回信封：

```jsonc
// 成功
{ "ok": true, "data": { ... }, "meta": { ... } }

// 失败
{ "ok": false, "error": { "code": "AGENT_XXX", "message": "人类可读说明", "retryable": true, "detail": { } } }
```

`meta`（每次响应必带，供 Prompt 版本管理与设计3 的 AI 使用记录归档）：

```jsonc
{
  "request_id": "uuid",            // 链路追踪 ID，前端透传
  "prompt_id": "plan-generation",  // Prompt 标识
  "prompt_version": "v0.1",
  "model": "xxx",                  // 实际使用的 LLM 型号
  "attempts": 1,                   // 修复循环实际执行次数（含首次）
  "latency_ms": 3200,
  "token_usage": { "prompt": 1200, "completion": 800 }
}
```

### 2.2 超时与重试

| 项 | 约定 |
|---|---|
| 单次 LLM 调用超时 | 60s（`parse_preferences`）/ 120s（`generate_itinerary`、`replan_day`）|
| 修复循环上限 | 见 §5，**总耗时上限 300s**，超限直接返回失败 |
| Agent 接口幂等 | 按 `request_id` 幂等：同 request_id 重试返回缓存结果，不重复计费 |
| 并发 | Agent 无状态；行程级并发由后端用 `version` 乐观锁控制（见 §6） |

## 3. 接口清单（6 个）

| # | 接口 | 对应模块 | 使用周次 |
|---|---|---|---|
| 1 | `parse_preferences` | 模块① 偏好理解（多轮追问） | 第 2 周 |
| 2 | `generate_itinerary` | 模块③ 行程生成 | 第 2 周 |
| 3 | `revise_itinerary` | 模块⑤ 交互式修改（行前改约束） | 第 3 周 |
| 4 | `replan_day` | 附加B 行中重排（只改当天剩余） | 第 3 周 |
| 5 | `explain_diff` | 模块⑤ 差异说明（可独立调用） | 第 3 周 |
| 6 | `extract_guide` | 附加E 攻略文本抽取 | 第 3 周 |

### 3.1 parse_preferences — 需求理解

多轮对话中提取结构化约束；缺失必填项时**一次只追问一个问题**。

**输入**

```jsonc
{
  "session_id": "uuid",          // 一轮行程创建会话
  "history": [                   // 完整对话历史（含系统追问）
    { "role": "user", "content": "我们五个人十一想去成都吃火锅，人均预算1500" },
    { "role": "assistant", "content": "好的，请问你们计划哪天出发、哪天返程？" },
    { "role": "user", "content": "10月1号到3号" }
  ],
  "constraints_so_far": {        // 上一轮解析结果（首轮传 null 字段结构）
    "city": "成都", "date_start": null, "date_end": null,
    "budget_total": 7500, "budget_note": "用户表述人均1500×5人换算",
    "traveler_count": 5, "preferences": ["美食"], "pace": null,
    "party_type": null, "special_constraints": []
  }
}
```

**输出 `data`**

```jsonc
{
  "constraints": {               // 结构与 constraints_so_far 一致，累积合并
    "city": "成都", "date_start": "2026-10-01", "date_end": "2026-10-03",
    "budget_total": 7500, "budget_note": "用户表述人均1500×5人换算",
    "traveler_count": 5, "preferences": ["美食"], "pace": null,
    "party_type": null, "special_constraints": []
  },
  "missing_required": [],        // 当前仍缺失的必填项
  "ready_to_generate": true,     // true=必填齐全，前端显示"生成行程"按钮
  "next_question": null          // 缺失时为一句中文追问，一次只问一个
}
```

**必填项定义**：`city`、`date_start`、`date_end`、`budget_total`、`traveler_count`。追问顺序：城市 → 日期 → 人数 → 预算。

**规则**：只提取用户明确表达的信息，缺失一律 null，**禁止编造**；"人均"换算为总额并写 `budget_note`；`ready_to_generate=false` 时 `next_question` 必非空。

**Prompt**：见 [需求理解Prompt-v0.1](./prompts/需求理解Prompt-v0.1.md)

### 3.2 generate_itinerary — 行程生成

**输入**

```jsonc
{
  "trip_id": "",                  // 首次生成为空串，后端落库后回填
  "constraints": { /* 3.1 输出的完整约束 */ },
  "poi_candidates": [             // 模块② 用地图 API 预查的候选集（关键：不让 LLM 瞎编）
    { "poi_id": "B0FFG9XXXX", "name": "宽窄巷子", "type": "景点",
      "lng": 104.053, "lat": 30.663, "rating": 4.5,
      "open_hours_hint": "全天开放", "ticket_price_hint": "免费" }
  ],
  "base_version": null            // 首次生成 null
}
```

**输出 `data`**：完整行程 JSON（符合 `itinerary.schema.json`），其中：

- LLM 只填：`meta`、`city.name`、`days[].date/day_index/theme/activities[]`（`activity_id/type/title/time_slot/cost/note/open_hours_hint/location.name`）
- **后端负责回填**：`location` 的 `lng/lat/poi_id`（按名称匹配 poi_candidates）、`cost.price_type` 强制改写为 `estimate`+`source=llm`、`days[].transfers[]`（调地图路线规划 API）、`cost_summary`（规则引擎重算）、`version`、`trip_id`
- `revisions` 首条 `create` 记录由后端生成

**生成流水线**（技术2 编排）：

```
约束齐全 → 地图API搜POI候选集 → Agent生成行程JSON
  → L0/L1 校验+修复循环 → L2 业务规则校验（模块④）→ L3 POI回填/抽检
  → 落库(version=1) → 返回前端渲染
```

**Prompt**：见 [行程生成Prompt-v0.1](./prompts/行程生成Prompt-v0.1.md)

### 3.3 revise_itinerary — 行前交互式修改（模块⑤）

**输入**

```jsonc
{
  "trip_id": "uuid",
  "base_version": 3,             // 冲突检测：当前 version > base_version → 409
  "itinerary": { /* 当前完整行程 */ },
  "changed_constraints": {       // 只传变化项，如 {"budget_total": 1000} 或 {"preferences": ["美食优先"]}
    "removed": [], "updated": { "budget_total": 1000 }
  },
  "user_instruction": "预算降到1000，还是想保持美食优先"   // 可选，自然语言补充
}
```

**输出 `data`**（注意：**不是直接覆盖，而是修订提案**）

```jsonc
{
  "revision_id": "rev-4",
  "action": "constraint_change",
  "summary": "预算从1500降至1000，替换了2个高价景点，取消1项演出",
  "diff": [                      // 结构化差异，见 Schema §4.6
    { "op": "replace", "path": "/days/0/activities/2/title",
      "field": "title", "old_value": "蜀风雅韵川剧", "new_value": "人民公园茶馆",
      "reason": "演出票价180元/人，替换后可将总费用控制在1000元内" }
  ],
  "proposed_itinerary": { /* 修改后的完整行程快照，status 全部 planned */ }
}
```

**User Control 流程**：前端展示 summary + diff → 用户「确认应用」→ 后端将 `proposed_itinerary` 落库（version+1）、revision 置 applied；「放弃」→ revision 置 rejected，原行程不变。

### 3.4 replan_day — 行中局部重排（附加B）

**核心难点：只改当天剩余时段，保住其余所有天与当天已过部分。**

**输入**：在 3.3 基础上增加范围限定字段：

```jsonc
{
  "trip_id": "uuid",
  "base_version": 5,
  "itinerary": { /* 当前完整行程（LLM 必须拿到全量上下文） */ },
  "scope": { "type": "rest_of_day", "day_index": 2, "after_time": "14:00" },
  "trigger": {                   // 触发原因，供 Prompt 与 replaced_reason 使用
    "reason_type": "rain | closed | queue | user_request",
    "description": "预报明天下午有雨",
    "target_activity_ids": ["act-8"]    // 可选：被用户点名替换的景点
  },
  "candidate_replacements": [    // 模块② 按室内/雨天友好条件预查的替换候选（可选传入）
    { "poi_id": "B0FFH1YYYY", "name": "成都博物馆", "type": "室内景点" }
  ]
}
```

**输出 `data`**：与 3.3 同构（revision + diff + proposed_itinerary），额外约束：

- `diff` 的 `path` **只允许命中 `/days/1/...`（即 day_index=2 当天）** 且 `time_slot.start >= 14:00` 的活动；越界 diff 视为 L1 校验失败，进入修复循环
- 未变更活动的 `activity_id` 必须原样保留（Schema 设计原则 6）
- 被替换活动置 `status=replaced` + `replaced_reason`（从 trigger.description 提炼）

### 3.5 explain_diff — 差异说明

3.3/3.4 已内置 `diff[].reason`；当 diff 条目 >10 或前端需要整段自然语言时独立调用：

**输入**：`{ "old_itinerary": {...}, "new_itinerary": {...} }`
**输出 `data`**：`{ "summary": "一句话总述", "by_day": [ { "day_index": 1, "changes": ["...白话说明..."] } ] }`

### 3.6 extract_guide — 攻略文本抽取（附加E）

**输入**：`{ "text": "用户粘贴的游记正文（≤8000字）", "city": "成都" }`（红线：只接受粘贴文本，不做爬虫/不读链接）

**输出 `data`**：候选条目列表（符合 Schema `candidates[]` 结构）+ `{ "warning": "文本中提到的『某餐厅已歇业』无法核实，已标注" }`

**校验规则**：抽取结果中的 POI 一律 `poi_source=llm` 占位，用户勾选后由后端调地图 API 校验存在性并回填真实 `poi_id`；校验不到的条目保留但标记"未能定位，请人工确认"。

## 4. 统一错误码

| code | HTTP 映射 | retryable | 触发场景 | 前端/调用方处理 |
|---|---|---|---|---|
| `AGENT_INPUT_INVALID` | 422 | false | 输入不符合本契约（缺必填字段、日期格式错、history 非法） | 提示"输入有误"，展示 message |
| `AGENT_NOT_READY` | 409 | false | `ready_to_generate=false` 时请求生成 | 继续追问流程（正常业务态） |
| `AGENT_OUTPUT_INVALID` | 500 | true | LLM 输出经修复循环仍不过 L1/L2 校验（§5） | 提示"生成失败，请重试"；attempts 证据入 AI 使用记录 |
| `AGENT_OUTPUT_TRUNCATED` | 500 | true | 输出因 token 上限被截断 | 同上；detail 携带 `max_tokens` 建议值 |
| `AGENT_LLM_TIMEOUT` | 504 | true | 单次 LLM 调用超时 | 自动重试 ≤2 次，仍失败提示稍后再试 |
| `AGENT_LLM_UNAVAILABLE` | 503 | true | LLM 服务不可用/断流 | 进入**降级模式**（§5.4） |
| `AGENT_RATE_LIMIT` | 429 | true | LLM API 限流 | 指数退避重试；前端提示"稍等几秒" |
| `AGENT_QUOTA_EXCEEDED` | 402 | false | LLM 账户额度耗尽 | 不可重试；通知组内充值 |
| `AGENT_CONTEXT_TOO_LONG` | 413 | true | 输入 token 超限（超长攻略文本/超长行程） | 攻略文本提示分段粘贴；重排接口压缩上下文后重试 |
| `AGENT_COLLAB_CONFLICT` | 409 | false | `base_version` 落后于当前 version（§6） | 前端拉取最新行程 + 冲突弹窗（附加A2） |
| `AGENT_TRIP_NOT_FOUND` | 404 | false | trip_id 不存在 | 提示行程不存在 |
| `AGENT_INTERNAL` | 500 | true | 其他未归类异常 | 记录 request_id 上报 |

**约定**：`retryable=true` 由技术2 的编排器自动重试（带指数退避），重试次数耗尽才上抛；`retryable=false` 直接上抛。所有错误必须携带 `request_id`，方便对账 AI 使用记录。

## 5. 修复循环规则（技术1 定规则，技术2 落地实现）

### 5.1 校验层次

```
LLM 原始输出
  ├─ L0 程序清洗：剥 markdown 代码块围栏、修尾随逗号/截断、去注释 → 纯 JSON
  ├─ L1 Schema 校验：jsonschema（draft 2020-12）按 itinerary.schema.json 校验
  ├─ L2 业务校验（模块④，纯代码非 LLM）：
  │    时间：同 day 内 activities 按 time_slot 升序且不重叠；end>start
  │    日期：days 覆盖 date_start..date_end，无缺天、无重复
  │    城市：city 唯一且等于输入城市（不跨市）
  │    预算：cost_summary.total_estimate ≤ budget_total（超支 → 生成失败，回炉）
  │    ID：activity_id 唯一；重排场景 diff.path 不越界（§3.4）
  │    价格：所有 cost.price_type 必须 = estimate；出现 quoted 即失败
  └─ L3 事实校验（技术2，地图 API）：POI 存在性、坐标回填、开放时间/票价查询
       → 不过的 POI：优先在候选集中换同名/近似 POI 回填；无法替换则保留并标注"待核实"
```

### 5.2 循环流程

```
attempt=1 调 LLM
  → L0 清洗（程序内，无 LLM 参与，不计入 attempt）
  → L1/L2 校验
      通过 → 进入 L3 → 成功返回
      失败 → 收集全部错误（一次性给全，避免挤牙膏）→ attempt+1 重新调 LLM
             Prompt 追加结构化错误清单，例如：
             「上次输出存在以下问题，必须全部修复：
              1) days[1] 缺失（应覆盖10-21）
              2) /days/0/activities/2/time_slot.end 早于 start
              3) activity_id 'act-2' 重复」
  → attempt > 2 仍失败 → 返回 AGENT_OUTPUT_INVALID（携带各次 attempt 错误摘要到 detail）
```

### 5.3 硬性规则

1. **最多 2 次修复**（总 attempts ≤ 3），总耗时 ≤ 300s。
2. 错误信息**一次性全量**回喂，不逐条挤牙膏。
3. 每次 attempt 的原始输出、错误清单、耗时均落日志（AI 使用记录素材，设计3 归档用）。
4. L3 不触发整体重生成：POI 层面的问题用"候选集替换/标注待核实"就地解决，避免整篇回炉浪费 token。
5. temperature 约定：生成类接口 temperature ≤ 0.7；修复重试时降至 ≤ 0.3 提高服从性。

### 5.4 降级模式（AGENT_LLM_UNAVAILABLE / 重试耗尽时）

| 场景 | 降级行为 |
|---|---|
| 需求理解不可用 | 前端回退为**表单填写**（城市/日期/人数/预算/偏好手动输入，等价于 constraints），表单可直接进 generate_itinerary |
| 行程生成不可用 | 明确报错"AI 生成暂不可用"，可从历史行程模板列表选择（如已有行程副本）；不做假 AI |
| 重排不可用 | 保留"手动编辑"通道：用户可自行拖改/删除 activity，后端记录 member_edit 修订 |

对应 PDF 硬要求「演示一个异常用例以及怎么处理」：答辩时演示"AI 返回乱码 → 修复循环 → 仍失败 → 降级表单"，即本节与 §5.2 的完整链路。

## 6. 多人协同相关约定（与附加A 对齐）

1. **乐观锁**：所有写行程的 Agent 接口（3.3/3.4，及后端的 member_edit 落库）必须携带 `base_version`；后端 `WHERE trip_id=? AND version=<base_version>` 更新，影响行数 0 → 返回 `AGENT_COLLAB_CONFLICT`。
2. **冲突弹窗数据**（A2 方案，3s 轮询）：前端轮询发现 version 变化 → 拉最新行程 → 若本地有未保存编辑，弹窗展示"我的修改 vs 最新行程"（复用 `explain_diff`/diff 结构），用户选择保留哪版。
3. **activity_id 稳定性**是协同的地基：任何人/AI 的编辑都不允许变更未动条目的 activity_id，L1 校验强制执行。
4. AI 修订（replan/revise）与成员手动编辑（member_edit）在 `revisions[]` 中统一留痕，`actor.source` 区分，保证"谁加了哪个景点、谁改了时间"可追溯（对应附加A 痛点）。

## 7. Prompt 与契约的关系

| Prompt 文件 | 服务接口 | 版本 |
|---|---|---|
| [prompts/需求理解Prompt-v0.1.md](./prompts/需求理解Prompt-v0.1.md) | parse_preferences | v0.1 |
| [prompts/行程生成Prompt-v0.1.md](./prompts/行程生成Prompt-v0.1.md) | generate_itinerary / revise_itinerary / replan_day（后两者的 Prompt 第 2 周在本文件基础上派生） | v0.1 |

- Prompt 内声明的输出结构**必须**与本契约一致；不一致以本契约为准，改 Prompt。
- Prompt 升版本走技术2 的 Prompt 版本管理，`meta.prompt_version` 自动上报。

## 8. 待评审确认项（周日评审需拍板）

1. LLM 供应商与型号（影响成本与 JSON 服从性；建议选支持 JSON mode / 结构化输出的型号，可大幅减少修复循环次数）。
2. 修复循环上限 attempts ≤ 3 是否符合成本预期（可先上线后按 AGENT_OUTPUT_INVALID 率调整）。
3. `revise_itinerary` 输出整份 proposed_itinerary 的 token 成本 vs 只输出 diff + 变更活动列表（第 3 周视实测决定，契约已预留两种可能）。

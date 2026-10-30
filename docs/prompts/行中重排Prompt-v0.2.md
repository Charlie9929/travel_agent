# replan_day Prompt v0.2（附加B 行中局部重排）

> 负责人：技术1 ｜ 版本：v0.2（2026-10-30，Week 3）｜ 服务接口：`replan_day`（见 [02-Agent接口契约 §3.4](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=2500, response_format=json_object
> v0.1→v0.2 变更：补 4 个边界 case（target 不存在、after_time 跨活动、二次重排、pending revision）；diff.ops 结构对齐 diff_scope_validator

---

## 1. 核心难点（也是最容易出 bug 的地方）

**只改当天剩余时段，保住其余所有天与当天已过部分。**

L1 校验会强制执行：
1. `activity_id 稳定性`：replan 后非 scope 天的 activity_id 集合必须与输入完全一致；scope 天 after_time 之前的活动 activity_id 必须保留
2. `diff 越界`：diff.ops 的 day_index 必须 = scope.day_index
3. 被替换活动 status="replaced" + replaced_reason，禁止直接删除

## 2. API 参数

```jsonc
{
  "model": "deepseek-chat",
  "temperature": 0.5,
  "max_tokens": 2500,
  "response_format": { "type": "json_object" },
  "top_p": 0.9
}
```

## 3. 变量表

| 变量 | 说明 |
|---|---|
| `{{itinerary_json}}` | 当前完整行程（**必须全量传给 LLM**，让它看到完整上下文才能不乱动其他天） |
| `{{scope}}` | `{ "type": "rest_of_day", "day_index": 2, "after_time": "14:00" }` |
| `{{trigger}}` | 触发原因 `{ "reason_type": "rain"|"closed"|"queue"|"user_request", "description": "预报明天下午有雨", "target_activity_ids": ["act-8"] }` |
| `{{candidate_replacements}}` | 模块② 预查的替换候选（按触发条件过滤，如"室内景点"），可选传入 |

## 4. System Prompt

```text
你是旅行行程的「行中重排模块」。行程进行中，某个原因（下雨/闭馆/排队太长/用户临时要求）需要调整某一天下午的安排。你的任务：只重排 scope 指定的那一天、指定时间之后的活动，其余全部原样保留。

# 铁律（违反任何一条 = 输出作废，L1 校验会拦）
1. 范围硬约束：diff 只能涉及 scope.day_index 指定的那一天，且只能是该天内 time_slot.start ≥ scope.after_time 的活动。其他天、以及当天 after_time 之前的活动，一律原样保留。
2. activity_id 不变：未修改的活动 activity_id 必须原样保留；被替换的活动改为 status="replaced" + replaced_reason；新增活动的 activity_id 接现有最大编号
3. 被替换活动必须保留（status=replaced），不能删除——多人协同需要追溯"谁换掉了哪个"
4. price_type 只能是 "estimate"，source 只能是 "llm"
5. 单日时间不重叠：修改后的当天 activities 按 start 升序，end < 下一个 start
6. 输出纯 JSON

# 边界场景处理
- trigger.target_activity_ids 中某些 id 在行程里不存在（已被队友替换）：忽略不存在的 id，按 after_time 时间范围自由重排即可。不要因为找不到某个 id 就报错。
- scope.after_time 跨越某条活动中间（如 act-3 13:00-14:30，after_time=13:45）：整条 act-3 都算在重排范围内（因为 after_time 落在它中间），可以替换 act-3 本身。但 act-3 之前的活动必须原样保留。
- 被替换活动本身已经是 status="replaced"（二次重排）：仍然把它算进 diff（op=remove），并新增新的替代活动。原来的 replaced 活动继续保留在 proposed_itinerary 里（追溯链不能断）。
- scope.day_index 那天存在 status="pending_revision" 的活动（多人协同，队友刚推了但还没应用的修订）：忽略 pending 状态，只看已应用的活动。Agent 拿到的 itinerary_json 已经由上下文组装中间件过滤过，你不用管 pending。

# 触发原因处理
- trigger.reason_type = "rain" → 优先换室内/非露天活动（博物馆/美术馆/茶馆/商业街）
- trigger.reason_type = "closed" → 必须换掉被点名的 target_activity_ids，换成候选集中的替代项
- trigger.reason_type = "queue" → 调整时间段（改早/改晚避开高峰）或换替代项
- trigger.reason_type = "user_request" → 按 description 自由发挥但仍受范围约束

# 输出骨架（纯 JSON）
{
  "summary": string (一句话说明，如"2026-10-21（Day2）14:00后因降雨预报，将3个露天活动替换为室内博物馆和茶馆"),
  "diff": {
    "ops": [
      {
        "op": "replace" | "remove" | "add" | "move",
        "activity_id": string,        // 被修改/替换的活动 id
        "day_index": integer,          // 必须等于 scope.day_index
        "fields": string[] | null,     // replace 场景：被替换的顶层字段（如 ["poi","time_slot"]）。每个 op 只改一个顶层 field
        "target_activity_ids": string[] | null,  // replan_day 场景：哪些活动触发了这条 op（可选）
        "reason": string | null
      }
    ]
  },
  "proposed_itinerary": {
    // 完整行程，结构同输入 itinerary_json
    // 只有 diff 涉及的字段改值，其余完全照搬
    // 被替换的活动：status="replaced", replaced_reason=从 trigger.description 提炼
    // 新增的替换活动：接在被替换位置附近，time_slot 连贯
  }
}

# diff.ops 粒度铁律（违反 = 被 diff_scope_validator 拒绝）
- 每个 replace op 只改一个顶层 field（如只改 time_slot 就只 replace time_slot）。同时改 poi + time_slot 应该拆成两个 replace op。
- 禁止 remove + add 同一个 activity_id——应该用 replace 替代。
- move op 用于活动位置调整（时间变了但内容没变），必须同时有 from_id 和 to_id。
- op="remove" 只有在二次重排时才用（原来 replaced 的活动被新的替代活动彻底移除）。正常替换用 op="replace"。
```

## 5. User 消息模板

```text
【当前完整行程】
{{itinerary_json}}

【重排范围 scope】
{{scope}}

【触发原因 trigger】
{{trigger}}

【替换候选（可选）】
{{candidate_replacements}}

请输出修改提案 JSON。
```

## 6. 测试用例

### 用例 1：Day2 下午下雨替换露天景点（正常场景）

**输入**

```jsonc
// scope
{ "type": "rest_of_day", "day_index": 2, "after_time": "14:00" }
// trigger
{ "reason_type": "rain", "description": "2026-10-21 14:00后降雨概率80%",
  "target_activity_ids": ["act-8", "act-9"] }
// candidate_replacements（模块② 按"室内"条件预查）
[
  { "poi_id": "B0FFI2", "name": "成都博物馆", "type": "室内景点", "open_hours_hint": "09:00-17:00", "ticket_price_hint": "免费" },
  { "poi_id": "B0FFK1", "name": "四川省美术馆", "type": "室内景点", "open_hours_hint": "09:00-17:00", "ticket_price_hint": "免费" },
  { "poi_id": "B0FFL3", "name": "鹤鸣茶社", "type": "茶馆", "open_hours_hint": "08:00-21:00", "ticket_price_hint": "人均40" }
]
// itinerary_json（Day2 节选，完整行程必须全量传入）
{
  "days": [
    { "date": "2026-10-20", "day_index": 1, "activities": [/* 原样 */] },
    { "date": "2026-10-21", "day_index": 2, "activities": [
      { "activity_id": "act-7", "type": "poi", "title": "熊猫基地", "time_slot": { "start": "09:00", "end": "12:00" }, "status": "planned" },  // 在 14:00 前，不能动
      { "activity_id": "act-8", "type": "poi", "title": "青龙湖湿地公园", "time_slot": { "start": "14:00", "end": "16:30" }, "status": "planned" },  // 被触发
      { "activity_id": "act-9", "type": "poi", "title": "东安湖公园", "time_slot": { "start": "17:00", "end": "19:00" }, "status": "planned" },   // 被触发
      { "activity_id": "act-10", "type": "meal", "title": "晚餐", "time_slot": { "start": "19:30", "end": "21:00" }, "status": "planned" }   // 19:30 ≥ 14:00，可以动但 trigger 没点名
    ]},
    { "date": "2026-10-22", "day_index": 3, "activities": [/* 原样，绝不能动 */] }
  ]
}
```

**预期输出要点**

- diff.ops 数量 ≥ 2（act-8、act-9 被替换为 replaced + 新增室内活动）
- act-7 **原样保留**（在 14:00 前）
- Day1 和 Day3 的 activities **完全不变**（activity_id 集合与输入一致）
- act-8、act-9 在 proposed 中 status="replaced" + replaced_reason="降雨概率80%"
- 新增活动 title 精确匹配 candidate_replacements 里的 name
- Day2 下午时间连贯无重叠
- summary 提到 Day2 14:00 后因降雨替换

### 用例 2：target_activity_ids 不存在（队友已替换）

**输入**：同用例 1，但 trigger.target_activity_ids = `["act-8", "act-9", "act-99"]`（act-99 不存在）

**预期输出要点**

- Agent 忽略 act-99，正常处理 act-8、act-9
- summary 不提及 act-99
- 不报错、不输出空 diff

### 用例 3：after_time 跨越活动中间

**输入**：itinerary_json 的 Day2 有一条 act-3 13:00-14:30，scope.after_time = "13:45"

**预期输出要点**

- act-3 被整条算进重排范围（可以替换）
- act-3 之前的活动（13:00 之前的）必须原样保留
- act-3 本身 status 改为 "replaced" 或正常替换

### 用例 4：二次重排（被替换活动已存在）

**输入**：itinerary_json 中 act-8 已经是 status="replaced"（上次重排替换过），这次又触发 replace act-8 附近的活动

**预期输出要点**

- 原来 replaced 的 act-8 继续保留（追溯链不断）
- 新替代活动的 activity_id 接在现有最大编号之后
- diff.ops 里可以有 op="remove"（移除旧的 replaced）或 op="replace"（再 replace 一次）

**反例（会被 L1 校验拒绝）**

- diff.ops 包含 day_index ≠ scope.day_index → activity_id_validator 的 NON_SCOPE_DAY_MODIFIED / diff_scope_validator 的 OP_OUTSIDE_SCOPE_DAY
- after_time 之前的活动 activity_id 消失 → activity_id_validator 的 ID_MISSING_IN_SCOPE
- 直接删除 act-8 而不是改为 status="replaced" → activity_id_validator 的 ID_MISSING
- replace op 同时改 2 个顶层 field → diff_scope_validator 的 REPLACE_MULTI_FIELD
- remove + add 同一个 activity_id → diff_scope_validator 的 REMOVE_ADD_SAME_ID

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| LLM 不小心改了其他天的活动 | L1 校验硬拦：activity_id_validator 检查非 scope 天的 id 集合是否完全一致；diff_scope_validator 检查 day_index |
| 被替换活动被删除而非保留 replaced | activity_id_validator 检查原始 activity_id 是否还在 proposed 中（scope 场景只查 after_time 之前的；revise 场景查全部） |
| 替换活动超出时间限制（比如 17:00 闭馆的博物馆安排到 18:00） | few-shot 示范；open_hours_hint 字段已在 candidate_replacements 中提供，Agent 应参考 |
| 多人协同下 pending_revision 冲突 | 见 [03-多人协同上下文组装规则](../03-多人协同上下文组装规则.md)，上下文中间件已过滤 pending |
| trigger.target_activity_ids 不存在 | v0.2 新增处理规则：忽略不存在的 id，按时间范围自由重排 |
| after_time 刚好落在活动中间 | v0.2 新增规则：整条活动算在重排范围内 |

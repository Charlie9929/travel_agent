# replan_day Prompt v0.1（附加B 行中局部重排）

> 负责人：技术1 ｜ 版本：v0.1（2026-10-21，Week 2）｜ 服务接口：`replan_day`（见 [02-Agent接口契约 §3.4](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=2500, response_format=json_object

---

## 1. 核心难点（也是最容易出 bug 的地方）

**只改当天剩余时段，保住其余所有天与当天已过部分。**

L1 校验会强制执行：diff 的 path **只允许命中 scope 指定 day_index 的当天活动**，且只能是 `time_slot.start >= after_time` 的条目。越界 diff = 失败。

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

# 触发原因处理
- trigger.reason_type = "rain" → 优先换室内/非露天活动（博物馆/美术馆/茶馆/商业街）
- trigger.reason_type = "closed" → 必须换掉被点名的 target_activity_ids，换成候选集中的替代项
- trigger.reason_type = "queue" → 调整时间段（改早/改晚避开高峰）或换替代项
- trigger.reason_type = "user_request" → 按 description 自由发挥但仍受范围约束

# 输出骨架（纯 JSON）
{
  "summary": string (一句话说明，如"2026-10-21（Day2）14:00后因降雨预报，将3个露天活动替换为室内博物馆和茶馆"),
  "diff": [
    {
      "op": "replace" | "remove" | "add" | "move",
      "path": string (JSON Pointer),
      "field": string | null,
      "old_value": any | null,
      "new_value": any | null,
      "reason": string | null
    }
  ],
  "proposed_itinerary": {
    // 完整行程，结构同输入 itinerary_json
    // 只有 diff 涉及的字段改值，其余完全照搬
    // 被替换的活动：status="replaced", replaced_reason=从 trigger.description 提炼
    // 新增的替换活动：接在被替换位置附近，time_slot 连贯
  }
}
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

### 用例：Day2 下午下雨替换露天景点

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

- diff 数量 ≥ 2（act-8、act-9 被替换为 replaced + 新增室内活动）
- act-7 **原样保留**（在 14:00 前）
- Day1 和 Day3 的 activities **完全不变**（L1 越界校验会检查）
- act-8、act-9 在 proposed 中 status="replaced" + replaced_reason="降雨概率80%"
- 新增活动 title 精确匹配 candidate_replacements 里的 name
- Day2 下午时间连贯无重叠
- summary 提到 Day2 14:00 后因降雨替换

**反例（会被 L1 校验拒绝）**

- diff 包含 Day1 或 Day3 的 path（越界）
- diff 包含 act-7（14:00 前的活动）
- 删除了 act-8 而不是改为 status="replaced"

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| LLM 不小心改了其他天的活动 | L1 校验硬拦：遍历 diff.path，检查每个 path 命中的 day_index 是否等于 scope.day_index；不等于 → 整份失败进修复循环，错误清单第一条写"越界修改 Day X" |
| 被替换活动被删除而非保留 replaced | L1 校验：检查 proposed 中原始 activity_id 的 status，如果不见了 → 失败 |
| 替换活动超出时间限制（比如 17:00 闭馆的博物馆安排到 18:00） | few-shot 示范；L3 可用 open_hours_hint 校验（week 3 上线） |
| 多人协同下 pending_revision 冲突 | 见多人上下文组装规则文档 |
| 触发 target_activity_ids 不存在（已被其他成员替换） | Agent 忽略不存在的 id，按时间范围自由重排 |

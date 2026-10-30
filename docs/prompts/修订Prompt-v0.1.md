# revise_itinerary Prompt v0.1（模块⑤ 行前交互式修改）

> 负责人：技术1 ｜ 版本：v0.1（2026-10-21，Week 2）｜ 服务接口：`revise_itinerary`（见 [02-Agent接口契约 §3.3](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=3000, response_format=json_object

---

## 1. 核心原则

**修改量最小化**——只动受约束变化影响的活动，其余所有活动原样保留，特别是 `activity_id` 必须不变。用户改的是"预算"，你不应该重写整个行程。这是多人协同下可追溯性的地基。

## 2. API 参数

```jsonc
{
  "model": "deepseek-chat",
  "temperature": 0.5,
  "max_tokens": 3000,
  "response_format": { "type": "json_object" },
  "top_p": 0.9
}
```

修复重试 → temperature 降至 0.3，System Prompt 末尾追加错误清单。

## 3. 变量表

| 变量 | 说明 |
|---|---|
| `{{itinerary_json}}` | 当前完整行程（符合 itinerary.schema.json v1.0） |
| `{{changed_constraints}}` | 变化的约束 `{ "removed": [], "updated": {"budget_total": 1000} }` |
| `{{user_instruction}}` | 可选，用户的自然语言补充说明 |
| `{{base_version}}` | 当前行程的 version，用于冲突检测（前置校验，不进 Prompt） |

## 4. System Prompt

```text
你是旅行行程的「修改模块」。用户改了一个出行约束（比如预算、偏好、节奏），你的任务是在现有行程基础上做最小必要修改，并输出结构化的差异说明和修改后完整行程。

# 铁律（违反任何一条 = 输出作废）
1. 修改量最小化：只动受约束变化影响的活动，其余所有活动原样保留
2. activity_id 不变：未修改的活动必须保持原 activity_id，禁止重排编号、禁止删除后重添加
3. price_type 只能是 "estimate"，source 只能是 "llm"
4. 单日时间不重叠：每个 day 内 activities 按 start 升序，前一个的 end < 后一个的 start
5. 总 cost 必须 ≤ 新约束的 budget_total.amount（如果改了预算）
6. 输出纯 JSON，不要文字说明、不要 markdown 代码块

# 差异生成规则
- op="replace"：修改了字段值（如 cost.amount 从 120 改成 50）
- op="remove"：删除了整个活动
- op="add"：新增了活动（新 activity_id 接现有最大编号）
- op="move"：活动时间调整了（start/end 变更）
- path 用 JSON Pointer，如 /days/0/activities/2/time_slot
- reason 字段用中文简洁说明为什么改（如"该景点门票 180 元，换成免费的博物馆以控制预算"）

# 输出骨架（纯 JSON）
{
  "summary": string (一句话中文说明本次修改，如"预算从1500降到1000，替换了2个高价景点，取消1项演出"),
  "diff": [
    {
      "op": "replace" | "remove" | "add" | "move",
      "path": string (JSON Pointer),
      "field": string | null (语义化字段名，如"title","cost","time_slot"),
      "old_value": any | null (被替换/删除的旧值；add 时为 null),
      "new_value": any | null (新增/替换后的新值；remove 时为 null),
      "reason": string | null
    }
  ],
  "proposed_itinerary": {  // 修改后的完整行程，结构同输入 itinerary_json
    // 注意：只写顶层字段，内层结构完全照搬输入 itinerary_json，仅 diff 涉及的字段改值
  }
}
```

## 5. User 消息模板

```text
【当前行程】
{{itinerary_json}}

【约束变更】
{{changed_constraints}}

【用户补充说明】（可选）
{{user_instruction}}

请输出修改提案 JSON。
```

## 6. 测试用例

### 用例：预算从 4500 降到 3000（4 人 3 天）

**输入**：itinerary_json 是一个 4 人 3 天成都行程（总成本 ~4400），changed_constraints = `{"updated": {"budget_total": {"amount": 3000, "currency": "CNY", "price_type": "estimate", "source": "llm"}}}`

**预期输出要点**

- summary 一句话说明替换了什么、删了什么
- diff 数量 ≤ 8（3 天行程预算砍 1/3，修改量应集中但不过度）
- 所有未变更活动的 activity_id、title、location.name、time_slot **完全不变**
- proposed_itinerary.cost_summary.total_estimate ≤ 3000
- diff 中每个 reason 解释为什么换（如"门票 120 元/人×4=480，换成免费公园"）
- 时间不重叠

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| LLM 重写整个行程（违反最小修改原则） | activity_id 不变作为 L1 校验硬规则——如果 proposed 的 activity_id 和输入有显著差异（超过 diff 数量 + 2），直接判失败 |
| diff path 写错导致前端定位不到变化 | v0.2 观察；必要时 Prompt 末尾附 JSON Pointer 快速参考 |
| 预算砍太狠导致行程空洞 | 规则 5 要求必须 ≤ 新预算，但没说下限——靠 few-shot 示范"替换高价为低价免费"而非简单删除 |
| multi-person 场景下 pending_revision 冲突 | 见多人上下文组装规则文档，Agent 拿到的 itinerary_json 已经过滤掉未应用的修订 |

# revise_itinerary Prompt v0.2（模块⑤ 行前交互式修改）

> 负责人：技术1 ｜ 版本：v0.2（2026-10-30，Week 3）｜ 服务接口：`revise_itinerary`（见 [02-Agent接口契约 §3.3](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=3000, response_format=json_object
> v0.1→v0.2 变更：补 diff 粒度铁律；diff 结构对齐 diff_scope_validator；activity_id 不变作为 L1 硬规则明确化

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

# diff 粒度铁律（违反 = 被 diff_scope_validator 拒绝）
- 每个 replace op 只改一个顶层 field。同时改 cost + time_slot 应该拆成两个 replace op。
- 只改 cost 金额 → op="replace", fields=["cost"], reason="砍预算换低价"，不要把整条 activity 标记为 replace。
- activity 顺序变了但内容没变（只是时间挪了）→ op="move"，不要用 add + remove 或 replace。
- 禁止 remove + add 同一个 activity_id——这在 activity_id 校验层面是"先删再加"，会被拦。应该用 op="replace"。
- op="remove" 只有在活动被彻底取消（如闭馆/用户删掉）时才用。
- op="add" 用于新增活动（新 activity_id 接现有最大编号）。

# 输出骨架（纯 JSON）
{
  "summary": string (一句话中文说明本次修改，如"预算从1500降到1000，替换了2个高价景点，取消1项演出"),
  "diff": {
    "ops": [
      {
        "op": "replace" | "remove" | "add" | "move",
        "activity_id": string,          // 被修改/替换的活动 id；add 时是新 id
        "from_id": string | null,       // remove/move 场景：原 activity_id
        "to_id": string | null,         // add/move 场景：目标 activity_id
        "day_index": integer,            // 活动所在 day_index
        "fields": string[] | null,       // replace 场景：被替换的顶层字段（如 ["cost"] 或 ["time_slot"]）。每个 op 只改一个顶层 field
        "reason": string | null
      }
    ]
  },
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

### 用例 1：预算从 4500 降到 3000（4 人 3 天）

**输入**：itinerary_json 是一个 4 人 3 天成都行程（总成本 ~4400），changed_constraints = `{"updated": {"budget_total": {"amount": 3000, "currency": "CNY", "price_type": "estimate", "source": "llm"}}}`

**预期输出要点**

- summary 一句话说明替换了什么、删了什么
- diff.ops 数量 ≤ 8（3 天行程预算砍 1/3，修改量应集中但不过度）
- 所有未变更活动的 activity_id、title、location.name、time_slot **完全不变**
- proposed_itinerary.cost_summary.total_estimate ≤ 3000
- 每个 replace op 的 fields 只含一个顶层字段（如 `["cost"]` 或 `["poi"]`）
- 没有 remove + add 同一个 activity_id 的情况
- 时间不重叠

### 用例 2：只改一个活动的 cost（最小修改场景）

**输入**：用户要求"把 Day1 的蜀风雅韵川剧 180 元/人换成免费景点"

**预期输出要点**

- diff.ops 只有 1 条或 2 条（取决于是否新增替代）
- 如果只替换 cost → 1 条 replace，fields=["cost"]
- 如果替换整个 activity → 1 条 replace（原 activity_id） + 1 条 add（新 activity_id）
- 其他所有活动 activity_id 不变

### 用例 3：只是活动时间调整（move 场景）

**输入**：用户要求"把 Day2 的熊猫基地从上午改到下午"

**预期输出要点**

- diff.ops 里有 op="move"（from_id="act-7", to_id="act-7" 或 from_id="act-7", to_id="act-7"）
- 不要用 add + remove 表达这个改动
- 其他活动 activity_id 不变

**反例（会被 L1 校验拒绝）**

- proposed 的 activity_id 和输入有显著差异（超过 diff.ops 数量 + 2）→ activity_id_validator 多个 ID_MISSING
- replace op 同时改 cost + time_slot → diff_scope_validator 的 REPLACE_MULTI_FIELD
- remove + add 同一个 activity_id → diff_scope_validator 的 REMOVE_ADD_SAME_ID
- 把内容没变但顺序变了的活动用 replace → 应该用 move

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| LLM 重写整个行程（违反最小修改原则） | activity_id 不变作为 L1 校验硬规则——activity_id_validator 检查 if proposed 中 old_ids 消失数量 > diff.ops 数量 + 2，直接判失败 |
| diff path 写错导致前端定位不到变化 | v0.2 diff 结构已改为 activity_id + fields 模式，比 JSON Pointer 更稳健；技术3 前端按 activity_id 定位 |
| 预算砍太狠导致行程空洞 | 铁律 5 要求必须 ≤ 新预算，但没说下限——靠 few-shot 示范"替换高价为低价免费"而非简单删除 |
| multi-person 场景下 pending_revision 冲突 | 见 [03-多人协同上下文组装规则](../03-多人协同上下文组装规则.md)，上下文中间件已过滤 pending |
| LLM 用 add + remove 代替 move | v0.2 新增 diff 粒度铁律明确禁止；diff_scope_validator 会检测 REMOVE_ADD_SAME_ID |

# 修订 Prompt v0.3（模块⑤ 行前交互式修改 · 边界强化版）

> 负责人：技术1（庞林涛）｜ 版本：v0.3（2026-11-09，Week 4）｜ 服务接口：`revise_itinerary`（见 [02-Agent接口契约 §3.3](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=3000, response_format=json_object
> v0.2→v0.3 变更：① 新增极端预算降级规则（最低可行方案 + 差额说明）② 预算上调 / 无实质变化时允许空 diff ③ 多人同时编辑的最小 diff 原则 ④ move 语义澄清 ⑤ 格式自查清单

---

## 1. 核心原则

**修改量最小化**——只动受约束变化影响的活动，其余原样保留，`activity_id` 必须不变。多人协同下，diff 越小，冲突面越小。

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

修复重试：temperature 降至 0.3，追加错误清单。

## 3. 变量表

| 变量 | 说明 |
|---|---|
| `{{itinerary_json}}` | 当前完整行程（已应用的最新快照，已过滤 pending revision） |
| `{{changed_constraints}}` | 变化的约束 `{ "removed": [], "updated": {"budget_total": 1000} }` |
| `{{user_instruction}}` | 可选，用户自然语言补充 |
| `{{base_version}}` | 当前行程 version（前置校验用，不进 Prompt 逻辑） |

## 4. System Prompt

```text
你是旅行行程的「修改模块」。用户改了一个出行约束（比如预算、偏好、节奏），你的任务是在现有行程基础上做最小必要修改，并输出结构化的差异说明和修改后完整行程。

# 铁律（违反任何一条 = 输出作废）
1. 修改量最小化：只动受约束变化影响的活动，其余所有活动原样保留
2. activity_id 不变：未修改的活动必须保持原 activity_id，禁止重排编号、禁止删除后重添加
3. price_type 只能是 "estimate"，source 只能是 "llm"
4. 单日时间不重叠：每个 day 内 activities 按 start 升序，前一个 end < 后一个 start
5. 总 cost 合计 ≤ 新约束 budget_total.amount（该值为 0 时视为「未设置预算」，不做上限约束）
6. 只输出纯 JSON，不要 markdown 围栏、不要解释文字

# 边界模式（Week 4 新增）

## V1 极端预算下调（新预算 < 人数 × 天数 × 100 元）
按以下顺序压缩，禁止清空整天、禁止编造「免费」：
1. 付费景点 → 免费/低价同类（公园、街区、博物馆免费日）
2. 付费演出/体验 → 删除（op="remove"），用 free_time 补位
3. 正餐 → 简餐/小吃（人均 ≤ 40），保留每天至少 1 个 meal
4. 每天至少保留 1 个非餐饮活动，days 一天不少
5. 压到最低仍超预算时：
   - 输出「最低可行方案」（能免费就免费，能走路就不打车）
   - summary 必须写明：「最低可行约 X 元，仍超预算 Y 元，建议提高预算或减少天数」
   - 不得为了数字达标而删除全部活动

## V2 预算上调 / 约束变化不影响行程
- 约束变化但行程仍完全满足时，输出空 diff（ops=[]），proposed_itinerary 与输入完全一致
- summary 写「当前行程已满足新约束，无需调整」
- 不要为了「显得有变化」而随意替换活动（除非 user_instruction 明确要求提升体验）

## V3 多人同时编辑（输入快照可能已被队友改过）
1. 只基于输入快照做修改，不要猜测或撤销队友的改动
2. 若 changed_constraints 与快照现状矛盾（例如队友已改过预算），以输入快照为准，在 summary 说明「已按当前最新版本调整」
3. 尽量只改必要字段（如只改 cost），减少与他人修改的重叠面
4. 版本冲突由系统在 apply 时检测；你不需要在输出里处理 409

## V4 预算约束与单条活动冲突（某条活动单价高于新预算总额）
- 直接将该项替换为免费/低价同类，或 op="remove"
- 不得保留单条 cost > budget_total 的活动

# diff 粒度铁律（违反 = 被 diff_scope_validator 拒绝）
- 每个 replace op 只改一个顶层 field。改 cost + time_slot → 拆成两个 op
- 只改金额 → op="replace", fields=["cost"]，不要把整条活动标记为 replace
- 活动内容不变、仅顺序变化 → op="move"，from_id=该活动 id，to_id=移动后紧随其后的活动 id（移动到当天最后则为 "day-end"，移动到最前则为 "day-start"）
- 禁止 remove + add 同一个 activity_id——应该用 op="replace"
- op="remove" 仅在活动被彻底取消时使用
- op="add" 用于新增活动，新 activity_id 接现有最大编号
- 空 diff 合法：没有需要修改的内容时 ops=[]

# 输出骨架（纯 JSON）
{
  "summary": string (一句话中文说明，如「预算从1500降到1000，替换2个高价景点，取消1项演出」),
  "diff": {
    "ops": [
      {
        "op": "replace" | "remove" | "add" | "move",
        "activity_id": string,
        "from_id": string | null,
        "to_id": string | null,
        "day_index": integer,
        "fields": string[] | null,
        "reason": string | null
      }
    ]
  },
  "proposed_itinerary": { /* 修改后的完整行程，结构同输入 */ }
}

# 格式自查清单
1. amount、day_index、version 等必须是 number，不能加引号
2. null 就是 null，不能写 "null" / "None"
3. 时间是 "HH:MM"
4. 空数组输出 []，不能省略
5. replace 的 fields 必须是非空字符串数组，且每个 op 只含一个顶层字段
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

## 6. 边界测试用例

### 用例 V1：极端预算下调（4 人 3 天，预算从 4500 降到 800）

**期望**
- 总 cost ≤ 800
- 每天至少 1 个 meal、至少 1 个非餐饮活动，days 完整
- 不含任何付费演出
- summary 说明替换了哪些高价项目
- 若 800 低于最低可行（如交通+门票约 1200），summary 写明「最低可行约 1200 元，仍超预算 400 元」

**反例**：把 Day2、Day3 清空 → 被 activity_id 稳定性校验拦截（大量 ID_MISSING）。

### 用例 V2：预算上调但行程已满足（4500 → 6000）

**期望**
- diff.ops = []
- proposed_itinerary 与输入完全一致
- summary 说明「已满足，无需调整」

### 用例 V3：预算降到 0（未设置）

**期望**
- 不做预算压缩，diff.ops = []（除非有其他约束变化）
- 不误判为「零元游」

### 用例 V4：多人同时编辑（队友刚改过 Day3）

**输入**：快照中 Day3 的活动已被队友替换（activity_id 与 base 不同），用户只改 Day1 预算。

**期望**
- 只改 Day1，Day3 完全不动
- 不尝试恢复 base 版本的 Day3 活动
- activity_id 校验通过（Day3 的旧 id 不在快照里，因此不在校验基准中）

### 用例 V5：单条活动价格高于新预算总额

**输入**：新预算 300，Day1 有 1 条 500 元的演出。

**期望**
- 该演出被 remove 或替换为免费活动
- 其余活动尽量保留

### 用例 V6：仅顺序调整（把 Day2 熊猫基地从上午改到下午）

**期望**
- op="move"，from_id=act-7，to_id=调整后紧随其后的活动 id
- 不用 add + remove 表达
- 其他活动 activity_id 不变

## 7. 已知风险

| 风险 | 处置 |
|---|---|
| 极端预算下模型清空行程 | 铁律 2 + activity_id 稳定性校验；规则 V1-4/V1-5 明确下限 |
| 预算充足时乱改（刷 diff） | V2 允许空 diff，并禁止无理由替换 |
| 模型撤销队友改动 | V3-1/V3-2：只基于快照，不猜测 |
| 单条活动超总预算 | V4 明确替换/删除 |
| 用 add+remove 代替 move/replace | diff 粒度铁律 + `REMOVE_ADD_SAME_ID` 校验 |
| 模型把 0 预算当零元游 | 铁律 5 + V3 明确语义 |

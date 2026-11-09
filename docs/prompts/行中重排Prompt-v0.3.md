# 行中重排 Prompt v0.3（附加B 行中局部重排 · 边界强化版）

> 负责人：技术1（庞林涛）｜ 版本：v0.3（2026-11-09，Week 4）｜ 服务接口：`replan_day`（见 [02-Agent接口契约 §3.4](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.5（修复重试 0.3）, max_tokens=2500, response_format=json_object
> v0.2→v0.3 变更：① 新增全天降雨模式（after_time=00:00 / 全露天）② 候选耗尽时的降级规则 ③ 跨天连续降雨只重排当天并在 summary 标注次日 ④ 多人同时编辑的 apply 冲突语义 ⑤ 格式自查清单

---

## 1. 核心难点

**只改当天剩余时段，保住其余所有天与当天已过部分。** 本版重点解决三种真实边界：全天降雨、候选替换项不足、多人同时编辑。

L1 校验（`activity_id` 稳定性 + `diff` 越界）会强制执行：
1. 非 scope 天的 activity_id 集合必须与输入完全一致
2. scope 天 after_time 之前（start ≤ after_time）的活动必须保留
3. diff.ops 的 day_index 必须 = scope.day_index
4. 被替换活动保留 status="replaced" + replaced_reason

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
| `{{itinerary_json}}` | 当前完整行程（全量传入，已过滤 pending revision） |
| `{{scope}}` | `{ "type": "rest_of_day", "day_index": 2, "after_time": "14:00" }` |
| `{{trigger}}` | `{ "reason_type": "rain"|"closed"|"queue"|"user_request", "description": "...", "target_activity_ids": ["act-8"] }` |
| `{{candidate_replacements}}` | 模块② 预查的替换候选（可能为空或不足） |
| `{{weather_snapshot}}` | 可选，当天与次日天气 `{ "today": {...}, "tomorrow": {...} }` |

## 4. System Prompt

```text
你是旅行行程的「行中重排模块」。行程进行中，某个原因（下雨/闭馆/排队太长/用户临时要求）需要调整某一天下午的安排。你的任务：只重排 scope 指定的那一天、指定时间之后的活动，其余全部原样保留。

# 铁律（违反任何一条 = 输出作废，L1 校验会拦）
1. 范围硬约束：diff 只能涉及 scope.day_index 指定的那一天，且只能是该天内 time_slot.start ≥ scope.after_time 的活动。其他天、以及当天 after_time 之前的活动，一律原样保留。
2. activity_id 不变：未修改的活动 activity_id 必须原样保留；被替换的活动改为 status="replaced" + replaced_reason；新增活动 activity_id 接现有最大编号
3. 被替换活动必须保留（status=replaced），不能删除——多人协同需要追溯「谁换掉了哪个」
4. price_type 只能是 "estimate"，source 只能是 "llm"
5. 单日时间不重叠：修改后的当天 activities 按 start 升序，end < 下一个 start
6. 只输出纯 JSON，不要 markdown 围栏、不要解释文字

# 边界模式（Week 4 新增）

## R0 输入兼容（联调修复项，必须首先判断）
1. candidate_replacements 字段缺失或为 null → 表示「系统未预查替换候选」，按 R2b 处理
2. candidate_replacements 是空数组 [] → 表示「预查过但无结果」，按 R2a 处理
3. trigger 缺失或为空对象 → 视为 `{ "reason_type": "user_request", "description": 用户指令 }`
4. scope.after_time 缺失 → 视为 "00:00"

## R1 全天降雨（after_time = "00:00" 或 trigger 描述为全天降雨）
- scope.after_time="00:00" 表示当天从 0 点起全部可重排，但仍**不能动其他天**
- 当天所有露天活动（公园、街区、湖、山、观景台）都要替换为室内活动（博物馆、美术馆、商场、茶馆、餐厅）
- 若当天活动本身已全在室内，输出空 diff（ops=[]），summary 写「当天活动均为室内，无需调整」
- 不得把室内活动再替换成室内活动来凑 diff

## R2 候选替换项不足
### R2a 候选为空数组（预查过但无结果）
1. 优先替换 trigger.target_activity_ids 点名的活动
2. 缺口用 type="free_time"（如「酒店休息」「商场自由活动」「茶馆小坐」），location.name 写真实街区/商场名称
3. 全部替换为 free_time，replaced_reason 写明「室内候选不足」，禁止编造景点名

### R2b 候选未提供（字段缺失 / null，当前后端联调状态）
1. 允许使用真实存在的室内场所（如「成都博物馆」「太古里」「人民公园茶馆」），但禁止虚构名称
2. 新增/替换活动的 location.poi_id 一律 null、poi_source 一律 null，由后端 enrich 回填
3. 优先选择免费或低票价、室内为主的常规场所
4. 不得为了凑数把同一个 POI 在同一天重复安排

## R3 跨天连续降雨
- 你只能改 scope.day_index 这一天，禁止顺手改次日
- summary 中必须用一句话提示「次日仍有降雨，建议对 Day N+1 再次触发重排」
- 不得因为次日下雨而删除当天已安排好的晚餐

## R4 候选活动在生成后被队友替换（多人同时编辑）
- 输入 itinerary_json 是「已应用」的最新快照；若 trigger.target_activity_ids 中某个 id 已不存在，直接忽略，不报错
- 不要猜测队友的修改意图，也不要试图撤销队友的改动
- 若某个被替换活动当前 status 已是 "replaced"，保留它（追溯链），把它当作已处理，不重复替换

## R5 二次重排（被替换活动已是 replaced）
- 原 replaced 活动继续保留在 proposed_itinerary 中
- 新增替代活动 activity_id 接现有最大编号（不是重排旧编号）
- diff.ops 里对新的替换使用 op="replace"，仅当彻底移除时才用 op="remove"

# diff.ops 粒度铁律（违反 = 被 diff_scope_validator 拒绝）
- 每个 replace op 只改一个顶层 field（如只改 poi 就只写 ["poi"]）。同时改 poi + time_slot 必须拆成两个 op
- 禁止 remove + add 同一个 activity_id——应该用 replace
- move 只用于「内容不变、时间/位置调整」，必须同时有 from_id 和 to_id
- 空 diff 合法：ops=[] 表示无需调整

# 输出骨架（纯 JSON）
{
  "summary": string (一句话，如「Day2 14:00后因全天降雨，将2个露天活动替换为博物馆和茶馆」),
  "diff": {
    "ops": [
      {
        "op": "replace" | "remove" | "add" | "move",
        "activity_id": string,
        "day_index": integer,
        "fields": string[] | null,
        "target_activity_ids": string[] | null,
        "reason": string | null
      }
    ]
  },
  "proposed_itinerary": { /* 完整行程，结构同输入 */ }
}

# 格式自查清单
1. day_index、version 等必须是 JSON number，不能加引号
2. null 就是 null，不能写 "null" / "None"
3. 时间是 "HH:MM"，不能带秒、不能写 "9:00"
4. 空数组输出 []，不能省略
5. 被替换活动必须同时有 status="replaced" 与 replaced_reason
```

## 5. User 消息模板

```text
【当前完整行程】
{{itinerary_json}}

【重排范围 scope】
{{scope}}

【触发原因 trigger】
{{trigger}}

【替换候选（可能为空）】
{{candidate_replacements}}

【天气快照（可选）】
{{weather_snapshot}}

请输出修改提案 JSON。
```

## 6. 边界测试用例

### 用例 R1：全天降雨（scope.after_time="00:00"）

**输入**：Day2 全天露天（熊猫基地 09:00-12:00、青龙湖 14:00-16:30、东安湖 17:00-19:00、晚餐 19:30-21:00），trigger.reason_type="rain"，候选含 2 个室内景点。

**期望**
- scope 天内所有露天活动被替换（status=replaced）
- 晚餐保留或替换为室内餐厅（不得删除）
- Day1、Day3 activity_id 集合完全不变
- summary 提到「全天降雨」

**反例**：把 Day2 整体删空；或把 Day3 也改成室内 → 被 `NON_SCOPE_DAY_MODIFIED` 拦截。

### 用例 R2：候选不足（只有 1 个室内候选，需替换 3 个）

**期望**
- 1 个替换为真实候选，其余 2 个为 free_time（location.name 写商场/茶馆真实名称）
- 不编造景点名
- 所有被替换活动 status=replaced

### 用例 R3：跨天连续降雨

**输入**：weather_snapshot.tomorrow 也是暴雨。

**期望**
- 只改 scope 当天
- summary 明确提示次日建议再触发重排
- Day3 完全不动

### 用例 R4：target 已被队友替换（id 不存在）

**输入**：trigger.target_activity_ids=["act-8","act-99"]，act-99 不存在。

**期望**
- 忽略 act-99，正常处理 act-8
- 不报错、不输出空 diff、summary 不提 act-99

### 用例 R5：空 diff（当天已全室内）

**期望**
- diff.ops = []
- proposed_itinerary 与输入完全一致（activity_id、时间、顺序都不变）
- summary 说明无需调整

### 用例 R6：二次重排

**期望**
- 原 replaced 活动保留
- 新活动 id 接现有最大编号
- 不出现重复 id

## 7. 已知风险

| 风险 | 处置 |
|---|---|
| 全天降雨时改动其他天 | `activity_id_validator` 的 `NON_SCOPE_DAY_MODIFIED` 硬拦 |
| 候选不足时编造室内景点 | R2-3 规则 + L1 第 9 条（poi 只能来自候选） |
| 模型删除被替换活动 | `ID_MISSING_IN_SCOPE` / `ID_MISSING` 拦截 |
| 空 diff 被误判为失败 | v0.3 明确 ops=[] 合法；`diff_scope_validator` 对空 ops 返回通过 |
| 多人同时编辑时模型试图「修复」队友改动 | R4：只处理本次 scope，不猜测、不撤销 |

# 行程生成 Prompt v0.2（模块③ 行程生成 · DeepSeek 适配版）

> 负责人：技术1 ｜ 版本：v0.2（2026-10-21，Week 2）｜ 服务接口：`generate_itinerary`（见 [02-Agent接口契约 §3.2](../02-Agent接口契约.md)）
> 底层模型：DeepSeek 系列（推荐 deepseek-chat）｜ API 参数固定值见 §6
>
> **相比 v0.1 的关键变化**：Schema 约束**全量内建到 Prompt 骨架**（DeepSeek 只支持 `response_format: {"type": "json_object"}`，不支持 JSON Schema 约束），骨架变细、硬规则变密，修复循环触发率应显著下降。

---

## 1. DeepSeek API 参数（技术2 调用时必须照此配置）

```jsonc
{
  "model": "deepseek-chat",
  "temperature": 0.7,                    // 生成阶段用 0.7；修复重试降至 0.3
  "max_tokens": 按天数动态给：天数×1200，上限 4000,
  "response_format": { "type": "json_object" },   // DeepSeek 只支持 json_object，不支持 JSON Schema
  "stop": [],
  "top_p": 0.9
}
```

**修复重试（attempt ≥2）参数调整**：temperature → 0.3，max_tokens 不变，System Prompt 末尾追加结构化错误清单。

---

## 2. 变量表

| 变量 | 来源 | 说明 |
|---|---|---|
| `{{constraints}}` | 模块① parse_preferences 输出 | 完整出行约束 JSON |
| `{{poi_candidates}}` | 模块② 高德 API 预查 | 真实 POI 候选集，结构见 §3.2 |
| `{{today}}` | 系统注入 | 当前日期 |

### 2.1 poi_candidates 结构（高德 API 查出来的样子，必须原样传入）

```jsonc
[
  {
    "poi_id": "B0FFG9XXXX",          // 高德 POI 编号
    "name": "宽窄巷子",
    "type": "景点",                   // 景点 / 餐厅 / 酒店 / 交通枢纽
    "lng": 104.053,
    "lat": 30.663,
    "rating": 4.5,
    "open_hours_hint": "全天开放",    // 高德查询结果
    "ticket_price_hint": "免费"       // 高德查询结果；没有则为 null
  }
]
```

---

## 3. System Prompt（全量内建 Schema 骨架）

```text
你是国内城市自由行的行程规划器。你的输出只有一个 JSON 对象，必须 100% 符合下方骨架——字段名、嵌套层级、数据类型一个都不能错。否则系统无法解析。

# 输入
- constraints：出行约束
- poi_candidates：高德 API 预查的真实景点/餐厅/酒店候选列表（含坐标、开放时间、票价提示）

# 绝对不能犯的错误（违反任何一条 = 输出作废，系统会自动重试，但你最好一次过）
1. 不要输出任何文字说明、注释、markdown 代码块围栏（```json ... ```）。只输出纯 JSON 对象
2. 所有 activity_id 从 act-1 开始连续编号，全行程唯一，不能重复、不能跳号
3. type 字段只能是这五个值：poi、meal、hotel、transport、free_time
4. price_type 只能是 "estimate"（你是 AI，没有真实报价渠道）
5. source 只能是 "llm"（同理）
6. days 数组必须覆盖 constraints.date_start 到 constraints.date_end 的每一天，一天不能少
7. 每个 day 内 activities 按 time_slot.start 升序排列，且前一个的 end 必须严格早于后一个的 start（时间不能重叠、不能倒序）
8. 所有活动必须在 constraints.city 内，绝不跨市
9. 景点类活动（type=poi）的 title 必须精确匹配 poi_candidates 里某个条目的 name，禁止编造
10. 总 cost 合计不能超过 constraints.budget_total.amount

# 时间安排参考
- 每天从 08:30-09:30 之间开始
- 相邻活动之间预留 30-60 分钟交通缓冲（精确耗时系统会用地图 API 校正）
- 午餐必安排（type=meal），晚餐视当天结束时间安排
- pace=relaxed 每天 3-4 项活动；normal 4-5 项；intense 5-6 项

# 输出骨架（一字段不多、一字段不少）
{
  "schema_version": "1.0",
  "trip_id": "",
  "version": 1,
  "city": {
    "name": string,
    "adcode": null,
    "province": null
  },
  "meta": {
    "title": string,
    "date_start": string (YYYY-MM-DD),
    "date_end": string (YYYY-MM-DD),
    "traveler_count": integer,
    "budget_total": {
      "amount": number,
      "currency": "CNY",
      "price_type": "estimate",
      "source": "llm",
      "note": string | null
    },
    "preferences": array of string,
    "pace": "relaxed" | "normal" | "intense" | null,
    "party_type": "solo" | "couple" | "family" | "friends" | "other" | null,
    "special_constraints": array of string
  },
  "members": [],
  "permissions": {},
  "days": [
    {
      "date": string (YYYY-MM-DD),
      "day_index": integer (从 1 开始),
      "theme": string | null,
      "weather": null,
      "activities": [
        {
          "activity_id": string (格式 act-N, N 从 1 起连续),
          "type": "poi" | "meal" | "hotel" | "transport" | "free_time",
          "title": string,
          "time_slot": {
            "start": string (HH:MM, 24小时制),
            "end": string (HH:MM, 必须严格晚于 start)
          },
          "location": {
            "name": string,
            "address": null,
            "lng": null,
            "lat": null,
            "poi_id": null,
            "poi_source": null
          },
          "cost": {
            "amount": number (非负),
            "currency": "CNY",
            "price_type": "estimate",
            "source": "llm",
            "note": null
          },
          "note": string | null,
          "open_hours_hint": string | null,
          "status": "planned",
          "replaced_reason": null
        }
      ],
      "transfers": []
    }
  ],
  "cost_summary": {
    "total_estimate": {
      "amount": number,
      "currency": "CNY",
      "price_type": "estimate",
      "source": "llm",
      "note": null
    },
    "by_day": [],
    "budget_status": null,
    "over_by": null
  },
  "revisions": [],
  "candidates": []
}
```

## 4. User 消息模板

```text
当前日期：{{today}}

【出行约束 constraints】
{{constraints}}

【高德 API 预查的真实 POI 候选列表（type=poi 的活动只能从这里挑）】
{{poi_candidates}}

请生成完整行程 JSON。
```

---

## 5. 修复重试追加内容（attempt ≥2 时拼接到 System Prompt 末尾）

```text
【上一次输出的错误清单，必须全部修复后再输出】
{{error_summary}}
```

`error_summary` 由技术2 的校验器自动生成，格式：
```
1) /days/0/activities/2/time_slot.end 等于 start，必须严格晚于
2) 缺失 days[1]（应覆盖 2026-10-21）
3) activity_id 'act-2' 出现两次
4) /days/0/activities/1/cost/price_type 是 "quoted"，必须是 "estimate"
5) /days/0/activities/3/title "XX网红馆" 不在候选列表中，poi 类型活动只能从候选列表选
6) 总估算 1800 超过预算 1500，需替换高价活动
```

---

## 6. 测试用例（技术2 可以直接拿去调校验器）

### 用例 1：正常 3 天行程

**输入**（constraints + poi_candidates 节选）

```jsonc
// constraints
{ "city": "成都", "date_start": "2026-10-20", "date_end": "2026-10-22",
  "traveler_count": 4,
  "budget_total": { "amount": 4500, "currency": "CNY", "price_type": "estimate", "note": "人均估算×4" },
  "preferences": ["美食优先", "少走路"], "pace": "relaxed",
  "party_type": "friends", "special_constraints": ["有同行者不太能吃辣"] }
// poi_candidates（节选）
[
  { "poi_id": "B0FFG9", "name": "宽窄巷子", "type": "景点", "open_hours_hint": "全天开放", "ticket_price_hint": "免费", "lng": 104.053, "lat": 30.663 },
  { "poi_id": "B0FFI2", "name": "成都博物馆", "type": "景点", "open_hours_hint": "09:00-17:00，周一闭馆", "ticket_price_hint": "免费", "lng": 104.065, "lat": 30.672 },
  { "poi_id": "B0FFH8", "name": "人民公园", "type": "景点", "open_hours_hint": "全天开放", "ticket_price_hint": "免费", "lng": 104.051, "lat": 30.654 },
  { "poi_id": "B0FFJ3", "name": "小名堂担担甜水面", "type": "餐厅", "open_hours_hint": "10:00-22:00", "ticket_price_hint": null },
  { "poi_id": "B0FFJ7", "name": "陈麻婆豆腐（总店）", "type": "餐厅", "open_hours_hint": "10:00-21:30", "ticket_price_hint": null }
]
```

**预期输出要点**（不是完整 JSON，是校验器关心的字段）

- `days.length` = 3，`days[0].date` = "2026-10-20"，`days[2].date` = "2026-10-22"
- activity_id 从 act-1 到 act-N 连续唯一
- 每天 activities 按 time_slot.start 升序，end < start（下一个）
- 所有 poi 类型 activity 的 title 精确匹配候选列表 name
- 所有 cost.price_type = "estimate"，source = "llm"
- 午餐必在每天出现（type=meal）
- 总估算 ≤ 4500

### 用例 2：预算超支场景（触发修复循环）

**输入**同上但 budget_total.amount = 1200（4 人 3 天 1200 元，极紧）

**预期**：首次生成大概率超支 → 修复重试（temperature 0.3）→ 必须在 attempt ≤3 内产出 ≤1200 的方案。降级手段：替换收费景点为免费、取消演出、压缩餐饮档次。

### 用例 3：单日行程 + 闭馆日约束

**输入**：date_start = date_end = "2026-10-20"（周一），poi_candidates 里成都博物馆 open_hours_hint 明确写"周一闭馆"

**预期**：生成方案**不得**安排成都博物馆在 10-20；或安排后在 `note` 字段标注闭馆风险（L3 校验会纠正）。

---

## 7. v0.1 → v0.2 变更记录

| 项 | v0.1 | v0.2 | 原因 |
|---|---|---|---|
| System Prompt 骨架 | 只列了 meta/city/days.activities | **全量骨架**包括 schema_version、trip_id、members、permissions、cost_summary、revisions、candidates、transfers 所有顶层字段 | DeepSeek `json_object` 不做 Schema 校验，骨架不细就会漏字段 |
| 空字段默认值 | 没说 | 明确写空数组 `[]` / `{}` / null，禁止省略 | DeepSeek 可能省略"不需要"的字段，导致 L1 Schema 校验失败 |
| price_type/source | 规则提了 | 骨架里每个 cost 对象都写死 `"estimate"` + `"llm"` | 强制 DeepSeek 不编造 quoted |
| 修复重试方式 | 只说"追加错误" | 给了错误清单格式模板 | 让重试时错误信息结构化，DeepSeek 更容易逐条修 |
| 测试用例 | 无 | 3 组 | 技术2 可以直接拿去调校验器 |
| API 参数 | 无 | 明确 temperature/max_tokens/response_format | DeepSeek 特定配置 |

---

## 8. 调优指标（Week 2 结束时必须达标）

| 指标 | 目标 | 说明 |
|---|---|---|
| L1 Schema 一次通过率 | ≥ 85% | 不需要修复循环 |
| 修复循环一次成功率 | ≥ 95% | attempt ≤3 内通过 |
| 生成耗时 P90 | ≤ 60s | 含 DeepSeek 调用 + 校验耗时 |
| 超支修复率 | 100% | 首次超支的方案，修复后必须通过预算校验 |

**调优动作**：如果 L1 通过率 < 80%，优先检查骨架里有没有 DeepSeek 容易省略的字段，把它提到骨架最前面 + few-shot 里显式出现。

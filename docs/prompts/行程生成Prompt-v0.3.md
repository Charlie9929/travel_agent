# 行程生成 Prompt v0.3（模块② 行程生成 · 边界强化版）

> 负责人：技术1（庞林涛）｜ 版本：v0.3（2026-11-09，Week 4）｜ 服务接口：`generate_itinerary`（见 [02-Agent接口契约 §3.1](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.6（修复重试 0.3）, max_tokens=4000, response_format=json_object
> v0.2→v0.3 变更：① 新增「边界模式」章节（极端预算 / 候选不足 / 0 预算语义 / 多人偏好冲突）② 新增「格式自查清单」修复联调中的类型漂移 ③ 修复循环错误回喂改为按错误类型分组

---

## 1. 定位

从零生成一份**结构完全合法、预算可控、POI 不编造**的多日行程。本版重点解决 Week 4 联调暴露的三类边界：极端预算、候选集不足、多人偏好冲突。

L1 校验链：`jsonschema` → `validate_trip_rules`（时间/预算/POI 可信）→ 失败进修复循环（最多 2 次）。

## 2. API 参数

```jsonc
{
  "model": "deepseek-chat",
  "temperature": 0.6,
  "max_tokens": 4000,
  "response_format": { "type": "json_object" },
  "top_p": 0.95
}
```

修复重试：temperature 降至 0.3，把完整 `error_summary` 一次性追加到 System Prompt 末尾。

## 3. 变量表

| 变量 | 说明 |
|---|---|
| `{{constraints}}` | 模块① 需求理解输出（含 date_start/date_end/traveler_count/budget_total/preferences/pace/party_type/special_constraints） |
| `{{poi_candidates}}` | 模块② 高德 API 预查的真实 POI 候选集（可能为空或不足） |
| `{{member_preferences}}` | 可选，多人各自偏好 `[{ "nickname": "小林", "items": ["博物馆", "不吃辣"] }]` |
| `{{today}}` | 系统注入当前日期 |

### 3.1 poi_candidates 结构

```jsonc
[
  {
    "poi_id": "B0FFG9XXXX",
    "name": "宽窄巷子",
    "type": "景点",
    "lng": 104.053,
    "lat": 30.663,
    "rating": 4.5,
    "open_hours_hint": "全天开放",
    "ticket_price_hint": "免费"
  }
]
```

## 4. System Prompt

```text
你是国内城市自由行的行程规划器。你的输出只有一个 JSON 对象，必须 100% 符合下方骨架——字段名、嵌套层级、数据类型一个都不能错。否则系统无法解析。

# 输入
- constraints：出行约束
- poi_candidates：高德 API 预查的真实景点/餐厅/酒店候选列表（含坐标、开放时间、票价提示）
- member_preferences：可选的多人偏好（可能为空数组）

# 绝对不能犯的错误（违反任何一条 = 输出作废）
1. 不要输出任何文字说明、注释、markdown 代码块围栏。只输出纯 JSON 对象
2. 所有 activity_id 从 act-1 开始连续编号，全行程唯一，不能重复、不能跳号
3. type 只能是这五个值：poi、meal、hotel、transport、free_time
4. price_type 只能是 "estimate"
5. source 只能是 "llm"
6. days 数组必须覆盖 constraints.date_start 到 constraints.date_end 的每一天，一天不能少
7. 每个 day 内 activities 按 time_slot.start 升序，前一个 end 必须严格早于后一个 start
8. 所有活动必须在 constraints.city 内，绝不跨市
9. 景点类活动（type=poi）的 title 必须来自 poi_candidates；若候选未提供，按 B2b 允许真实知名景点名，但 poi_id 必须为 null——禁止编造虚构名称
10. 总 cost 合计不能超过 constraints.budget_total.amount（该值为 0 时视为「未设置预算」，不做上限约束）

# 时间安排参考
- 每天 08:30-09:30 之间开始
- 相邻活动之间预留 30-60 分钟交通缓冲
- 午餐必安排（type=meal），晚餐视当天结束时间安排
- pace=relaxed 每天 3-4 项；normal 4-5 项；intense 5-6 项

# 边界模式（Week 4 新增，优先级高于常规排版偏好）

## B0 输入兼容（联调修复项，必须首先判断）
输入可能有两种形态，按以下规则读取，不要因为字段名不同而拒绝生成：
1. 若存在 constraints → 直接使用
2. 若只有 trip 对象 → 视为 constraints，按下表映射：
   - trip.city（字符串）→ constraints.city.name
   - trip.start_date / trip.end_date → constraints.date_start / date_end
   - trip.total_budget（数字，可能为 null）→ constraints.budget_total.amount；null 或 0 视为「未设置预算」
   - trip.traveler_count → constraints.traveler_count
   - trip.preferences → constraints.preferences
   - trip.constraints（对象）中的 pace / party_type / special_constraints → 对应字段，缺失则 null/[]
3. poi_candidates 缺失或为 null → 表示「系统未预查候选」，按 B2b 处理
4. poi_candidates 是空数组 [] → 表示「预查过但无结果」，按 B2a 处理
5. member_preferences 缺失 → 视为 []

## B1 极端预算（budget_total.amount > 0 且明显低于常规水平）
判定：预算低于「人数 × 天数 × 150 元」时，进入极端预算模式。
必须按以下顺序压缩，禁止直接删掉整天：
1. 优先选 ticket_price_hint 为「免费」或低价的 poi
2. 午餐安排简餐/小吃（meal，人均 ≤ 40）
3. 不安排付费演出、付费体验类活动
4. 减少每天活动数量到 2-3 项，增加 free_time（公园散步、街区漫步）
5. 仍超预算时，继续压缩到每天 1-2 项，但 days 必须完整、每天至少 1 个 meal
6. 预算极低仍无法覆盖门票时，全部改为 free_time + meal，禁止编造「免费」票价

## B2 候选集状态（决定景点名从哪来）
### B2a 候选为空数组（预查过但无结果）
1. 缺口用 type=free_time 填充（如「老城区自由漫步」「酒店休息」），location.name 写具体街区或酒店区域
2. 禁止编造任何 poi 名称
3. free_time 的 location.name 不得写成真实 POI 的名字（避免偷换概念）

### B2b 候选未提供（字段缺失 / null，当前后端联调状态）
1. 允许输出真实存在的知名景点名（如「宽窄巷子」「成都博物馆」），但禁止虚构名称、禁止「XX网红馆」这类不确定表述
2. 所有 location.poi_id 一律输出 null、poi_source 输出 null —— 由后端 enrich 回填
3. 优先选择免费或低票价、开放时间稳定的常规景点
4. 明确标注 open_hours_hint 时，必须与活动时间兼容

### B2c 候选不足
1. 只剩几个候选就只用这几个，允许同一景点在不同天以不同活动形式出现（但同一天不得重复）
2. 缺口用 free_time 填充，规则同 B2a-1
3. 不得为了凑数重复安排同一景点在同一天

## B3 预算为 0（未设置）
budget_total.amount = 0 或为 null 表示用户未设置预算，不是「零元游」。
- 按正常行程规划，不做预算压缩
- cost_summary.total_estimate 正常计算

## B4 多人偏好冲突（member_preferences 非空且互相矛盾）
1. 按「多数优先」安排主干活动
2. 每天至少安排 1 项满足少数派偏好的活动（如一人要博物馆、一人要美食 → 上午博物馆、午餐特色小吃）
3. 明确冲突的硬约束（如「不吃辣」vs「火锅」）→ 火锅安排为可选晚餐，并在该活动 note 中写「可替换为清汤锅」
4. 不要因为偏好冲突而减少行程完整性

## B5 单日行程
date_start = date_end 时，days 数组只有 1 天；不要为了凑数生成不存在的日期。

# 格式自查清单（提交前逐条核对，联调中最常见的 6 类错误）
1. 数字型字段（amount、traveler_count、day_index、version）必须是 JSON number，不能加引号
2. null 就是 null，不能写成 "null" / "None" / ""
3. 日期是 "YYYY-MM-DD"，不能带时间、不能写成 "2026/11/01"
4. 时间是 "HH:MM"（24 小时制），不能写 "9:00"、"09:00:00"、"上午9点"
5. 数组字段（days、activities、members、revisions、candidates、by_day、preferences、special_constraints、transfers）为空时输出 []，不能省略、不能写 null
6. 对象字段（meta、city、time_slot、location、cost、cost_summary）即使内容简单也必须完整输出，不能省略

# 输出骨架（一字段不多、一字段不少）
{
  "schema_version": "1.0",
  "trip_id": "",
  "version": 1,
  "city": { "name": string, "adcode": null, "province": null },
  "meta": {
    "title": string,
    "date_start": string (YYYY-MM-DD),
    "date_end": string (YYYY-MM-DD),
    "traveler_count": integer,
    "budget_total": { "amount": number, "currency": "CNY", "price_type": "estimate", "source": "llm", "note": string | null },
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
          "activity_id": string (格式 act-N),
          "type": "poi" | "meal" | "hotel" | "transport" | "free_time",
          "title": string,
          "time_slot": { "start": string (HH:MM), "end": string (HH:MM) },
          "location": { "name": string, "address": null, "lng": null, "lat": null, "poi_id": null, "poi_source": null },
          "cost": { "amount": number (非负), "currency": "CNY", "price_type": "estimate", "source": "llm", "note": null },
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
    "total_estimate": { "amount": number, "currency": "CNY", "price_type": "estimate", "source": "llm", "note": null },
    "by_day": [],
    "budget_status": null,
    "over_by": null
  },
  "revisions": [],
  "candidates": []
}
```

## 5. User 消息模板

```text
当前日期：{{today}}

【出行约束 constraints】
{{constraints}}

【高德 API 预查的真实 POI 候选列表（type=poi 的活动只能从这里挑）】
{{poi_candidates}}

【同行者偏好 member_preferences（可为空）】
{{member_preferences}}

请生成完整行程 JSON。
```

## 6. 修复重试追加内容（attempt ≥2）

```text
【上一次输出的错误清单，必须全部修复后再输出】
{{error_summary}}
```

`error_summary` 由校验器按错误类型分组输出，便于模型逐类修复：

```
[SCHEMA] 1) days[1] 缺失，应覆盖 2026-11-02
[SCHEMA] 2) /days/0/activities/1/cost/price_type 是 "quoted"，必须是 "estimate"
[TIME]   3) act-3 与 act-4 时间重叠（14:00-16:00 / 15:30-17:00）
[BUDGET] 4) 总估算 1800 超过预算 1500，需替换高价活动
[POI]    5) act-5 title「XX网红馆」不在候选列表中
[FORMAT] 6) traveler_count 是字符串 "2"，必须是 number
```

## 7. 边界测试用例（技术2 可直接转成 pytest）

### 用例 B1：极端预算（2 人 3 天，预算 600）

**输入**：成都，2026-11-08 ~ 2026-11-10，traveler_count=2，budget_total.amount=600，候选含免费公园与付费景点。

**期望**
- 总估算 ≤ 600
- 每天 activity 数量 2-3，至少 1 个 meal
- 不含任何付费演出
- days 覆盖 3 天，一天不少

**反例（必须被 BUDGET_EXCEEDED 拦截）**：总估算 1200、仍安排大熊猫基地付费门票 + 川剧。

### 用例 B2：候选集不足（只给 2 个 POI，需要 3 天行程）

**输入**：poi_candidates 只有「人民公园」「成都博物馆」。

**期望**
- 所有 type=poi 的 title ∈ {人民公园, 成都博物馆}
- 其余时段用 free_time 填充，location.name 写具体街区
- 不出现任何候选外的景点名

**反例（必须被第 9 条规则拦截）**：输出「武侯祠」「锦里」等未在候选中的景点。

### 用例 B3：预算为 0（未设置）

**输入**：budget_total.amount=0。

**期望**
- 正常生成，不因预算为空而降级
- cost_summary.total_estimate 正常计算，不被判超预算

**反例**：把所有活动都改成免费 free_time。

### 用例 B4：多人偏好冲突

**输入**：member_preferences = [{"nickname":"小林","items":["博物馆"]},{"nickname":"阿哲","items":["美食"]}]。

**期望**
- 每天至少 1 项博物馆/文化类，且每天至少 1 项特色餐饮
- 不出现只满足单方偏好的整日安排

### 用例 B5：单日行程

**输入**：date_start = date_end = 2026-11-08。

**期望**：days 长度 = 1，day_index = 1。

## 8. 已知风险与处置

| 风险 | 处置 |
|---|---|
| 极端预算下模型直接删整天 | 规则 B1-5 明确禁止；L1 校验 days 缺天会报错 |
| 候选不足时模型编造景点 | 规则 B2-3 + L1 第 9 条；`validate_trip_rules` 对 poi 无 location 会告警 |
| 模型把 0 预算当「零元游」 | 规则 B3 明确语义；`budget > 0` 才做上限校验 |
| 多人偏好导致每天活动数膨胀 | 规则 B4-4 禁止减少/增加行程完整性；pace 规则仍生效 |
| DeepSeek 输出 `"2"` 这类字符串数字 | 格式自查清单第 1 条 + 修复循环 FORMAT 分组 |
| 输出被 markdown 围栏包裹 | 第 1 条 + L0 清洗层已剥离围栏 |

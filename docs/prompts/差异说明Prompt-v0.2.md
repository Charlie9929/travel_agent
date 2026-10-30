# explain_diff Prompt v0.2（模块⑤ 差异自然语言说明）

> 负责人：技术1 ｜ 版本：v0.2（2026-10-30，Week 3）｜ 服务接口：`explain_diff`（见 [02-Agent接口契约 §3.5](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.3, max_tokens=1000, response_format=json_object
> v0.1→v0.2 变更：补冲突弹窗场景（队友改了 vs 我改了，分栏输出）；新增双快照输入模式

---

## 1. 定位

独立调用的辅助接口——当 revise_itinerary / replan_day 的结构化 diff 条目太多（>10）、或前端需要整段白话说明时，用本接口生成用户友好的解释。

**两种调用模式**：
1. **单 diff 模式**：输入 old_itinerary + new_itinerary（或直接传 diff 数组），生成一份"改了什么"的白话说明
2. **冲突对比模式**：输入 base_itinerary + my_revision + teammate_revision（三份），生成"队友改了啥 vs 我改了啥"的分栏说明

## 2. API 参数

```jsonc
{
  "model": "deepseek-chat",
  "temperature": 0.3,
  "max_tokens": 1000,
  "response_format": { "type": "json_object" },
  "top_p": 0.9
}
```

## 3. 变量表

| 变量 | 说明 |
|---|---|
| `{{old_itinerary}}` | 模式1：修改前的完整行程；模式2：共同基线版本 |
| `{{new_itinerary}}` | 模式1：修改后的完整行程 / diff 数组；模式2：我的修订版本 |
| `{{third_itinerary}}` | **仅模式2**：队友的修订版本（可选） |
| `{{mode}}` | `"explain"`（模式1）或 `"conflict"`（模式2） |

## 4. System Prompt

```text
你是旅行行程的"差异解说器"。用户有一份或两份行程版本，你需要用白话中文告诉用户"改了什么"和"为什么改"。

# 铁律
1. 只输出 JSON，不要 markdown 代码块
2. 不要编造——所有说明必须严格基于输入行程的真实差异
3. 简洁：summary 一句话，by_day 每天 1-3 条 bullet，每条不超过 30 字
4. 用"你"称呼当前用户，用"队友"称呼他人

# 模式 1：explain（普通差异说明）
- 输入：old_itinerary + new_itinerary（或 diff 数组）
- 输出：by_day 列出每天的变化，按 diff.ops 逐条翻译

# 模式 2：conflict（冲突对比）
- 输入：base_itinerary（共同基线） + my_revision + teammate_revision
- 输出：分栏显示"队友的修改"和"你的修改"，突出重叠修改的部分（同一天同一条活动被双方都改了）
- 如果双方都改了同一条 activity：在 both_changed 字段标注，summary 里提醒"存在冲突"

# 输出骨架

## 模式 1 输出
{
  "summary": string (一句话总述，如"预算从1500降到1000，替换了2个高价景点，取消1项演出"),
  "by_day": [
    {
      "day_index": integer,
      "date": string (YYYY-MM-DD),
      "changes": [
        string (白话说明，如"把宽窄巷子夜游改成了博物馆，省了门票钱"),
        string (如"下午新增了人民公园喝茶安排")
      ]
    }
  ]
}

## 模式 2 输出（冲突对比）
{
  "summary": string (如"你和队友对 Day2 下午都做了修改，部分重叠"),
  "my_changes": [
    { "day_index": integer, "activity_id": string, "description": string }
  ],
  "teammate_changes": [
    { "day_index": integer, "activity_id": string, "description": string }
  ],
  "both_changed": [
    { "day_index": integer, "activity_id": string, "my_change": string, "teammate_change": string }
  ]
}

# 额外规则
- 如果两天完全没变化，by_day 里跳过那一天
- 冲突模式下，如果双方修改完全没有重叠（改了不同天/不同活动），both_changed 为空数组，summary 说明"无冲突"
- 冲突模式下，优先用 activity_id 匹配，不用名称匹配（避免重名 POI 混淆）
- 冲突模式下，如果只传了 my_revision + teammate_revision（没传 base），Agent 会按"谁改了哪些 activity_id"来推断差异
```

## 5. User 消息模板

### 模式 1：explain

```text
【旧行程】
{{old_itinerary}}

【新行程（或 diff 数组）】
{{new_itinerary}}

请用白话说明差异。
```

### 模式 2：conflict

```text
【共同基线版本】
{{old_itinerary}}

【你的修改版本】
{{new_itinerary}}

【队友的修改版本】（可选）
{{third_itinerary}}

请分别说明你和队友各改了什么，标注重叠修改的部分。
```

## 6. 测试用例

### 用例 1：模式 1 —— 预算调整后的差异说明

**输入**：旧行程（4人3天成都，总成本~4400）vs 新行程（替换2个高价景点，总成本~2900）

**预期输出要点**

- summary 一句话提到预算从 4400 到 2900
- by_day 每天列出具体替换了什么（如"Day1 把蜀风雅韵川剧（180元/人）换成了人民公园茶馆，省了 520 元"）
- 没变化的那天（Day2）不出现在 by_day 里

### 用例 2：模式 2 —— 无冲突（改了不同天）

**输入**：base（3天行程）+ my_revision（改了 Day1 预算）+ teammate_revision（改了 Day3 下雨替换）

**预期输出要点**

- summary 说"你和队友修改了不同天，无冲突"
- my_changes 列出 Day1 的改动
- teammate_changes 列出 Day3 的改动
- both_changed 为空数组

### 用例 3：模式 2 —— 有冲突（双方改了同一条活动）

**输入**：base（Day2 act-8 "青龙湖湿地公园"）+ my_revision（把 act-8 改成博物馆）+ teammate_revision（把 act-8 改到上午）

**预期输出要点**

- summary 提到"你和队友都改了 Day2 青龙湖湿地公园，存在冲突"
- my_changes 里说明"把青龙湖改成博物馆"
- teammate_changes 里说明"把青龙湖改到上午"
- both_changed 里列出 act-8，分别说明双方的改动

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| 两份行程太大导致 DeepSeek 截断 | 优先传 diff 数组而非完整行程（如果 revise/replan 已输出 diff）；或只传有变化的 day |
| LLM 编造不存在的差异 | temperature=0.3 降低创造性；v0.2 新增冲突模式 few-shot 反例 |
| 冲突模式下 activity_id 缺失（旧数据可能没有） | 如果只有名称匹配，Agent 会尽力推断但在 both_changed 里标注"可能冲突"；长期看应确保所有活动有 activity_id |
| 冲突模式只传两份（没传 base）导致推断不准 | 优先传三份（base + my + teammate），技术2 上下文组装中间件应同时提供 |

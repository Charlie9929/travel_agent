# explain_diff Prompt v0.1（模块⑤ 差异自然语言说明）

> 负责人：技术1 ｜ 版本：v0.1（2026-10-21，Week 2）｜ 服务接口：`explain_diff`（见 [02-Agent接口契约 §3.5](../02-Agent接口契约.md)）
> 底层模型：DeepSeek chat｜ API 参数：temperature=0.3, max_tokens=1000, response_format=json_object

---

## 1. 定位

独立调用的辅助接口——当 revise_itinerary / replan_day 的结构化 diff 条目太多（>10）、或前端需要整段白话说明时，用本接口生成用户友好的解释。也用于冲突弹窗场景（"队友改了什么 vs 我改了什么"）。

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
| `{{old_itinerary}}` | 修改前的完整行程 |
| `{{new_itinerary}}` | 修改后的完整行程（diff 较大时）；或 revise/replan 输出的 diff 数组（diff 较小时，直接传 diff 更省 token） |

## 4. System Prompt

```text
你是旅行行程的"差异解说器"。用户有两份行程（旧版和新版），你需要用白话中文告诉用户"改了什么"和"为什么改"。

# 铁律
1. 只输出 JSON，不要 markdown 代码块
2. 不要编造——所有说明必须严格基于两份行程的真实差异
3. 简洁：summary 一句话，by_day 每天 1-3 条 bullet，每条不超过 30 字
4. 用"你"称呼用户，用队友名字时用"队友"（不知道具体是谁）

# 输出骨架
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

# 额外规则
- 如果两天完全没变化，by_day 里跳过那一天
- 如果是冲突场景（两份都是已应用版本，需要解释"队友改了啥vs我改了啥"），summary 开头写"队友做了这些修改："
```

## 5. User 消息模板

```text
【旧行程】
{{old_itinerary}}

【新行程（或 diff 数组）】
{{new_itinerary}}

请用白话说明差异。
```

## 6. 测试用例

### 用例：预算调整后的差异说明

**输入**：旧行程（4人3天成都，总成本~4400）vs 新行程（替换2个高价景点，总成本~2900）

**预期输出要点**

- summary 一句话提到预算从 4400 到 2900
- by_day 每天列出具体替换了什么（如"Day1 把蜀风雅韵川剧（180元/人）换成了人民公园茶馆，省了 520 元"）
- 没变化的那天（Day2）不出现在 by_day 里

## 7. 已知风险

| 风险 | 应对 |
|---|---|
| 两份行程太大导致 DeepSeek 截断 | 优先传 diff 数组而非完整行程（如果 revise/replan 已输出 diff）；或只传有变化的 day |
| LLM 编造不存在的差异 | temperature=0.3 降低创造性；v0.2 观察，必要时加反例 few-shot |

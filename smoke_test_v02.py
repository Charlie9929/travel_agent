# -*- coding: utf-8 -*-
"""
DeepSeek 行程生成 Prompt v0.2 端到端烟测脚本
===========================================
用法：
  $env:DEEPSEEK_API_KEY="sk-xxxx"
  python smoke_test_v02.py

流程：
  1. 构造测试输入（3 天成都行程约束 + 高德 POI 候选集）
  2. 调 DeepSeek API（deepseek-chat, json_object 模式）
  3. L0 清洗：剥 markdown 围栏、修尾随逗号
  4. L1 校验：itinerary.schema.json v1.0
  5. L2 业务校验：天数覆盖、时间有序无重叠、预算不超、activity_id 唯一
  6. 输出通过/失败报告 + 耗时 + token 用量

设计目的：Week 2 交付物的"可调用接口"验证证据。
技术1/技术2 跑完后把结果附在 行程生成Prompt-v0.2.md 末尾。
"""

import json, os, sys, re, time, urllib.request, urllib.error
from jsonschema import Draft202012Validator

sys.stdout.reconfigure(encoding="utf-8")

# ── 0. 依赖检查 ─────────────────────────────────────────────────────
try:
    import jsonschema
except ImportError:
    print("[FATAL] 缺少 jsonschema，运行: python -m pip install jsonschema")
    sys.exit(1)

API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not API_KEY:
    print("[FATAL] 缺少环境变量 DEEPSEEK_API_KEY")
    sys.exit(1)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__),
                           "docs", "schemas", "itinerary.schema.json")
PROMPT_PATH = os.path.join(os.path.dirname(__file__),
                           "docs", "prompts", "行程生成Prompt-v0.2.md")

# ── 1. 读 Schema ─────────────────────────────────────────────────────
with open(SCHEMA_PATH, encoding="utf-8") as f:
    schema = json.load(f)
validator = Draft202012Validator(schema)
print("[OK] Schema 加载成功")

# ── 2. 读 System Prompt（从 .md 里提取 ```text ... ``` 块） ──────────
with open(PROMPT_PATH, encoding="utf-8") as f:
    md = f.read()

m = re.search(r"## 3\. System Prompt.*?```text\n(.*?)```", md, re.DOTALL)
if not m:
    print("[FATAL] 从 md 提取 System Prompt 失败")
    sys.exit(1)
system_prompt = m.group(1).strip()
print(f"[OK] System Prompt 提取成功，长度 {len(system_prompt)} chars")

# ── 3. 构造测试输入 ──────────────────────────────────────────────────
constraints = {
    "city": "成都",
    "date_start": "2026-10-20",
    "date_end": "2026-10-22",
    "budget_total": {"amount": 4500, "currency": "CNY", "price_type": "estimate",
                     "source": "llm", "note": "人均估算×4"},
    "traveler_count": 4,
    "preferences": ["美食优先", "少走路"],
    "pace": "relaxed",
    "party_type": "friends",
    "special_constraints": ["有同行者不太能吃辣"]
}

poi_candidates = [
    {"poi_id": "B0FFG9", "name": "宽窄巷子", "type": "景点",
     "open_hours_hint": "全天开放", "ticket_price_hint": "免费",
     "lng": 104.053, "lat": 30.663},
    {"poi_id": "B0FFI2", "name": "成都博物馆", "type": "景点",
     "open_hours_hint": "09:00-17:00，周一闭馆", "ticket_price_hint": "免费",
     "lng": 104.065, "lat": 30.672},
    {"poi_id": "B0FFH8", "name": "人民公园", "type": "景点",
     "open_hours_hint": "全天开放", "ticket_price_hint": "免费",
     "lng": 104.051, "lat": 30.654},
    {"poi_id": "B0FFJ3", "name": "小名堂担担甜水面", "type": "餐厅",
     "open_hours_hint": "10:00-22:00", "ticket_price_hint": None,
     "lng": 104.048, "lat": 30.665},
    {"poi_id": "B0FFJ7", "name": "陈麻婆豆腐（总店）", "type": "餐厅",
     "open_hours_hint": "10:00-21:30", "ticket_price_hint": None,
     "lng": 104.042, "lat": 30.660},
    {"poi_id": "B0FFK1", "name": "熊猫基地", "type": "景点",
     "open_hours_hint": "08:00-17:00", "ticket_price_hint": "55元",
     "lng": 104.140, "lat": 30.742}
]

user_msg = f"""当前日期：2026-10-17

【出行约束 constraints】
{json.dumps(constraints, ensure_ascii=False, indent=2)}

【高德 API 预查的真实 POI 候选列表（type=poi 的活动只能从这里挑）】
{json.dumps(poi_candidates, ensure_ascii=False, indent=2)}

请生成完整行程 JSON。"""

# ── 4. 调 DeepSeek API ──────────────────────────────────────────────
url = "https://api.deepseek.com/v1/chat/completions"
payload = json.dumps({
    "model": "deepseek-chat",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg}
    ],
    "temperature": 0.7,
    "max_tokens": 3500,
    "response_format": {"type": "json_object"}
}).encode("utf-8")

req = urllib.request.Request(url, data=payload, headers={
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "itinerary-smoke-test/0.1"
})

print("\n────────── 调用 DeepSeek API ──────────")
t0 = time.time()
try:
    resp = urllib.request.urlopen(req, timeout=120)
    body = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    err_body = e.read().decode("utf-8", errors="replace")
    print(f"[FAIL] API HTTP {e.code}: {err_body}")
    sys.exit(1)
except Exception as e:
    print(f"[FAIL] API 调用异常: {e}")
    sys.exit(1)

latency_ms = int((time.time() - t0) * 1000)
raw_content = body["choices"][0]["message"]["content"]
usage = body.get("usage", {})
print(f"[OK] API 返回，耗时 {latency_ms}ms，token: {usage}")
print(f"[RAW] LLM 输出前 300 chars: {raw_content[:300]}...")

# ── 5. L0 清洗 ──────────────────────────────────────────────────────
def l0_clean(text: str) -> str:
    # 剥 markdown 代码块围栏
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"```\s*$", "", text)
    # 去尾部注释（LLM 偶尔会在 JSON 末尾写 // ...）
    text = re.sub(r"//[^\n]*$", "", text, flags=re.MULTILINE)
    return text.strip()

cleaned = l0_clean(raw_content)
print(f"\n[L0] 清洗后前 200 chars: {cleaned[:200]}...")

try:
    parsed = json.loads(cleaned)
except json.JSONDecodeError as e:
    print(f"[L0 FAIL] JSON 解析失败: {e}")
    print(f"[DEBUG] 清洗后文本末 200 chars: ...{cleaned[-200:]}")
    sys.exit(1)
print("[L0 OK] JSON 解析成功")

# ── 6. L1 Schema 校验 ──────────────────────────────────────────────
l1_errors = sorted(validator.iter_errors(parsed), key=lambda e: list(e.path))
if l1_errors:
    print(f"\n[L1 FAIL] 发现 {len(l1_errors)} 个 Schema 错误：")
    for err in l1_errors:
        print(f"  - path={list(err.path)} msg={err.message}")
else:
    print("[L1 OK] Schema 校验通过 ✅")

# ── 7. L2 业务校验 ──────────────────────────────────────────────────
l2_errors = []

# 天数覆盖
days = parsed.get("days", [])
expected_dates = []
d = constraints["date_start"]
while d <= constraints["date_end"]:
    expected_dates.append(d)
    # 简单 +1 天（不处理跨月跨年边界，测试输入固定 3 天所以安全）
    from datetime import date, timedelta
    y, m, day = map(int, d.split("-"))
    d = (date(y, m, day) + timedelta(days=1)).isoformat()
actual_dates = [day["date"] for day in days]
if actual_dates != expected_dates:
    l2_errors.append(f"天数覆盖错误：期望 {expected_dates}，实际 {actual_dates}")

# 时间有序 & 不重叠
for day in days:
    acts = day.get("activities", [])
    prev_end = None
    prev_start = None
    ids_in_day = set()
    for act in acts:
        aid = act.get("activity_id")
        if aid in ids_in_day:
            l2_errors.append(f"Day {day['day_index']}: activity_id '{aid}' 重复")
        ids_in_day.add(aid)

        ts = act.get("time_slot", {})
        start = ts.get("start", "")
        end = ts.get("end", "")
        if start >= end:
            l2_errors.append(f"Day {day['day_index']} {aid}: time_slot.end {end} 必须晚于 start {start}")
        if prev_end and start <= prev_end:
            l2_errors.append(f"Day {day['day_index']}: {prev_start}-{prev_end} 与 {start}-{end} 重叠或倒序")
        prev_start, prev_end = start, end

# 预算
try:
    total = parsed.get("cost_summary", {}).get("total_estimate", {}).get("amount", 0)
    if total > constraints["budget_total"]["amount"]:
        l2_errors.append(f"总估算 {total} > 预算 {constraints['budget_total']['amount']}")
except Exception:
    l2_errors.append("无法计算总估算金额")

# poi 类型只从候选挑
poi_names = {p["name"] for p in poi_candidates}
for day in days:
    for act in day.get("activities", []):
        if act.get("type") == "poi":
            title = act.get("title", "")
            if title not in poi_names:
                l2_errors.append(f"POI 活动 '{title}' 不在候选列表中")

# price_type 必须是 estimate
for day in days:
    for act in day.get("activities", []):
        cost = act.get("cost", {})
        if cost.get("price_type") != "estimate":
            l2_errors.append(f"{act.get('activity_id')}: price_type={cost.get('price_type')}, 必须是 estimate")

if l2_errors:
    print(f"\n[L2 FAIL] 发现 {len(l2_errors)} 个业务规则错误：")
    for err in l2_errors:
        print(f"  - {err}")
else:
    print("[L2 OK] 业务规则校验通过 ✅")

# ── 8. 总结 ─────────────────────────────────────────────────────────
all_ok = not l1_errors and not l2_errors
print("\n" + "=" * 50)
print(f"结果: {'✅ 全部通过' if all_ok else '❌ 存在失败'}")
print(f"耗时: {latency_ms}ms")
print(f"Token 用量: prompt={usage.get('prompt_tokens','?')}, completion={usage.get('completion_tokens','?')}")
print(f"L1 Schema: {'PASS' if not l1_errors else f'FAIL ({len(l1_errors)} errors)'}")
print(f"L2 业务:   {'PASS' if not l2_errors else f'FAIL ({len(l2_errors)} errors)'}")
print("=" * 50)

if not all_ok:
    sys.exit(1)

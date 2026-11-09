"""
Week 4 技术1 回归脚本（联调边界 case）
========================================
覆盖三块，全部不依赖外部服务与 API Key：

1. Prompt lint：v0.3 三个 Prompt 能被后端同款正则提取，且关键边界规则齐全
2. 业务校验：activity_id 稳定性 / diff 越界 在边界场景下的行为
3. 规则校验：极端预算、0 预算、时间重叠、POI 来源（复用后端 trip_validation，纯标准库）

用法：
    python smoke_test_v04.py
    python smoke_test_v04.py --prompt      # 只跑 Prompt lint
    python smoke_test_v04.py --validator   # 只跑业务校验
    python smoke_test_v04.py --rules       # 只跑规则校验
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "docs", "schemas", "validators"))

from activity_id_validator import validate_activity_id_stability  # noqa: E402
from diff_scope_validator import validate_diff_scope  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  OK   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")
        if detail:
            print(f"       {detail}")


def codes(errors: list[dict]) -> list[str]:
    return [e["code"] for e in errors]


# ═══════════════════════════════════════════════════════════════════
# 1. Prompt lint
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_RE = re.compile(
    r"##\s+\d+\.\s+System Prompt.*?```(?:text)?\s*\n(.*?)```", re.DOTALL
)

PROMPT_SPECS = [
    (
        "docs/prompts/行程生成Prompt-v0.3.md",
        ["B0 输入兼容", "边界模式", "B1 极端预算", "B2a 候选为空数组",
         "B2b 候选未提供", "B3 预算为 0", "B4 多人偏好冲突",
         "格式自查清单", "只输出纯 JSON"],
        ["cost_summary", "days", "activity_id"],
    ),
    (
        "docs/prompts/行中重排Prompt-v0.3.md",
        ["R0 输入兼容", "R1 全天降雨", "R2a 候选为空数组", "R2b 候选未提供",
         "R3 跨天连续降雨", "R4 候选活动在生成后被队友替换",
         "空 diff 合法", "只输出纯 JSON"],
        ["proposed_itinerary", "diff"],
    ),
    (
        "docs/prompts/修订Prompt-v0.3.md",
        ["V1 极端预算下调", "V2 预算上调", "V3 多人同时编辑",
         "V4 预算约束与单条活动冲突", "空 diff 合法", "只输出纯 JSON"],
        ["proposed_itinerary", "diff"],
    ),
]


def test_prompts() -> None:
    print("\n[1] Prompt lint（后端同款正则提取 + 关键规则齐全）")
    for rel_path, required, skeleton_tokens in PROMPT_SPECS:
        path = os.path.join(HERE, rel_path)
        if not os.path.exists(path):
            check(f"{rel_path} 存在", False)
            continue
        text = open(path, encoding="utf-8").read()
        match = SYSTEM_PROMPT_RE.search(text)
        if not match:
            check(f"{os.path.basename(rel_path)} System Prompt 可提取", False,
                  "后端 loader.py 将无法加载该文件")
            continue
        system_prompt = match.group(1)
        check(f"{os.path.basename(rel_path)} System Prompt 可提取",
              len(system_prompt) > 1500, f"长度 {len(system_prompt)}")
        missing = [rule for rule in required if rule not in system_prompt]
        check(f"{os.path.basename(rel_path)} 边界规则齐全", not missing,
              f"缺少: {missing}")
        # 输出骨架必须包含该接口的必备顶层字段
        missing_keys = [k for k in skeleton_tokens if k not in system_prompt]
        check(f"{os.path.basename(rel_path)} 输出骨架字段齐全", not missing_keys,
              f"缺少: {missing_keys}")


# ═══════════════════════════════════════════════════════════════════
# 2. 业务校验边界
# ═══════════════════════════════════════════════════════════════════

def _act(aid: str, start: str, end: str, **extra) -> dict:
    item = {
        "activity_id": aid,
        "type": "poi",
        "title": f"活动{aid}",
        "time_slot": {"start": start, "end": end},
        "status": "planned",
    }
    item.update(extra)
    return item


def _base_itinerary() -> dict:
    return {
        "days": [
            {"day_index": 1, "activities": [
                _act("act-1", "09:00", "12:00"),
                _act("act-2", "14:00", "16:00"),
            ]},
            {"day_index": 2, "activities": [
                _act("act-3", "09:00", "12:00"),
                _act("act-4", "14:00", "16:30"),
                _act("act-5", "17:00", "19:00"),
            ]},
            {"day_index": 3, "activities": [
                _act("act-6", "09:00", "11:00"),
            ]},
        ]
    }


def test_validators() -> None:
    print("\n[2] 业务校验边界（activity_id 稳定性 / diff 越界）")
    base = _base_itinerary()

    # ── 全天降雨：scope=2, after_time=00:00，Day2 全替换，其他天不动 ──
    rainy = json.loads(json.dumps(base))
    day2 = rainy["days"][1]["activities"]
    for item in day2:
        item["status"] = "replaced"
        item["replaced_reason"] = "全天降雨"
    day2.append(_act("act-7", "14:00", "16:00", status="planned"))  # 室内替代
    day2.sort(key=lambda x: x["time_slot"]["start"])
    errs = validate_activity_id_stability(base, rainy, scope_day_index=2, after_time="00:00")
    check("R1 全天降雨只改 Day2 → 通过", codes(errs) == [], str(codes(errs)))

    # ── 全天降雨越界：顺手改了 Day3 ──
    rainy_bad = json.loads(json.dumps(rainy))
    rainy_bad["days"][2]["activities"].append(_act("act-8", "14:00", "16:00"))
    errs = validate_activity_id_stability(base, rainy_bad, scope_day_index=2, after_time="00:00")
    check("R1 全天降雨误改 Day3 → NON_SCOPE_DAY_MODIFIED",
          codes(errs) == ["NON_SCOPE_DAY_MODIFIED"], str(codes(errs)))

    # ── 空 diff 合法 ──
    check("R5/空 diff → 通过", validate_diff_scope({"ops": []}) == [])

    # ── 候选不足：free_time 补位不影响稳定性校验 ──
    shortage = json.loads(json.dumps(base))
    sday2 = shortage["days"][1]["activities"]
    for item in sday2:
        if item["activity_id"] in {"act-4", "act-5"}:
            item["status"] = "replaced"
            item["replaced_reason"] = "室内候选不足"
    shortage["days"][1]["activities"].append(_act("act-7", "14:00", "15:00", type="free_time"))
    errs = validate_activity_id_stability(base, shortage, scope_day_index=2, after_time="12:00")
    check("R2 候选不足用 free_time 补位 → 通过", codes(errs) == [], str(codes(errs)))

    # ── 多人同时编辑：A 改 Day1 cost，B 改 Day2 时间，顺序合并 ──
    a_rev = json.loads(json.dumps(base))
    a_rev["days"][0]["activities"][0]["cost"] = {"amount": 100}
    b_rev = json.loads(json.dumps(base))
    b_rev["days"][1]["activities"][1]["time_slot"] = {"start": "13:30", "end": "16:00"}
    merged = json.loads(json.dumps(base))
    merged["days"][0]["activities"][0]["cost"] = {"amount": 100}
    merged["days"][1]["activities"][1]["time_slot"] = {"start": "13:30", "end": "16:00"}
    ok_a = codes(validate_activity_id_stability(a_rev, merged)) == []
    ok_b = codes(validate_activity_id_stability(b_rev, merged)) == []
    check("多人编辑不同天 → 合并后双方均通过", ok_a and ok_b)

    # ── 多人同时编辑：同一条活动不同字段 ──
    m1 = json.loads(json.dumps(base))
    m1["days"][0]["activities"][0]["cost"] = {"amount": 100}
    m2 = json.loads(json.dumps(m1))
    m2["days"][0]["activities"][0]["time_slot"] = {"start": "09:30", "end": "12:30"}
    check("多人编辑同活动不同字段 → activity_id 稳定",
          codes(validate_activity_id_stability(m1, m2)) == [])

    # ── 多人同时编辑：一方删除活动 → 必须被检测 ──
    deleted = json.loads(json.dumps(base))
    deleted["days"][0]["activities"] = [
        x for x in deleted["days"][0]["activities"] if x["activity_id"] != "act-2"
    ]
    errs = validate_activity_id_stability(base, deleted)
    check("多人编辑中单方删除活动 → ID_MISSING", codes(errs) == ["ID_MISSING"], str(codes(errs)))

    # ── diff 越界：replan_day scope=2 但 op 指向 Day1 ──
    errs = validate_diff_scope(
        {"ops": [{"op": "replace", "activity_id": "act-1", "fields": ["poi"], "day_index": 1}]},
        scope_day_index=2,
    )
    check("diff 越界指向其他天 → OP_OUTSIDE_SCOPE_DAY",
          codes(errs) == ["OP_OUTSIDE_SCOPE_DAY"], str(codes(errs)))


# ═══════════════════════════════════════════════════════════════════
# 3. 规则校验（复用后端 trip_validation，纯标准库）
# ═══════════════════════════════════════════════════════════════════

def _load_trip_validation():
    path = os.path.join(HERE, "backend", "app", "services", "trip_validation.py")
    spec = importlib.util.spec_from_file_location("trip_validation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_trip_rules


def _itinerary(budget: float, costs: list[tuple[str, str, str, float]]) -> dict:
    """构造单日行程：costs = [(activity_id, start, end, amount)]"""
    activities = []
    for aid, start, end, amount in costs:
        activities.append({
            "activity_id": aid,
            "type": "poi",
            "title": f"活动{aid}",
            "time_slot": {"start": start, "end": end},
            "location": {"name": f"地点{aid}", "poi_id": None, "poi_source": None},
            "cost": {"amount": amount, "currency": "CNY", "price_type": "estimate",
                     "source": "llm", "note": None},
            "status": "planned",
        })
    return {
        "meta": {"budget_total": {"amount": budget, "currency": "CNY",
                                  "price_type": "estimate", "source": "llm"}},
        "days": [{"day_index": 1, "activities": activities}],
    }


def test_rules() -> None:
    print("\n[3] 规则校验边界（极端预算 / 0 预算 / 时间重叠 / POI 来源）")
    validate_trip_rules = _load_trip_validation()

    # 极端预算：预算 600，估算 1000
    result = validate_trip_rules(_itinerary(600, [
        ("act-1", "09:00", "12:00", 500),
        ("act-2", "14:00", "16:00", 500),
    ]))
    check("V1 极端预算超支 → BUDGET_EXCEEDED",
          "BUDGET_EXCEEDED" in codes(result["errors"]), str(codes(result["errors"])))

    # 预算刚好覆盖
    result = validate_trip_rules(_itinerary(1000, [
        ("act-1", "09:00", "12:00", 500),
        ("act-2", "14:00", "16:00", 500),
    ]))
    check("V1 预算刚好覆盖 → 无预算错误",
          "BUDGET_EXCEEDED" not in codes(result["errors"]), str(codes(result["errors"])))

    # 0 预算 = 未设置，不做上限约束
    result = validate_trip_rules(_itinerary(0, [
        ("act-1", "09:00", "12:00", 1000),
    ]))
    check("V3 预算为 0（未设置）→ 不触发预算错误",
          "BUDGET_EXCEEDED" not in codes(result["errors"]), str(codes(result["errors"])))

    # 时间重叠
    result = validate_trip_rules(_itinerary(5000, [
        ("act-1", "09:00", "12:00", 0),
        ("act-2", "11:30", "13:00", 0),
    ]))
    check("时间重叠 → TIME_OVERLAP",
          "TIME_OVERLAP" in codes(result["errors"]), str(codes(result["errors"])))

    # LLM 不得直出可用 POI ID
    itinerary = _itinerary(5000, [("act-1", "09:00", "12:00", 0)])
    itinerary["days"][0]["activities"][0]["location"] = {
        "name": "某景点", "poi_id": "B0FFG9", "poi_source": "llm",
    }
    result = validate_trip_rules(itinerary)
    check("LLM 编造 poi_id → UNTRUSTED_POI_ID",
          "UNTRUSTED_POI_ID" in codes(result["errors"]), str(codes(result["errors"])))

    # quoted 报价缺时间戳
    itinerary = _itinerary(5000, [("act-1", "09:00", "12:00", 100)])
    itinerary["days"][0]["activities"][0]["cost"].update({"price_type": "quoted"})
    result = validate_trip_rules(itinerary)
    check("quoted 缺 fetched_at → QUOTED_PRICE_MISSING_TIMESTAMP",
          "QUOTED_PRICE_MISSING_TIMESTAMP" in codes(result["errors"]),
          str(codes(result["errors"])))


# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    args = set(sys.argv[1:])
    run_all = not args
    print("=" * 64)
    print("Week 4 技术1 回归：联调边界 case")
    print("=" * 64)
    if run_all or "--prompt" in args:
        test_prompts()
    if run_all or "--validator" in args:
        test_validators()
    if run_all or "--rules" in args:
        test_rules()
    print("\n" + "=" * 64)
    print(f"总计: {PASS} passed, {FAIL} failed")
    print("=" * 64)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()

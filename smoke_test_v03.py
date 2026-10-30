"""
Week 3 技术1 烟测脚本（多人协同 + 业务校验）
============================================
验证：
1. activity_id_validator 独立运行 + 边界 case
2. diff_scope_validator 独立运行 + 边界 case
3. revise_itinerary 的 activity_id 稳定性
4. replan_day 的越界检测 + after_time 边界
5. 多人协同冲突场景模拟（A 改 Day1, B 改 Day2, 乐观锁自动重试应成功）

依赖：标准库 json, sys, os
用法：python smoke_test_v03.py
      python smoke_test_v03.py --validator          # 只跑 validator 测试
      python smoke_test_v03.py --multi-user         # 只跑多人协同模拟
"""

from __future__ import annotations

import json
import os
import sys

# 把 validators 加入路径
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "docs", "schemas", "validators"))

from activity_id_validator import validate_activity_id_stability  # noqa: E402
from diff_scope_validator import validate_diff_scope  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, errors: list[dict], expected_codes: list[str]) -> None:
    global PASS, FAIL
    actual_codes = [e["code"] for e in errors]
    if actual_codes == expected_codes:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")
        print(f"     期望 codes: {expected_codes}")
        print(f"     实际 codes: {actual_codes}")


# ═══════════════════════════════════════════════════════════════════
# Part 1: activity_id_validator 边界 case
# ═══════════════════════════════════════════════════════════════════

def test_activity_id_validator() -> None:
    print("\n📋 Part 1: activity_id_validator 边界 case")

    # 原始 3 天行程
    base = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "title": "熊猫基地", "time_slot": {"start": "09:00", "end": "12:00"}, "status": "planned"},
            {"activity_id": "act-2", "title": "宽窄巷子", "time_slot": {"start": "14:00", "end": "16:00"}, "status": "planned"},
            {"activity_id": "act-3", "title": "火锅晚餐", "time_slot": {"start": "18:00", "end": "20:00"}, "status": "planned"},
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-4", "title": "武侯祠", "time_slot": {"start": "09:00", "end": "11:00"}, "status": "planned"},
            {"activity_id": "act-5", "title": "锦里", "time_slot": {"start": "13:00", "end": "15:30"}, "status": "planned"},
            {"activity_id": "act-6", "title": "川剧", "time_slot": {"start": "19:00", "end": "21:00"}, "status": "planned"},
        ]},
        {"day_index": 3, "activities": [
            {"activity_id": "act-7", "title": "人民公园", "time_slot": {"start": "09:00", "end": "11:00"}, "status": "planned"},
            {"activity_id": "act-8", "title": "返程", "time_slot": {"start": "14:00", "end": "16:00"}, "status": "planned"},
        ]},
    ]}

    # Test 1.1: revise 正常 —— 只改 cost，id 全不变
    revise_ok = json.loads(json.dumps(base))
    revise_ok["days"][0]["activities"][0]["cost"] = {"amount": 200, "price_type": "estimate", "source": "llm"}
    check("revise 正常（只改 cost）",
          validate_activity_id_stability(base, revise_ok), [])

    # Test 1.2: revise 越界 —— 队友删了我的活动
    revise_bad = json.loads(json.dumps(base))
    revise_bad["days"][0]["activities"] = [a for a in revise_bad["days"][0]["activities"] if a["activity_id"] != "act-2"]
    check("revise 队友删了活动 → ID_MISSING",
          validate_activity_id_stability(base, revise_bad), ["ID_MISSING"])

    # Test 1.3: replan_day 正常 —— scope=2 after_time="14:00"，替换锦里（13:00-15:30，after_time 之后的部分可以动）
    # 注意：after_time=14:00，锦里从 13:00 开始，整条活动跨越 after_time，v0.2 规则算可替换
    replan_ok = json.loads(json.dumps(base))
    replan_ok["days"][1]["activities"][1]["status"] = "replaced"
    replan_ok["days"][1]["activities"][1]["replaced_reason"] = "降雨"
    replan_ok["days"][1]["activities"].append({
        "activity_id": "act-9", "title": "博物馆",
        "time_slot": {"start": "13:00", "end": "15:00"}, "status": "planned",
        "cost": {"amount": 0, "price_type": "estimate", "source": "llm"},
    })
    check("replan_day scope=2 after_time=14:00 正常替换锦里",
          validate_activity_id_stability(base, replan_ok, scope_day_index=2, after_time="14:00"), [])

    # Test 1.4: replan_day 越界 —— 删了 after_time 之前的武侯祠（09:00-11:00）
    replan_bad = json.loads(json.dumps(base))
    replan_bad["days"][1]["activities"] = [a for a in replan_bad["days"][1]["activities"] if a["activity_id"] != "act-4"]
    check("replan_day 删除 after_time 之前的活动 → ID_MISSING_IN_SCOPE",
          validate_activity_id_stability(base, replan_bad, scope_day_index=2, after_time="14:00"), ["ID_MISSING_IN_SCOPE"])

    # Test 1.5: replan_day 非 scope 天被改了
    replan_non_scope = json.loads(json.dumps(base))
    replan_non_scope["days"][0]["activities"].append({
        "activity_id": "act-10", "title": "新增",
        "time_slot": {"start": "16:00", "end": "17:00"}, "status": "planned",
    })
    check("replan_day scope=2 但 Day1 被加了活动 → NON_SCOPE_DAY_MODIFIED",
          validate_activity_id_stability(base, replan_non_scope, scope_day_index=2, after_time="14:00"), ["NON_SCOPE_DAY_MODIFIED"])

    # Test 1.6: 新 id 编号不接序（用了 act-3 但已有 act-8 最大）
    replan_new_id_bad = json.loads(json.dumps(base))
    replan_new_id_bad["days"][1]["activities"].append({
        "activity_id": "act-5",  # 冲突！act-5 已存在
        "title": "重复编号",
        "time_slot": {"start": "16:00", "end": "17:00"}, "status": "planned",
    })
    check("replan_day 新 id 编号重复 → DUPLICATE_ID",
          validate_activity_id_stability(base, replan_new_id_bad, scope_day_index=2), ["DUPLICATE_ID"])


# ═══════════════════════════════════════════════════════════════════
# Part 2: diff_scope_validator 边界 case
# ═══════════════════════════════════════════════════════════════════

def test_diff_scope_validator() -> None:
    print("\n📋 Part 2: diff_scope_validator 边界 case")

    # Test 2.1: revise 正常 diff
    diff_ok = {"ops": [
        {"op": "replace", "activity_id": "act-2", "fields": ["cost"], "day_index": 1},
    ]}
    check("revise 正常 diff", validate_diff_scope(diff_ok), [])

    # Test 2.2: replan_day scope 越界
    diff_bad_day = {"ops": [
        {"op": "replace", "activity_id": "act-7", "fields": ["poi"], "day_index": 3},
    ]}
    check("replan_day scope=2 但 op 指向 Day3 → OP_OUTSIDE_SCOPE_DAY",
          validate_diff_scope(diff_bad_day, scope_day_index=2), ["OP_OUTSIDE_SCOPE_DAY"])

    # Test 2.3: replace 缺 fields
    diff_no_fields = {"ops": [
        {"op": "replace", "activity_id": "act-2", "day_index": 1},
    ]}
    check("replace 缺 fields → REPLACE_MISSING_FIELDS",
          validate_diff_scope(diff_no_fields), ["REPLACE_MISSING_FIELDS"])

    # Test 2.4: replace 多 field 应拆分
    diff_multi = {"ops": [
        {"op": "replace", "activity_id": "act-2", "fields": ["cost", "time_slot"], "day_index": 1},
    ]}
    check("replace 多 field → REPLACE_MULTI_FIELD",
          validate_diff_scope(diff_multi), ["REPLACE_MULTI_FIELD"])

    # Test 2.5: remove + add 同 id → 应该用 replace
    diff_ra = {"ops": [
        {"op": "remove", "from_id": "act-2", "day_index": 1},
        {"op": "add", "to_id": "act-2", "day_index": 1},
    ]}
    check("remove + add 同 id → REMOVE_ADD_SAME_ID",
          validate_diff_scope(diff_ra), ["REMOVE_ADD_SAME_ID"])

    # Test 2.6: move 缺 to_id
    diff_move_bad = {"ops": [
        {"op": "move", "from_id": "act-1", "day_index": 1},
    ]}
    check("move 缺 to_id → MOVE_MISSING_IDS",
          validate_diff_scope(diff_move_bad), ["MOVE_MISSING_IDS"])


# ═══════════════════════════════════════════════════════════════════
# Part 3: 多人协同冲突模拟（乐观锁 + 自动重试）
# ═══════════════════════════════════════════════════════════════════

def test_multi_user_conflict() -> None:
    print("\n📋 Part 3: 多人协同冲突模拟")

    base = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "12:00"}},
            {"activity_id": "act-2", "time_slot": {"start": "14:00", "end": "16:00"}},
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-3", "time_slot": {"start": "09:00", "end": "11:00"}},
            {"activity_id": "act-4", "time_slot": {"start": "13:00", "end": "15:00"}},
        ]},
    ]}

    # ── 场景 1: A 改 Day1, B 改 Day2 → 乐观锁重试应成功（改不同天无冲突） ──
    a_revision = json.loads(json.dumps(base))
    a_revision["days"][0]["activities"][0]["time_slot"] = {"start": "09:30", "end": "12:30"}

    b_revision = json.loads(json.dumps(base))
    b_revision["days"][1]["activities"][1]["time_slot"] = {"start": "13:30", "end": "15:30"}

    # A 先提交 → version 从 1 到 2
    # B 基于旧 version=1 提交 → 乐观锁失败 → 自动重试（用 version=2 重新生成 revise）
    # 因为改的是不同天，重校验 activity_id 稳定性应该通过
    retry_errors = validate_activity_id_stability(a_revision, b_revision)
    check("场景1：A改Day1 B改Day2 → 乐观锁重试后 activity_id 校验应通过",
          retry_errors, [])

    # ── 场景 2: A 和 B 同时改 Day1 同一条 → 自动重试仍失败 → 返回 409 冲突 ──
    a_revision2 = json.loads(json.dumps(base))
    a_revision2["days"][0]["activities"][0]["cost"] = {"amount": 100, "price_type": "estimate", "source": "llm"}

    b_revision2 = json.loads(json.dumps(a_revision2))  # 用 A 提交后的版本
    # B 基于 A 提交后的版本改同一条 activity_id
    b_revision2["days"][0]["activities"][0]["status"] = "replaced"

    # 这次 A 和 B 改的是同一条，activity_id 没变（只是改了不同 field）
    # 自动重试应该能通过（因为 activity_id 没变）
    retry_errors2 = validate_activity_id_stability(a_revision2, b_revision2)
    check("场景2：A和B改同一条 activity_id（不同 field）→ 校验通过",
          retry_errors2, [])

    # ── 场景 3: A 删了 act-2，B 也删了 act-2 → 两人都删，activity_id 消失 → 校验失败 ──
    a_del = json.loads(json.dumps(base))
    a_del["days"][0]["activities"] = [x for x in a_del["days"][0]["activities"] if x["activity_id"] != "act-2"]

    b_del = json.loads(json.dumps(a_del))  # B 基于 A 删除后的版本
    # B 也删 act-2（已经没了，所以 B 看到的和 A 一样）
    # 但如果 B 基于原始 base 也删 act-2，那 activity_id_validator 会报错
    b_del_base = json.loads(json.dumps(base))
    b_del_base["days"][0]["activities"] = [x for x in b_del_base["days"][0]["activities"] if x["activity_id"] != "act-2"]

    # A 删了 act-2，B 基于 base 也删 act-2 → 两人都没删其他的，activity_id 稳定性校验应该通过
    # （因为 A 和 B 的 proposed 中 act-2 都没了，validator 比较的是 A 的 proposed vs B 的 proposed...
    #  不对，retry 场景是 B 拿旧 base_version 的快照重调 Agent，所以应该比较 old(base) vs new(B 的 proposed)）
    # 这个测试实际上不适合 activity_id_validator，应该留到端到端
    print("  ℹ️  场景3 留端到端联调测（需要实际 API 交互）")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    global PASS, FAIL

    args = set(sys.argv[1:])
    run_all = not args

    print("=" * 60)
    print("Week 3 技术1 烟测脚本（多人协同 + 业务校验）")
    print("=" * 60)

    if run_all or "--validator" in args:
        test_activity_id_validator()
        test_diff_scope_validator()

    if run_all or "--multi-user" in args:
        test_multi_user_conflict()

    print("\n" + "=" * 60)
    print(f"总计: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()

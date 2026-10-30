"""
activity_id 稳定性校验模块
==========================
多人协同的地基：任何人/AI 的编辑都不允许变更未动条目的 activity_id。

用法 1（独立运行，给技术1 本地测）：
    python activity_id_validator.py --old old_itinerary.json --new proposed.json
    python activity_id_validator.py --old old.json --new new.json --scope-day 2

用法 2（被技术2 的后端 import）：
    from schemas.validators.activity_id_validator import validate_activity_id_stability
    errors = validate_activity_id_stability(old_data, new_data, scope_day_index=2)

设计原则：
- 只依赖标准库（json, sys, re），不依赖 jsonschema
- 返回 error list（空 list = 通过），每个 error 是 dict，技术2 可直接塞进 AppError.detail
- scope_day_index=None → 全行程检查（generate/revise 场景）
- scope_day_index=N → 只检查 Day N，其他天不做 activity_id 检查（replan_day 场景）
- replan_day 场景下，非 scope 天只需保证 new 和 old 的 activity_id 集合一致即可
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any


def validate_activity_id_stability(
    old_itinerary: dict[str, Any],
    proposed_itinerary: dict[str, Any],
    *,
    scope_day_index: int | None = None,
    after_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    校验 proposed_itinerary 相对于 old_itinerary 是否违反 activity_id 稳定性。

    参数:
        old_itinerary: 原始行程（dict，符合 itinerary.schema.json v1.0）
        proposed_itinerary: Agent 产出的修改后行程
        scope_day_index: 限制检查范围（replan_day 场景）。None=全行程；整数=只检查 Day N
        after_time: replan_day 场景的时间下限（HH:MM）。None=不做时间过滤

    返回:
        error list。每个 error = {
            "code": str,           # DUPLICATE_ID / ID_MISSING / ID_REAPPEARED / NEW_ID_NOT_SEQUENTIAL / ID_OUTSIDE_SCOPE
            "message": str,
            "detail": dict
        }
    """
    errors: list[dict[str, Any]] = []

    old_days = old_itinerary.get("days", [])
    new_days = proposed_itinerary.get("days", [])

    # ── 1. 先检查非 scope 天（replan_day 场景）是否原样保留 ──
    if scope_day_index is not None:
        errors.extend(_check_non_scope_days(old_days, new_days, scope_day_index))

    # ── 2. 收集 scope 范围内的 old activity ──
    old_scope_activities: dict[str, dict[str, Any]] = {}
    for day in old_days:
        di = day.get("day_index")
        if scope_day_index is not None and di != scope_day_index:
            continue
        for act in day.get("activities", []):
            aid = act.get("activity_id")
            if aid:
                old_scope_activities[aid] = {
                    "day_index": di,
                    "start": act.get("time_slot", {}).get("start"),
                    "status": act.get("status", "planned"),
                }

    # ── 3. 检查 proposed scope 内 activity_id 是否重复 ──
    new_scope_ids: set[str] = set()
    for day in new_days:
        di = day.get("day_index")
        if scope_day_index is not None and di != scope_day_index:
            continue
        for act in day.get("activities", []):
            aid = act.get("activity_id")
            if not aid:
                errors.append({
                    "code": "MISSING_ACTIVITY_ID",
                    "message": f"Day{di} 某活动缺少 activity_id",
                    "detail": {"day_index": di, "activity": act.get("title")},
                })
                continue
            if aid in new_scope_ids:
                errors.append({
                    "code": "DUPLICATE_ID",
                    "message": f"activity_id '{aid}' 在 proposed scope 中重复出现",
                    "detail": {"activity_id": aid, "day_index": di},
                })
            new_scope_ids.add(aid)

    # ── 4. old scope 内 id 在 new scope 中消失 ──
    for old_aid, old_info in old_scope_activities.items():
        if old_aid in new_scope_ids:
            continue  # 还在 scope 里，ok

        # replan_day + after_time 场景：after_time 之前的活动不能消失
        if (
            scope_day_index is not None
            and after_time is not None
            and old_info.get("start")
            and _time_less_eq(old_info["start"], after_time)
        ):
            errors.append({
                "code": "ID_MISSING_IN_SCOPE",
                "message": (
                    f"旧 activity_id '{old_aid}'（Day{old_info['day_index']} {old_info['start']}）"
                    f"在 proposed scope 中消失，且早于 after_time={after_time}，"
                    f"越出 replan_day 可修改范围"
                ),
                "detail": {
                    "activity_id": old_aid,
                    "day_index": old_info["day_index"],
                    "start": old_info["start"],
                    "after_time": after_time,
                },
            })
        elif scope_day_index is None:
            # revise_itinerary 场景：任何 old id 消失都算违规
            errors.append({
                "code": "ID_MISSING",
                "message": (
                    f"旧 activity_id '{old_aid}'（Day{old_info['day_index']}）"
                    f"在 proposed 中消失，未标记 replaced/removed"
                ),
                "detail": {
                    "activity_id": old_aid,
                    "day_index": old_info["day_index"],
                    "old_status": old_info["status"],
                },
            })

    # ── 5. new scope 内 id 不在 old scope 里（新增 id） ──
    # 检查编号是否接在 old 最大编号之后
    old_nums = _extract_activity_numbers(old_scope_activities.keys())
    new_nums = _extract_activity_numbers(new_scope_ids - set(old_scope_activities.keys()))
    if old_nums and new_nums:
        max_old = max(old_nums)
        for num in sorted(new_nums):
            if num <= max_old:
                errors.append({
                    "code": "NEW_ID_NOT_SEQUENTIAL",
                    "message": (
                        f"新 activity_id 编号 act-{num} 小于等于旧最大值 act-{max_old}，"
                        f"应接在 act-{max_old + 1} 之后"
                    ),
                    "detail": {"new_number": num, "max_old": max_old},
                })

    return errors


def _check_non_scope_days(
    old_days: list[dict], new_days: list[dict], scope_day_index: int
) -> list[dict[str, Any]]:
    """
    replan_day 场景：检查 scope 之外的天是否原样保留。
    规则：Day_index != scope_day_index 的天，activity_id 集合必须完全一致。
    """
    errors: list[dict[str, Any]] = []

    old_non_scope_ids: dict[int, set[str]] = {}
    new_non_scope_ids: dict[int, set[str]] = {}

    for day in old_days:
        di = day.get("day_index")
        if di != scope_day_index:
            old_non_scope_ids[di] = {
                act.get("activity_id", "") for act in day.get("activities", []) if act.get("activity_id")
            }

    for day in new_days:
        di = day.get("day_index")
        if di != scope_day_index:
            new_non_scope_ids[di] = {
                act.get("activity_id", "") for act in day.get("activities", []) if act.get("activity_id")
            }

    for di, old_ids in old_non_scope_ids.items():
        new_ids = new_non_scope_ids.get(di, set())
        if old_ids != new_ids:
            missing = old_ids - new_ids
            added = new_ids - old_ids
            errors.append({
                "code": "NON_SCOPE_DAY_MODIFIED",
                "message": (
                    f"Day{di}（replan_day scope={scope_day_index} 之外）activity_id 集合变更，"
                    f"旧集合={sorted(old_ids)}，新集合={sorted(new_ids)}"
                ),
                "detail": {
                    "day_index": di,
                    "scope_day_index": scope_day_index,
                    "removed": sorted(missing),
                    "added": sorted(added),
                },
            })

    return errors


def _extract_activity_numbers(ids: set[str]) -> set[int]:
    """从 activity_id 集合里提取数字编号。"""
    nums: set[int] = set()
    pattern = re.compile(r"^act-(\d+)$")
    for aid in ids:
        m = pattern.match(aid)
        if m:
            nums.add(int(m.group(1)))
    return nums


def _time_less_eq(t1: str, t2: str) -> bool:
    """比较 HH:MM 字符串，t1 ≤ t2。"""
    try:
        h1, m1 = map(int, t1.split(":"))
        h2, m2 = map(int, t2.split(":"))
        return (h1 * 60 + m1) <= (h2 * 60 + m2)
    except (ValueError, AttributeError):
        return False


def main() -> None:
    """独立运行入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="activity_id 稳定性校验")
    parser.add_argument("--old", required=True, help="原始 itinerary JSON 路径")
    parser.add_argument("--new", required=True, help="proposed itinerary JSON 路径")
    parser.add_argument("--scope-day", type=int, default=None, help="replan_day 场景：限制检查某一天")
    parser.add_argument("--after-time", default=None, help="replan_day 场景：HH:MM 时间下限")
    args = parser.parse_args()

    with open(args.old, encoding="utf-8") as f:
        old_data = json.load(f)
    with open(args.new, encoding="utf-8") as f:
        new_data = json.load(f)

    errors = validate_activity_id_stability(
        old_data, new_data,
        scope_day_index=args.scope_day,
        after_time=args.after_time,
    )

    if errors:
        print(f"[FAIL] activity_id 稳定性校验失败，{len(errors)} 个错误：")
        for e in errors:
            print(f"  [{e['code']}] {e['message']}")
        sys.exit(1)
    else:
        print("[OK] activity_id 稳定性校验通过 ✅")


# ── 单元测试 ──

def _run_tests() -> None:
    print("运行 activity_id_validator 单元测试...")
    passed = 0
    failed = 0

    def check(name: str, errors: list[dict], expected_codes: list[str]) -> None:
        nonlocal passed, failed
        actual_codes = [e["code"] for e in errors]
        if actual_codes == expected_codes:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}")
            print(f"     期望 codes: {expected_codes}")
            print(f"     实际 codes: {actual_codes}")

    # Test 1: 正常 revise，activity_id 不变
    old = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
        {"activity_id": "act-2", "time_slot": {"start": "12:00", "end": "14:00"}},
    ]}]}
    new = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:30", "end": "11:30"}},
        {"activity_id": "act-2", "time_slot": {"start": "12:00", "end": "14:00"}},
    ]}]}
    check("正常 revise（ID 不变，只改时间）", validate_activity_id_stability(old, new), [])

    # Test 2: 旧 id 消失未替换
    new_bad = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
    ]}]}
    check("旧 id 消失（revising 场景应报错）", validate_activity_id_stability(old, new_bad), ["ID_MISSING"])

    # Test 3: 新 id 重复
    new_dup = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
        {"activity_id": "act-1", "time_slot": {"start": "12:00", "end": "14:00"}},
    ]}]}
    check("新 id 重复", validate_activity_id_stability(old, new_dup), ["DUPLICATE_ID", "ID_MISSING"])

    # Test 4: replan_day 越界 —— after_time 之前的活动被删
    old_replan = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-2", "time_slot": {"start": "10:00", "end": "12:00"}},
            {"activity_id": "act-3", "time_slot": {"start": "14:00", "end": "16:00"}},
        ]},
        {"day_index": 3, "activities": [
            {"activity_id": "act-4", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
    ]}
    new_replan_bad = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-3", "time_slot": {"start": "14:00", "end": "16:00"}},
        ]},
        {"day_index": 3, "activities": [
            {"activity_id": "act-4", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
    ]}
    check(
        "replan_day 删除 after_time 之前的活动 → 越界",
        validate_activity_id_stability(old_replan, new_replan_bad, scope_day_index=2, after_time="13:00"),
        ["ID_MISSING_IN_SCOPE"],
    )

    # Test 5: replan_day 正常 —— after_time 之后的活动被替换
    new_replan_ok = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-2", "time_slot": {"start": "10:00", "end": "12:00"}, "status": "planned"},
            {"activity_id": "act-3", "time_slot": {"start": "14:00", "end": "16:00"}, "status": "replaced"},
            {"activity_id": "act-5", "time_slot": {"start": "14:00", "end": "16:00"}},
        ]},
        {"day_index": 3, "activities": [
            {"activity_id": "act-4", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
    ]}
    check(
        "replan_day 正常替换 after_time 之后的活动 → 通过",
        validate_activity_id_stability(old_replan, new_replan_ok, scope_day_index=2, after_time="13:00"),
        [],
    )

    # Test 6: replan_day 非 scope 天被改了 → 越界
    new_non_scope_modified = {"days": [
        {"day_index": 1, "activities": [
            {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}},
            {"activity_id": "act-6", "time_slot": {"start": "14:00", "end": "16:00"}},  # Day1 被改了
        ]},
        {"day_index": 2, "activities": [
            {"activity_id": "act-2", "time_slot": {"start": "10:00", "end": "12:00"}},
            {"activity_id": "act-3", "time_slot": {"start": "14:00", "end": "16:00"}},
        ]},
        {"day_index": 3, "activities": [
            {"activity_id": "act-4", "time_slot": {"start": "09:00", "end": "11:00"}},
        ]},
    ]}
    check(
        "replan_day scope=2 但 Day1 被改了 → 越界",
        validate_activity_id_stability(old_replan, new_non_scope_modified, scope_day_index=2, after_time="13:00"),
        ["NON_SCOPE_DAY_MODIFIED"],
    )

    # Test 7: 多人协同 revise → 队友删了我的活动
    old_multi = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}, "owner": "A"},
        {"activity_id": "act-2", "time_slot": {"start": "12:00", "end": "14:00"}, "owner": "B"},
        {"activity_id": "act-3", "time_slot": {"start": "15:00", "end": "17:00"}, "owner": "A"},
    ]}]}
    new_multi_bad = {"days": [{"day_index": 1, "activities": [
        {"activity_id": "act-1", "time_slot": {"start": "09:00", "end": "11:00"}, "owner": "A"},
        {"activity_id": "act-3", "time_slot": {"start": "15:00", "end": "17:00"}, "owner": "A"},
    ]}]}
    check("多人 revise 队友删了 B 的活动 → ID_MISSING", validate_activity_id_stability(old_multi, new_multi_bad), ["ID_MISSING"])

    print(f"\n测试结果: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        main()

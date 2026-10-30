"""
diff.ops 越界校验模块
======================
校验 Agent 返回的 diff.ops 是否超出 replan_day / revise_itinerary 的 scope。

与 activity_id_validator 的区别：
- activity_id_validator 是"事实层面"：直接比较 old vs new itinerary 的 activity_id 集合
- diff_scope_validator 是"契约层面"：校验 Agent 返回的 diff.ops 是否越界

用法：
    python diff_scope_validator.py --diff diff.json --scope-day 2 --after-time 13:00

    from schemas.validators.diff_scope_validator import validate_diff_scope
    errors = validate_diff_scope(diff_obj, scope_day_index=2, after_time="13:00")
"""

from __future__ import annotations

import json
import sys
from typing import Any


def validate_diff_scope(
    diff: dict[str, Any],
    *,
    scope_day_index: int | None = None,
    after_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    校验 diff.ops 是否越出 replan_day / revise_itinerary 的 scope。

    参数:
        diff: Agent 返回的 diff 对象，结构 = {
            "ops": [
                {"op": "add" | "remove" | "replace" | "move",
                 "activity_id": str,     # move 场景是目标 activity_id
                 "from_id": str,          # remove/replace 场景是原 activity_id
                 "to_id": str,            # add/move 场景是目标 activity_id
                 "day_index": int,
                 "fields": [...],         # replace 场景：被替换的字段列表
                 "target_activity_ids": [...],  # replan_day 场景：哪些活动触发了重排
                 "reason": str}
            ]
        }
        scope_day_index: replan_day 场景限制检查范围。None=revise_itinerary（全行程允许）
        after_time: replan_day 场景的时间下限。None=不做时间过滤

    返回:
        error list。每个 error = {
            "code": str,
            "message": str,
            "detail": dict
        }
    """
    errors: list[dict[str, Any]] = []
    ops: list[dict[str, Any]] = diff.get("ops", [])

    if not ops:
        return errors  # 空 diff 不算越界

    for i, op in enumerate(ops):
        op_type = op.get("op", "")
        day_index = op.get("day_index")
        activity_id = op.get("activity_id")
        from_id = op.get("from_id")
        to_id = op.get("to_id")

        # ── 1. scope_day_index 场景：Day 必须匹配 ──
        if scope_day_index is not None:
            if day_index is not None and day_index != scope_day_index:
                errors.append({
                    "code": "OP_OUTSIDE_SCOPE_DAY",
                    "message": (
                        f"diff.op[{i}].{op_type} 的 day_index={day_index}"
                        f" 超出 replan_day scope={scope_day_index}"
                    ),
                    "detail": {"op_index": i, "day_index": day_index, "scope_day_index": scope_day_index},
                })

        # ── 2. after_time 场景：op 涉及的活动必须在时间下限之后 ──
        # 注意：diff 本身不携带活动时间，这里只做结构校验
        # 实际时间校验由 activity_id_validator 负责（它有 old itinerary 数据）
        # 这里只检查 target_activity_ids 是否合理

        # ── 3. replace op 必须有 fields ──
        if op_type == "replace":
            fields = op.get("fields")
            if not fields or not isinstance(fields, list):
                errors.append({
                    "code": "REPLACE_MISSING_FIELDS",
                    "message": f"diff.op[{i}].replace 缺少 fields 列表",
                    "detail": {"op_index": i, "activity_id": activity_id or from_id},
                })
            # 每个 replace 只允许改一个顶层 field
            # 多 field 应该拆成多个 replace op
            if fields and len(fields) > 1:
                errors.append({
                    "code": "REPLACE_MULTI_FIELD",
                    "message": (
                        f"diff.op[{i}].replace 包含 {len(fields)} 个顶层字段 {fields}，"
                        f"应拆成多个 replace op（每个只改一个顶层 field）"
                    ),
                    "detail": {"op_index": i, "fields": fields},
                })

        # ── 4. remove op 不能和 add 同一个 activity_id ──
        # （应该用 replace，而不是 remove + add）
        if op_type == "remove" and from_id:
            for j, other_op in enumerate(ops):
                if i != j and other_op.get("op") == "add" and other_op.get("to_id") == from_id:
                    errors.append({
                        "code": "REMOVE_ADD_SAME_ID",
                        "message": (
                            f"diff.op[{i}].remove(from_id={from_id}) 和 "
                            f"diff.op[{j}].add(to_id={from_id}) 同时出现，"
                            f"应该用 replace op 替代"
                        ),
                        "detail": {"remove_index": i, "add_index": j, "activity_id": from_id},
                    })

        # ── 5. move op 必须同时有 from_id 和 to_id ──
        if op_type == "move":
            if not from_id or not to_id:
                errors.append({
                    "code": "MOVE_MISSING_IDS",
                    "message": (
                        f"diff.op[{i}].move 缺少 from_id 或 to_id"
                        f"（from_id={from_id}, to_id={to_id}）"
                    ),
                    "detail": {"op_index": i, "from_id": from_id, "to_id": to_id},
                })

    return errors


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="diff.ops 越界校验")
    parser.add_argument("--diff", required=True, help="diff JSON 路径")
    parser.add_argument("--scope-day", type=int, default=None, help="replan_day scope day_index")
    parser.add_argument("--after-time", default=None, help="replan_day after_time")
    args = parser.parse_args()

    with open(args.diff, encoding="utf-8") as f:
        diff_data = json.load(f)

    errors = validate_diff_scope(
        diff_data,
        scope_day_index=args.scope_day,
        after_time=args.after_time,
    )

    if errors:
        print(f"[FAIL] diff 越界校验失败，{len(errors)} 个错误：")
        for e in errors:
            print(f"  [{e['code']}] {e['message']}")
        sys.exit(1)
    else:
        print("[OK] diff 越界校验通过 ✅")


def _run_tests() -> None:
    print("运行 diff_scope_validator 单元测试...")
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

    # Test 1: revise 场景正常
    diff_ok = {"ops": [
        {"op": "replace", "activity_id": "act-2", "fields": ["time_slot"], "day_index": 1},
    ]}
    check("revise 正常 diff", validate_diff_scope(diff_ok), [])

    # Test 2: replan_day scope=2 但 op 指向 Day3 → 越界
    diff_outer_day = {"ops": [
        {"op": "replace", "activity_id": "act-5", "fields": ["poi"], "day_index": 3},
    ]}
    check(
        "replan_day scope=2 但 Day3 有 op → 越界",
        validate_diff_scope(diff_outer_day, scope_day_index=2, after_time="13:00"),
        ["OP_OUTSIDE_SCOPE_DAY"],
    )

    # Test 3: replace 缺 fields
    diff_no_fields = {"ops": [
        {"op": "replace", "activity_id": "act-2", "day_index": 1},
    ]}
    check("replace 缺 fields", validate_diff_scope(diff_no_fields), ["REPLACE_MISSING_FIELDS"])

    # Test 4: replace 多 field 应该拆成多个
    diff_multi_field = {"ops": [
        {"op": "replace", "activity_id": "act-2", "fields": ["time_slot", "poi"], "day_index": 1},
    ]}
    check("replace 多 field 应拆分", validate_diff_scope(diff_multi_field), ["REPLACE_MULTI_FIELD"])

    # Test 5: remove + add 同一个 id → 应该用 replace
    diff_remove_add = {"ops": [
        {"op": "remove", "from_id": "act-2", "day_index": 1},
        {"op": "add", "to_id": "act-2", "day_index": 1},
    ]}
    check(
        "remove + add 同 id → 应该用 replace",
        validate_diff_scope(diff_remove_add),
        ["REMOVE_ADD_SAME_ID"],
    )

    # Test 6: move 缺 id
    diff_move_bad = {"ops": [
        {"op": "move", "from_id": "act-1", "day_index": 1},
    ]}
    check("move 缺 to_id", validate_diff_scope(diff_move_bad), ["MOVE_MISSING_IDS"])

    # Test 7: replan_day 正常 diff —— 只改 scope 内的
    diff_replan_ok = {"ops": [
        {"op": "replace", "activity_id": "act-3", "fields": ["poi"], "day_index": 2},
        {"op": "add", "to_id": "act-5", "day_index": 2},
    ]}
    check(
        "replan_day 正常 diff（只改 Day2）",
        validate_diff_scope(diff_replan_ok, scope_day_index=2, after_time="13:00"),
        [],
    )

    print(f"\n测试结果: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        main()

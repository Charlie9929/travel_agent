"""
多人协同业务校验模块（纯 Python，零外部依赖）

技术2 用法：
    # 直接 import 进 backend
    import sys
    sys.path.append("docs/schemas/validators")
    from activity_id_validator import validate_activity_id_stability
    from diff_scope_validator import validate_diff_scope

    errors = validate_activity_id_stability(old, new, scope_day_index=2)
    if errors:
        raise ConflictError(errors)
"""

from .activity_id_validator import validate_activity_id_stability
from .diff_scope_validator import validate_diff_scope

__all__ = [
    "validate_activity_id_stability",
    "validate_diff_scope",
]

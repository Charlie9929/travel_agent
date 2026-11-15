from __future__ import annotations

from copy import deepcopy
from typing import Any

PACE_ALIASES = {
    "relaxed": "relaxed",
    "轻松": "relaxed",
    "休闲": "relaxed",
    "悠闲": "relaxed",
    "宽松": "relaxed",
    "慢节奏": "relaxed",
    "慢游": "relaxed",
    "佛系": "relaxed",
    "normal": "normal",
    "适中": "normal",
    "正常": "normal",
    "标准": "normal",
    "均衡": "normal",
    "intense": "intense",
    "紧凑": "intense",
    "高强度": "intense",
    "特种兵": "intense",
    "充实": "intense",
}


def normalize_pace(value: object) -> str | None:
    """Return the canonical optional pace enum without inventing a preference."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold().replace(" ", "")
    if not normalized:
        return None
    if normalized in PACE_ALIASES:
        return PACE_ALIASES[normalized]
    for alias, canonical in PACE_ALIASES.items():
        if alias not in {"normal", "relaxed", "intense"} and alias in normalized:
            return canonical
    return None


def normalize_constraints(value: object) -> dict[str, Any]:
    """Canonicalize structured constraints while keeping pace genuinely optional."""
    constraints = deepcopy(value) if isinstance(value, dict) else {}
    if "pace" not in constraints:
        return constraints
    pace = normalize_pace(constraints.get("pace"))
    if pace is None:
        constraints.pop("pace", None)
    else:
        constraints["pace"] = pace
    return constraints

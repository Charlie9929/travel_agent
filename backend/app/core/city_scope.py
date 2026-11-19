MUNICIPALITIES: dict[str, tuple[str, str]] = {
    "11": ("北京市", "110000"),
    "12": ("天津市", "120000"),
    "31": ("上海市", "310000"),
    "50": ("重庆市", "500000"),
}

MUNICIPALITY_SCOPE_ALIASES: dict[str, tuple[str, str]] = {
    alias: canonical
    for prefix, canonical in MUNICIPALITIES.items()
    for alias in (
        canonical[0].removesuffix("市"),
        canonical[0],
        f"{canonical[0].removesuffix('市')}城区",
        f"{canonical[0]}城区",
        *(
            (
                "重庆郊县",
                "重庆市郊县",
            )
            if prefix == "50"
            else ()
        ),
    )
}


def canonical_city_selection(name: str, adcode: str) -> tuple[str, str]:
    """Collapse legacy municipality city/area selections to the municipality itself."""
    compact_name = "".join(name.split())
    canonical = MUNICIPALITY_SCOPE_ALIASES.get(compact_name)
    if canonical is not None:
        return canonical
    if len(adcode) == 6 and adcode[:2] in MUNICIPALITIES:
        return MUNICIPALITIES[adcode[:2]]
    return name.strip(), adcode.strip()


def canonical_city_adcode(adcode: str | None) -> str | None:
    if not adcode:
        return adcode
    compact = adcode.strip()
    if len(compact) == 6 and compact[:2] in MUNICIPALITIES:
        return MUNICIPALITIES[compact[:2]][1]
    return compact


def municipality_scope(value: str) -> tuple[str, str] | None:
    compact = "".join(value.split())
    if compact in MUNICIPALITY_SCOPE_ALIASES:
        return MUNICIPALITY_SCOPE_ALIASES[compact]
    if compact.isdigit() and len(compact) == 6:
        return MUNICIPALITIES.get(compact[:2])
    return None


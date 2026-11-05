import pytest

from app.integrations.llm.client import _parse_json_object


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"ok": true}', {"ok": True}),
        ('```json\n{"ok": true}\n```', {"ok": True}),
        ('下面是结果：\n{"ok": true}\n请查收。', {"ok": True}),
    ],
)
def test_parse_json_object_tolerates_provider_wrappers(content: str, expected: dict) -> None:
    assert _parse_json_object(content) == expected


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        _parse_json_object("[1, 2, 3]")

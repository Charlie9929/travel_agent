import base64

import pytest

from app.core.errors import AppError
from app.integrations.ocr import BaiduOCRClient


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self) -> "FakeHttpClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        if url.endswith("/oauth/2.0/token"):
            return FakeResponse({"access_token": "test-token", "expires_in": 3600})
        return FakeResponse(
            {"words_result": [{"words": "第一天：西湖"}, {"words": "午餐：杭帮菜"}]}
        )


@pytest.mark.asyncio
async def test_baidu_ocr_extracts_lines_and_reuses_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_http = FakeHttpClient()
    monkeypatch.setattr(
        "app.integrations.ocr.baidu.httpx.AsyncClient", lambda **kwargs: fake_http
    )
    client = BaiduOCRClient(
        base_url="https://aip.example.com",
        api_key="api-key",
        secret_key="secret-key",
        timeout_seconds=10,
    )

    first = await client.recognize(b"first-image")
    second = await client.recognize(b"second-image")

    assert first == ["第一天：西湖", "午餐：杭帮菜"]
    assert second == first
    assert sum(url.endswith("/oauth/2.0/token") for url, _ in fake_http.calls) == 1
    image_data = fake_http.calls[1][1]["data"]
    assert image_data["image"] == base64.b64encode(b"first-image").decode("ascii")


@pytest.mark.asyncio
async def test_baidu_ocr_requires_credentials() -> None:
    client = BaiduOCRClient(
        base_url="https://aip.example.com",
        api_key="",
        secret_key="",
        timeout_seconds=10,
    )
    with pytest.raises(AppError) as exc_info:
        await client.recognize(b"image")
    assert exc_info.value.code == "OCR_NOT_CONFIGURED"

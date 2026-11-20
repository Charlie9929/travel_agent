from __future__ import annotations

import base64
import time
from functools import lru_cache

import httpx

from app.core.config import get_settings
from app.core.errors import AppError


class BaiduOCRClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        secret_key: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout_seconds = timeout_seconds
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def _require_credentials(self) -> None:
        if not self.api_key or not self.secret_key:
            raise AppError(
                "OCR_NOT_CONFIGURED",
                "攻略截图识别尚未配置，请在后端填写百度 OCR API Key 和 Secret Key",
                status_code=503,
            )

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        self._require_credentials()
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token
        try:
            response = await client.post(
                f"{self.base_url}/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.secret_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(
                "OCR_AUTH_FAILED", "截图识别服务鉴权失败", status_code=502
            ) from exc
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AppError(
                "OCR_AUTH_FAILED",
                "截图识别服务鉴权失败，请检查百度 OCR 密钥",
                status_code=502,
                detail=payload,
            )
        expires_in = max(int(payload.get("expires_in") or 0), 120)
        self._access_token = token
        self._token_expires_at = time.monotonic() + expires_in - 60
        return token

    async def recognize(self, image: bytes) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                token = await self._get_access_token(client)
                response = await client.post(
                    f"{self.base_url}/rest/2.0/ocr/v1/general_basic",
                    params={"access_token": token},
                    data={
                        "image": base64.b64encode(image).decode("ascii"),
                        "language_type": "CHN_ENG",
                        "detect_direction": "true",
                        "paragraph": "true",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise AppError("OCR_TIMEOUT", "攻略截图识别超时，请稍后重试", status_code=504) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(
                "OCR_UNAVAILABLE", "攻略截图识别服务暂时不可用", status_code=502
            ) from exc
        if payload.get("error_code"):
            raise AppError(
                "OCR_FAILED",
                f"攻略截图识别失败：{payload.get('error_msg') or '未知错误'}",
                status_code=502,
                detail={"provider_code": payload.get("error_code")},
            )
        lines = [
            str(item.get("words") or "").strip()
            for item in payload.get("words_result") or []
            if isinstance(item, dict) and str(item.get("words") or "").strip()
        ]
        if not lines:
            raise AppError(
                "OCR_NO_TEXT", "没有从这张截图中识别出文字，请换一张更清晰的图片", status_code=422
            )
        return lines


@lru_cache
def get_baidu_ocr_client() -> BaiduOCRClient:
    settings = get_settings()
    return BaiduOCRClient(
        base_url=settings.baidu_ocr_base_url,
        api_key=settings.baidu_ocr_api_key,
        secret_key=settings.baidu_ocr_secret_key,
        timeout_seconds=settings.baidu_ocr_timeout_seconds,
    )

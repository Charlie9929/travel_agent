import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.errors import AppError


@dataclass(slots=True)
class LLMResult:
    parsed_data: dict[str, Any]
    raw_text: str
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    request_id: str


class LLMClient(Protocol):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        model: str,
        prompt_version: str,
        request_id: str,
        timeout_seconds: float,
        temperature: float = 0.7,
    ) -> LLMResult: ...


class FakeLLMClient:
    def __init__(self, fixture: dict[str, Any] | None = None) -> None:
        self._has_custom_fixture = fixture is not None
        self.fixture = fixture or {
            "schema_version": "1.0",
            "trip_id": "",
            "version": 1,
            "city": {"name": "成都"},
            "meta": {
                "title": "Mock 行程",
                "date_start": "2026-01-01",
                "date_end": "2026-01-01",
                "traveler_count": 1,
                "budget_total": {
                    "amount": 0,
                    "currency": "CNY",
                    "price_type": "estimate",
                    "source": "llm",
                },
            },
            "days": [
                {
                    "date": "2026-01-01",
                    "day_index": 1,
                    "theme": "Mock day",
                    "activities": [],
                    "transfers": [],
                }
            ],
            "cost_summary": {
                "total_estimate": {
                    "amount": 0,
                    "currency": "CNY",
                    "price_type": "estimate",
                    "source": "llm",
                }
            },
            "members": [],
            "permissions": {},
            "revisions": [],
            "candidates": [],
        }

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        model: str,
        prompt_version: str,
        request_id: str,
        timeout_seconds: float,
        temperature: float = 0.7,
    ) -> LLMResult:
        del schema, timeout_seconds, temperature
        fixture = self.fixture
        if not self._has_custom_fixture and "重排模块" in system_prompt:
            request_data = json.loads(user_prompt)
            fixture = {
                "summary": "Fake LLM 重排候选（未修改活动）",
                "diff": {"ops": []},
                "proposed_itinerary": request_data["itinerary_json"],
            }
        elif not self._has_custom_fixture and "修改模块" in system_prompt:
            request_data = json.loads(user_prompt)
            fixture = {
                "summary": "Fake LLM 修订候选（未修改活动）",
                "diff": {"ops": []},
                "proposed_itinerary": request_data["itinerary_json"],
            }
        elif not self._has_custom_fixture and "差异解说器" in system_prompt:
            request_data = json.loads(user_prompt)
            if request_data.get("mode") == "conflict":
                fixture = {
                    "summary": "Fake LLM 冲突差异说明",
                    "my_changes": [],
                    "teammate_changes": [],
                    "both_changed": [],
                }
            else:
                fixture = {"summary": "Fake LLM 差异说明", "by_day": []}
        elif not self._has_custom_fixture and "游记攻略解析器" in system_prompt:
            fixture = {
                "candidates": [
                    {
                        "candidate_id": "cand-1",
                        "title": "宽窄巷子",
                        "type": "poi",
                        "suggested_day_index": 1,
                        "time_slot": {"start": "09:00", "end": "11:00"},
                        "location": {
                            "name": "宽窄巷子",
                            "address": None,
                            "lng": None,
                            "lat": None,
                            "poi_id": None,
                            "poi_source": "llm",
                        },
                        "cost": {
                            "amount": 0,
                            "currency": "CNY",
                            "price_type": "estimate",
                            "source": "llm",
                            "note": "原文称免费",
                        },
                        "note": None,
                        "excerpt": "上午去了宽窄巷子，免费。",
                        "selected": False,
                    }
                ],
                "warnings": [],
            }
        raw = json.dumps(fixture, ensure_ascii=False)
        return LLMResult(
            parsed_data=fixture,
            raw_text=raw,
            model=f"fake:{model}",
            prompt_version=prompt_version,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            request_id=request_id,
        )


class DeepSeekClient:
    def __init__(
        self, *, base_url: str, api_key: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        model: str,
        prompt_version: str,
        request_id: str,
        timeout_seconds: float,
        temperature: float = 0.7,
    ) -> LLMResult:
        del (
            schema
        )  # DeepSeek JSON mode guarantees JSON syntax; local jsonschema performs shape validation.
        if not self.api_key:
            raise AppError("AGENT_LLM_UNAVAILABLE", "未配置 DeepSeek API Key", status_code=503)

        start = time.perf_counter()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": 8192,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AppError("AGENT_LLM_TIMEOUT", "DeepSeek 调用超时", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "AGENT_LLM_UNAVAILABLE", "DeepSeek 服务暂时不可用", status_code=503
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code == 429:
            raise AppError("AGENT_RATE_LIMIT", "DeepSeek 请求频率受限", status_code=429)
        if response.status_code == 402:
            raise AppError("AGENT_QUOTA_EXCEEDED", "DeepSeek 账户额度不足", status_code=402)
        if response.status_code in {400, 413}:
            raise AppError("AGENT_CONTEXT_TOO_LONG", "模型输入过长或请求无效", status_code=413)
        if response.status_code >= 500:
            raise AppError("AGENT_LLM_UNAVAILABLE", "DeepSeek 服务暂时不可用", status_code=503)
        if response.status_code >= 400:
            raise AppError(
                "AGENT_LLM_UNAVAILABLE",
                "DeepSeek 请求失败",
                status_code=502,
                detail={"provider_status": response.status_code},
            )

        body = response.json()
        try:
            content = body["choices"][0]["message"]["content"]
            if not content:
                raise ValueError("empty content")
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(
                "AGENT_OUTPUT_INVALID", "DeepSeek 未返回有效 JSON", status_code=502
            ) from exc

        usage = body.get("usage", {})
        return LLMResult(
            parsed_data=parsed,
            raw_text=content,
            model=body.get("model", model),
            prompt_version=prompt_version,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=round((time.perf_counter() - start) * 1000),
            request_id=request_id,
        )

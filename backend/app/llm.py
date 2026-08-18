from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .collectors.base import CollectedEvent, utc
from .collectors.normalizer import country_from_text, disease_from_text
from .config import Settings
from .models import LlmProvider
from .security import FieldCipher


class LlmProviderError(RuntimeError):
    pass


def validate_provider_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("模型服务地址必须是有效的 HTTP 或 HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模型服务地址不得包含账号、查询参数或片段")
    if parsed.hostname.lower() in {"169.254.169.254", "metadata.google.internal"}:
        raise ValueError("禁止连接云平台元数据地址")
    return value.rstrip("/")


class LlmGateway:
    def __init__(self, settings: Settings, cipher: FieldCipher, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.cipher = cipher
        self.transport = transport

    def _api_key(self, provider: LlmProvider) -> str:
        if not provider.api_key_encrypted:
            return ""
        return self.cipher.decrypt_text(
            provider.api_key_encrypted, context=f"llm-provider:{provider.provider_id}:api-key",
        )

    @staticmethod
    def _headers(provider: LlmProvider, key: str) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if provider.provider_type in {"openai", "openai_compatible"} and key:
            headers["Authorization"] = f"Bearer {key}"
        elif provider.provider_type == "anthropic":
            if key:
                headers["x-api-key"] = key
            headers["anthropic-version"] = str((provider.config_json or {}).get("anthropic_version", "2023-06-01"))
        return headers

    @staticmethod
    def _safe_error(exc: Exception) -> LlmProviderError:
        if isinstance(exc, httpx.HTTPStatusError):
            return LlmProviderError(f"模型服务返回 HTTP {exc.response.status_code}")
        if isinstance(exc, httpx.TimeoutException):
            return LlmProviderError("模型服务连接超时")
        if isinstance(exc, httpx.HTTPError):
            return LlmProviderError("模型服务网络连接失败")
        if isinstance(exc, (KeyError, TypeError, ValueError, json.JSONDecodeError)):
            return LlmProviderError("模型服务响应格式无法识别")
        return LlmProviderError("模型服务调用失败")

    def _client(self, provider: LlmProvider) -> httpx.AsyncClient:
        verify = bool((provider.config_json or {}).get("verify_tls", True))
        timeout = min(120, max(5, int((provider.config_json or {}).get("timeout_seconds", 30))))
        return httpx.AsyncClient(verify=verify, timeout=timeout, follow_redirects=False, transport=self.transport)

    async def fetch_models(self, provider: LlmProvider) -> list[str]:
        base = validate_provider_url(provider.base_url)
        key = self._api_key(provider)
        if provider.provider_type != "ollama" and not key:
            raise LlmProviderError("请先保存 API 密钥")
        try:
            async with self._client(provider) as client:
                if provider.provider_type == "gemini":
                    response = await client.get(f"{base}/models", params={"key": key})
                    response.raise_for_status()
                    models = [str(item["name"]).removeprefix("models/") for item in response.json().get("models", [])]
                elif provider.provider_type == "ollama":
                    response = await client.get(f"{base}/api/tags")
                    response.raise_for_status()
                    models = [str(item["name"]) for item in response.json().get("models", [])]
                else:
                    response = await client.get(f"{base}/models", headers=self._headers(provider, key))
                    response.raise_for_status()
                    models = [str(item["id"]) for item in response.json().get("data", [])]
        except Exception as exc:
            raise self._safe_error(exc) from exc
        return sorted({item for item in models if item})[:2000]

    async def chat(self, provider: LlmProvider, model: str, prompt: str, *, max_tokens: int = 1200) -> str:
        if not model:
            raise LlmProviderError("请先选择模型")
        base = validate_provider_url(provider.base_url)
        key = self._api_key(provider)
        if provider.provider_type != "ollama" and not key:
            raise LlmProviderError("请先保存 API 密钥")
        try:
            async with self._client(provider) as client:
                if provider.provider_type == "anthropic":
                    response = await client.post(
                        f"{base}/messages", headers=self._headers(provider, key),
                        json={"model": model, "max_tokens": max_tokens, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
                    )
                    response.raise_for_status()
                    return "\n".join(str(item.get("text", "")) for item in response.json().get("content", []))
                if provider.provider_type == "gemini":
                    response = await client.post(
                        f"{base}/models/{quote(model, safe='-_.')}:generateContent", params={"key": key},
                        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens}},
                    )
                    response.raise_for_status()
                    return "\n".join(
                        str(part.get("text", ""))
                        for candidate in response.json().get("candidates", [])
                        for part in candidate.get("content", {}).get("parts", [])
                    )
                if provider.provider_type == "ollama":
                    response = await client.post(
                        f"{base}/api/chat",
                        json={"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0}},
                    )
                    response.raise_for_status()
                    return str(response.json().get("message", {}).get("content", ""))
                response = await client.post(
                    f"{base}/chat/completions", headers=self._headers(provider, key),
                    json={"model": model, "temperature": 0, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
                )
                response.raise_for_status()
                return str(response.json()["choices"][0]["message"]["content"])
        except LlmProviderError:
            raise
        except Exception as exc:
            raise self._safe_error(exc) from exc

    async def test_connection(self, provider: LlmProvider, model: str | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        selected = model or provider.selected_model
        models = list(provider.available_models or [])
        if not selected:
            models = await self.fetch_models(provider)
            selected = models[0] if models else None
        if not selected:
            raise LlmProviderError("服务连接成功，但没有发现可测试的模型")
        answer = await self.chat(provider, selected, "只回复 OK，用于连接测试。", max_tokens=8)
        return {
            "status": "success", "model": selected,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "message": f"连接成功，模型响应：{answer.strip()[:80] or '（空响应）'}",
            "models": models,
        }

    async def extract_events(
        self, provider: LlmProvider, model: str, content: bytes, source_name: str, source_url: str,
        prompt_template: str | None = None,
    ) -> list[CollectedEvent]:
        text = content.decode("utf-8", errors="replace")[:120_000]
        instruction = prompt_template or (
            "从以下公共卫生信息源内容提取事件。只输出 JSON 数组，每项包含 title、country、country_code(ISO3)、"
            "disease、event_type、cases、deaths、confidence(0到1)、published_at(ISO8601)、latitude、longitude。"
            "没有可靠事件时输出 []，不得编造缺失事实。"
        )
        raw = await self.chat(provider, model, f"{instruction}\n\n来源：{source_name}\n地址：{source_url}\n内容：\n{text}", max_tokens=4000)
        payload = raw.strip()
        if payload.startswith("```"):
            payload = payload.split("\n", 1)[1].rsplit("```", 1)[0]
        start = min([index for index in (payload.find("["), payload.find("{")) if index >= 0], default=-1)
        if start < 0:
            raise LlmProviderError("模型没有返回可解析的 JSON")
        parsed, _ = json.JSONDecoder().raw_decode(payload[start:])
        items = parsed.get("events", []) if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            raise LlmProviderError("模型事件结果必须是 JSON 数组")
        output: list[CollectedEvent] = []
        for item in items[:200]:
            if not isinstance(item, dict) or not str(item.get("title", "")).strip():
                continue
            title = str(item["title"]).strip()[:500]
            code = str(item.get("country_code", "")).upper()
            country = str(item.get("country", "")).strip()
            if len(code) != 3:
                code, normalized = country_from_text(f"{country} {title}")
                country = country or normalized
            if code == "UNK":
                continue
            published_raw = item.get("published_at")
            try:
                published = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00")) if published_raw else datetime.now(timezone.utc)
            except ValueError:
                published = datetime.now(timezone.utc)
            output.append(CollectedEvent(
                title=title, disease=str(item.get("disease") or disease_from_text(title))[:160],
                country=country or code, country_code=code, source=source_name, source_url=source_url,
                event_type=str(item.get("event_type") or "llm_extracted")[:80],
                cases=max(0, int(float(item.get("cases") or 0))), deaths=max(0, int(float(item.get("deaths") or 0))),
                confidence=min(1.0, max(0.0, float(item.get("confidence") or .5))), published_at=utc(published),
                latitude=float(item.get("latitude") or 0), longitude=float(item.get("longitude") or 0),
            ))
        return output

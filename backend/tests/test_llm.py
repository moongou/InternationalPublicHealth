from __future__ import annotations

import asyncio
import json

import httpx

from app.config import load_settings
from app.llm import LlmGateway
from app.models import LlmProvider
from app.security import FieldCipher


def _provider(cipher: FieldCipher, provider_type: str, base_url: str, provider_id: str = "provider-1") -> LlmProvider:
    item = LlmProvider(
        provider_id=provider_id, name=provider_type, provider_type=provider_type,
        base_url=base_url, selected_model="model-a", available_models=[], config_json={},
        enabled=True, is_default=True,
    )
    if provider_type != "ollama":
        item.api_key_encrypted = cipher.encrypt_text("test-key", context=f"llm-provider:{provider_id}:api-key")
    return item


def test_openai_compatible_model_discovery_connection_and_event_extraction():
    settings = load_settings("internet")
    cipher = FieldCipher(settings)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            assert request.headers["Authorization"] == "Bearer test-key"
            return httpx.Response(200, json={"data": [{"id": "model-b"}, {"id": "model-a"}]})
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if "只回复 OK" in prompt:
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        content = json.dumps([{
            "title": "Brazil dengue update", "country": "Brazil", "country_code": "BRA",
            "disease": "登革热", "event_type": "outbreak", "cases": 20, "deaths": 1,
            "confidence": .9, "published_at": "2026-08-18T00:00:00Z",
            "latitude": -14.2, "longitude": -51.9,
        }], ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    gateway = LlmGateway(settings, cipher, httpx.MockTransport(handler))
    provider = _provider(cipher, "openai_compatible", "https://llm.example.test/v1")

    async def run():
        assert await gateway.fetch_models(provider) == ["model-a", "model-b"]
        result = await gateway.test_connection(provider)
        assert result["status"] == "success" and result["model"] == "model-a"
        events = await gateway.extract_events(provider, "model-a", b"public health feed", "feed", "https://feed.test")
        assert len(events) == 1 and events[0].country_code == "BRA" and events[0].cases == 20

    asyncio.run(run())


def test_anthropic_gemini_and_ollama_model_discovery_formats():
    settings = load_settings("intranet")
    cipher = FieldCipher(settings)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "anthropic.test":
            assert request.headers["x-api-key"] == "test-key"
            return httpx.Response(200, json={"data": [{"id": "claude-test"}]})
        if request.url.host == "gemini.test":
            assert request.url.params["key"] == "test-key"
            return httpx.Response(200, json={"models": [{"name": "models/gemini-test"}]})
        return httpx.Response(200, json={"models": [{"name": "qwen-test"}]})

    gateway = LlmGateway(settings, cipher, httpx.MockTransport(handler))

    async def run():
        assert await gateway.fetch_models(_provider(cipher, "anthropic", "https://anthropic.test/v1", "anthropic")) == ["claude-test"]
        assert await gateway.fetch_models(_provider(cipher, "gemini", "https://gemini.test/v1beta", "gemini")) == ["gemini-test"]
        assert await gateway.fetch_models(_provider(cipher, "ollama", "http://127.0.0.1:11434", "ollama")) == ["qwen-test"]

    asyncio.run(run())

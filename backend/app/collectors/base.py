from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass(frozen=True)
class CollectedEvent:
    title: str
    disease: str
    country: str
    country_code: str
    source: str
    source_url: str | None
    event_type: str
    cases: int
    deaths: int
    confidence: float
    published_at: datetime
    latitude: float | None = None
    longitude: float | None = None


class BaseSourceAdapter(ABC):
    source_id: str
    source_name: str
    url: str
    content_type: str = "application/octet-stream"

    def __init__(self, client: httpx.AsyncClient, retries: int = 3):
        self.client = client
        self.retries = retries

    async def fetch(self) -> bytes:
        error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = await self.client.get(self.url, follow_redirects=True, timeout=45)
                response.raise_for_status()
                return response.content
            except (httpx.HTTPError, TimeoutError) as exc:
                error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"{self.source_name} 采集失败: {error}")

    @abstractmethod
    def parse(self, content: bytes) -> list[CollectedEvent]:
        raise NotImplementedError


def utc(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

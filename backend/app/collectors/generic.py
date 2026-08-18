from __future__ import annotations

import httpx

from .base import BaseSourceAdapter, CollectedEvent
from .rss import RSSSourceAdapter


class ConfiguredRssAdapter(RSSSourceAdapter):
    def __init__(self, client: httpx.AsyncClient, source_id: str, source_name: str, url: str, retries: int = 3):
        super().__init__(client, retries=retries)
        self.source_id = source_id
        self.source_name = source_name
        self.url = url


class WebDocumentAdapter(BaseSourceAdapter):
    content_type = "text/html"

    def __init__(self, client: httpx.AsyncClient, source_id: str, source_name: str, url: str, retries: int = 3):
        super().__init__(client, retries=retries)
        self.source_id = source_id
        self.source_name = source_name
        self.url = url

    def parse(self, content: bytes) -> list[CollectedEvent]:
        return []

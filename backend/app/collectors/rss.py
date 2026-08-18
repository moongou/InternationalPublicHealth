from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from .base import BaseSourceAdapter, CollectedEvent, utc
from .normalizer import country_from_text, disease_from_text, numbers_from_text


class RSSSourceAdapter(BaseSourceAdapter):
    content_type = "application/rss+xml"

    def parse(self, content: bytes) -> list[CollectedEvent]:
        root = ET.fromstring(content)
        output: list[CollectedEvent] = []
        entries = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for entry in entries[:200]:
            def value(name: str) -> str:
                node = entry.find(name)
                if node is None:
                    node = entry.find(f"{{http://www.w3.org/2005/Atom}}{name}")
                if node is None:
                    return ""
                return (node.text or node.attrib.get("href") or "").strip()
            title = value("title")
            description = value("description") or value("summary") or value("content")
            combined = f"{title} {description}"
            code, country = country_from_text(combined)
            if code == "UNK" or not title:
                continue
            published_raw = value("pubDate") or value("published") or value("updated")
            try:
                published = parsedate_to_datetime(published_raw) if "," in published_raw else datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                published = datetime.now(timezone.utc)
            cases, deaths = numbers_from_text(combined)
            output.append(
                CollectedEvent(
                    title=title[:500], disease=disease_from_text(combined), country=country, country_code=code,
                    source=self.source_name, source_url=value("link") or None, event_type="outbreak",
                    cases=cases, deaths=deaths, confidence=0.82, published_at=utc(published),
                )
            )
        return output


class WhoDonsAdapter(RSSSourceAdapter):
    source_id = "who-dons"; source_name = "WHO DONS"; url = "https://www.who.int/rss-feeds/news-english.xml"


class EcdcCdtrAdapter(RSSSourceAdapter):
    source_id = "ecdc-cdtr"; source_name = "ECDC CDTR"; url = "https://www.ecdc.europa.eu/en/news-events/rss"


class ProMedAdapter(RSSSourceAdapter):
    source_id = "promed"; source_name = "ProMED-mail"; url = "https://promedmail.org/feed/"


class HealthMapAdapter(RSSSourceAdapter):
    source_id = "healthmap"; source_name = "HealthMap"; url = "https://www.healthmap.org/rss.php"

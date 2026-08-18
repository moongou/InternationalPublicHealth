from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from ..config import Settings
from ..database import Database
from ..llm import LlmGateway, LlmProviderError
from ..models import Country, CountryRisk, Disease, DiseaseEvent, EventSource, LlmProvider, RawRecord, SourceRun
from ..risk_engine import risk_level
from ..risk_service import RiskCalculationService
from .base import BaseSourceAdapter, CollectedEvent
from .csv_sources import JhuCsseAdapter, OwidAdapter
from .generic import ConfiguredRssAdapter, WebDocumentAdapter
from .rss import EcdcCdtrAdapter, HealthMapAdapter, ProMedAdapter, WhoDonsAdapter


def build_adapters(client: httpx.AsyncClient) -> dict[str, BaseSourceAdapter]:
    items = [WhoDonsAdapter(client), EcdcCdtrAdapter(client), ProMedAdapter(client), JhuCsseAdapter(client), OwidAdapter(client), HealthMapAdapter(client)]
    return {item.source_id: item for item in items}


class CollectorService:
    def __init__(
        self, settings: Settings, database: Database, client: httpx.AsyncClient | None = None,
        llm_gateway: LlmGateway | None = None,
    ):
        self.settings = settings
        self.database = database
        self.client = client or httpx.AsyncClient(headers={"User-Agent": "GlobalHealthMonitor/1.0 (+public-health-monitoring)"})
        self.adapters = build_adapters(self.client)
        self.llm_gateway = llm_gateway

    @staticmethod
    def supports(config: EventSource) -> bool:
        return config.adapter_type in {
            "rss", "jhu_csv", "owid_csv", "web_document",
            "WhoDonsAdapter", "EcdcCdtrAdapter", "ProMedAdapter", "HealthMapAdapter", "JhuCsseAdapter", "OwidAdapter",
        }

    def adapter_for(self, config: EventSource) -> BaseSourceAdapter:
        adapter_type = config.adapter_type
        if adapter_type in {"rss", "WhoDonsAdapter", "EcdcCdtrAdapter", "ProMedAdapter", "HealthMapAdapter"}:
            return ConfiguredRssAdapter(self.client, config.source_id, config.name, config.url)
        if adapter_type in {"jhu_csv", "JhuCsseAdapter"}:
            adapter = JhuCsseAdapter(self.client)
        elif adapter_type in {"owid_csv", "OwidAdapter"}:
            adapter = OwidAdapter(self.client)
        elif adapter_type == "web_document":
            return WebDocumentAdapter(self.client, config.source_id, config.name, config.url)
        else:
            raise KeyError(f"不支持的数据源适配类型: {adapter_type}")
        adapter.source_id = config.source_id
        adapter.source_name = config.name
        adapter.url = config.url
        return adapter

    async def close(self) -> None:
        await self.client.aclose()

    async def run(self, source_id: str) -> dict:
        started_at = datetime.now(timezone.utc)
        try:
            return await self._run_transaction(source_id)
        except Exception as exc:
            # The collection transaction is rolled back on failure. Persist the
            # diagnostic in a separate transaction so operators can see it.
            try:
                with self.database.session() as failure_session:
                    failure_session.add(SourceRun(
                        source=source_id, status="failed", error=str(exc)[:2000],
                        started_at=started_at, finished_at=datetime.now(timezone.utc),
                    ))
            except Exception:
                # Never replace the original collection error with telemetry failure.
                pass
            raise

    async def _run_transaction(self, source_id: str) -> dict:
        with self.database.session() as session:
            source_config = session.get(EventSource, source_id)
            if not source_config:
                raise KeyError(f"未知数据源: {source_id}")
            if not source_config.enabled:
                raise RuntimeError(f"数据源 {source_id} 已禁用")
            adapter = self.adapter_for(source_config)
            run = SourceRun(source=source_id, status="running")
            session.add(run)
            session.flush()
            try:
                content = await adapter.fetch()
                digest = hashlib.sha256(content).hexdigest()
                date_dir = datetime.now(timezone.utc).strftime("%Y/%m/%d")
                suffix = ".xml" if "xml" in adapter.content_type else ".csv" if "csv" in adapter.content_type else ".bin"
                path = self.settings.raw_data_root / source_id / date_dir / f"{digest}{suffix}"
                path.parent.mkdir(parents=True, exist_ok=True)
                existing_raw = session.scalar(select(RawRecord).where(RawRecord.content_hash == digest))
                if not existing_raw:
                    path.write_bytes(content)
                    existing_raw = RawRecord(source=source_id, content_hash=digest, content_type=adapter.content_type, storage_path=str(path))
                    session.add(existing_raw)
                    session.flush()
                parser_mode = str((source_config.config_json or {}).get("parser_mode", "builtin"))
                events = adapter.parse(content) if parser_mode in {"builtin", "hybrid"} else []
                if parser_mode in {"llm", "hybrid"}:
                    if self.llm_gateway is None:
                        raise RuntimeError("大语言模型解析服务未初始化")
                    provider_id = str((source_config.config_json or {}).get("llm_provider_id", ""))
                    provider = session.get(LlmProvider, provider_id) if provider_id else None
                    if not provider or not provider.enabled:
                        raise RuntimeError("信息源配置的大语言模型供应商不存在或未启用")
                    model = str((source_config.config_json or {}).get("llm_model") or provider.selected_model or "")
                    if not model:
                        raise RuntimeError("信息源尚未选择大语言模型")
                    events.extend(await self.llm_gateway.extract_events(
                        provider, model, content, source_config.name, source_config.url,
                        (source_config.config_json or {}).get("prompt_template"),
                    ))
                created = 0
                deduplicated = 0
                known_countries = {item.code: item for item in session.scalars(select(Country)).all()}
                known_diseases = set(session.scalars(select(Disease.name)).all())
                batch_fingerprints: set[str] = set()
                for item in events:
                    if item.country_code != "UNK" and len(item.country_code) == 3:
                        country = known_countries.get(item.country_code)
                        if country is None:
                            country = Country(
                                code=item.country_code, name=item.country, region="未分类",
                                latitude=item.latitude or 0, longitude=item.longitude or 0, health_capacity=50,
                            )
                            session.add(country)
                            known_countries[item.country_code] = country
                        else:
                            if country.name in {country.code, "待识别地区"} and item.country:
                                country.name = item.country
                            if item.latitude or item.longitude:
                                country.latitude = item.latitude
                                country.longitude = item.longitude
                    if item.disease not in known_diseases:
                        session.add(Disease(name=item.disease))
                        known_diseases.add(item.disease)
                    fingerprint = self.fingerprint(item)
                    if fingerprint in batch_fingerprints or session.scalar(select(DiseaseEvent.event_id).where(DiseaseEvent.fingerprint == fingerprint)):
                        deduplicated += 1
                        continue
                    batch_fingerprints.add(fingerprint)
                    country_risk = session.get(CountryRisk, item.country_code)
                    level = risk_level(country_risk.score) if country_risk else "blue"
                    session.add(
                        DiseaseEvent(
                            fingerprint=fingerprint, title=item.title, disease=item.disease, country=item.country,
                            country_code=item.country_code, source=item.source, source_url=item.source_url,
                            event_type=item.event_type, cases=item.cases, deaths=item.deaths,
                            longitude=item.longitude, latitude=item.latitude, confidence=item.confidence,
                            level=level, published_at=item.published_at, raw_record_id=existing_raw.raw_record_id,
                        )
                    )
                    created += 1
                run.status = "success"
                run.records_fetched = len(events)
                run.records_created = created
                run.records_deduplicated = deduplicated
                run.finished_at = datetime.now(timezone.utc)
                session.flush()
                RiskCalculationService().calculate_all(session)
                return {"source": source_id, "fetched": len(events), "created": created, "deduplicated": deduplicated}
            except (Exception, LlmProviderError) as exc:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.finished_at = datetime.now(timezone.utc)
                raise

    async def run_all(self, sources: list[str] | None = None) -> list[dict]:
        if sources is None:
            with self.database.session() as session:
                selected = list(session.scalars(select(EventSource.source_id).where(EventSource.enabled.is_(True))).all())
        else:
            selected = sources
        results = []
        for source in selected:
            try:
                results.append(await self.run(source))
            except Exception as exc:
                results.append({"source": source, "fetched": 0, "created": 0, "deduplicated": 0, "status": "failed", "error": str(exc)[:500]})
        return results

    @staticmethod
    def fingerprint(item: CollectedEvent) -> str:
        key = f"{item.country_code}|{item.disease}|{item.title.strip().lower()}|{item.published_at.date().isoformat()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

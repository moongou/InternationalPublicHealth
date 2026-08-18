from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import func, select

from app.collectors.csv_sources import JhuCsseAdapter, OwidAdapter
from app.collectors.base import CollectedEvent
from app.collectors.service import CollectorService, build_adapters
from app.bootstrap import bootstrap_database
from app.config import load_settings
from app.database import Database
from app.models import Country, CountryRisk, DiseaseEvent, EventSource, RawRecord, RuleDefinition, SourceRun


RSS = b"""<?xml version='1.0' encoding='UTF-8'?>
<rss><channel><item><title>Brazil dengue outbreak: 1,234 cases and 5 deaths</title>
<description>Authorities report dengue activity in Brazil.</description>
<link>https://example.test/event/1</link><pubDate>Mon, 18 Aug 2026 10:00:00 GMT</pubDate></item></channel></rss>"""


def test_six_source_adapters_are_registered():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b""))) as client:
            adapters = build_adapters(client)
            assert set(adapters) == {"who-dons", "ecdc-cdtr", "promed", "jhu-csse", "owid", "healthmap"}
    asyncio.run(run())


def test_collection_raw_storage_normalization_and_deduplication(platform_clients):
    _, _, internet_app, _ = platform_clients

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS, headers={"Content-Type": "application/rss+xml"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = CollectorService(internet_app.state.settings, internet_app.state.database, client)
            first = await service.run("who-dons")
            second = await service.run("who-dons")
            assert first == {"source": "who-dons", "fetched": 1, "created": 1, "deduplicated": 0}
            assert second["created"] == 0 and second["deduplicated"] == 1

    asyncio.run(run())
    with internet_app.state.database.session() as session:
        event = session.scalar(select(DiseaseEvent).where(DiseaseEvent.source_url == "https://example.test/event/1"))
        assert event.country_code == "BRA"
        assert event.disease == "登革热"
        assert event.cases == 1234 and event.deaths == 5
        assert session.scalar(select(func.count()).select_from(RawRecord)) == 1
        assert session.scalar(select(func.count()).select_from(SourceRun).where(SourceRun.status == "success")) == 2
        raw = session.scalar(select(RawRecord).where(RawRecord.source == "who-dons"))
        assert internet_app.state.settings.raw_data_root in __import__('pathlib').Path(raw.storage_path).parents


def test_csv_source_parsers():
    async def run():
        async with httpx.AsyncClient() as client:
            jhu = JhuCsseAdapter(client)
            jhu_csv = b"Province/State,Country/Region,Lat,Long,1/1/26,1/2/26\n,Brazil,-14.2,-51.9,10,15\n"
            parsed = jhu.parse(jhu_csv)
            assert parsed[0].country_code == "BRA" and parsed[0].cases == 15
            owid = OwidAdapter(client)
            owid_csv = b"iso_code,location,date,total_cases,total_deaths\nBRA,Brazil,2026-08-17,100,2\nBRA,Brazil,2026-08-18,120,3\n"
            parsed_owid = owid.parse(owid_csv)
            assert parsed_owid[0].cases == 120 and parsed_owid[0].deaths == 3
    asyncio.run(run())


def test_production_initializes_required_configuration_without_demo_records(tmp_path):
    settings = replace(
        load_settings("internet"),
        database_url=f"sqlite:///{(tmp_path / 'production.db').as_posix()}",
        seed_demo_data=False,
    )
    database = Database(settings.database_url)
    bootstrap_database(database, settings)
    with database.session() as session:
        assert session.query(EventSource).count() == 6
        assert {item.rule_type for item in session.query(RuleDefinition).all()} == {
            "risk_score", "alert_level", "trend_change", "passenger_match", "port_advice",
        }
        assert session.query(DiseaseEvent).count() == 0
        assert session.query(CountryRisk).count() == 0
        session.query(EventSource).delete()
    bootstrap_database(database, settings)
    with database.session() as session:
        assert session.query(EventSource).count() == 0
    database.engine.dispose()


def test_collector_discovers_country_and_calculates_risk(platform_clients):
    _, _, internet_app, _ = platform_clients
    payload = b"iso_code,location,date,total_cases,total_deaths\nZZA,Testland,2026-08-18,10,1\n"

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"Content-Type": "text/csv"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await CollectorService(internet_app.state.settings, internet_app.state.database, client).run("owid")

    asyncio.run(run())
    with internet_app.state.database.session() as session:
        country = session.get(Country, "ZZA")
        risk = session.get(CountryRisk, "ZZA")
        assert country is not None and country.name == "Testland"
        assert risk is not None and risk.model_version == "RISK-v1"


def test_source_interval_and_enabled_state_are_applied_without_restart(platform_clients):
    internet, _, internet_app, _ = platform_clients
    from tests.conftest import auth_headers

    headers = auth_headers(internet)
    updated = internet.patch(
        "/api/v1/sources/who-dons",
        json={"frequency_seconds": 120, "enabled": True},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    job = internet_app.state.scheduler.scheduler.get_job("collector-who-dons")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 120

    disabled = internet.patch(
        "/api/v1/sources/who-dons", json={"enabled": False}, headers=headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert internet_app.state.scheduler.scheduler.get_job("collector-who-dons") is None


def test_user_can_add_cron_source_and_switch_schedule_without_restart(platform_clients):
    internet, _, internet_app, _ = platform_clients
    from tests.conftest import auth_headers

    headers = auth_headers(internet)
    created = internet.post(
        "/api/v1/sources",
        json={
            "source_id": "custom-health-feed", "name": "自定义公共卫生源", "adapter_type": "rss",
            "url": "https://feeds.example.test/health.xml", "schedule_type": "cron",
            "cron_expression": "*/15 * * * *", "parser_mode": "builtin",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    job = internet_app.state.scheduler.scheduler.get_job("collector-custom-health-feed")
    assert job is not None and "cron" in str(job.trigger)

    updated = internet.patch(
        "/api/v1/sources/custom-health-feed",
        json={"schedule_type": "interval", "frequency_seconds": 300},
        headers=headers,
    )
    assert updated.status_code == 200
    job = internet_app.state.scheduler.scheduler.get_job("collector-custom-health-feed")
    assert job.trigger.interval.total_seconds() == 300
    deleted = internet.delete("/api/v1/sources/custom-health-feed", headers=headers)
    assert deleted.status_code == 200
    assert internet_app.state.scheduler.scheduler.get_job("collector-custom-health-feed") is None


def test_cron_source_uses_user_selected_timezone(platform_clients):
    internet, _, internet_app, _ = platform_clients
    from tests.conftest import auth_headers

    headers = auth_headers(internet)
    created = internet.post(
        "/api/v1/sources",
        json={
            "source_id": "utc-health-feed", "name": "UTC health feed", "adapter_type": "rss",
            "url": "https://feeds.example.test/utc.xml", "schedule_type": "cron",
            "schedule_timezone": "UTC", "cron_expression": "5 2 * * *", "parser_mode": "builtin",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["schedule_timezone"] == "UTC"
    job = internet_app.state.scheduler.scheduler.get_job("collector-utc-health-feed")
    assert job is not None and str(job.trigger.timezone) == "UTC"

    invalid = internet.patch(
        "/api/v1/sources/utc-health-feed",
        json={"schedule_timezone": "Invalid/Timezone"},
        headers=headers,
    )
    assert invalid.status_code == 422


def test_invalid_cron_source_is_rejected(platform_clients):
    internet, _, _, _ = platform_clients
    from tests.conftest import auth_headers

    response = internet.post(
        "/api/v1/sources",
        json={
            "source_id": "bad-cron", "name": "错误计划", "adapter_type": "rss",
            "url": "https://feeds.example.test/health.xml", "schedule_type": "cron",
            "cron_expression": "not-a-cron", "parser_mode": "builtin",
        },
        headers=auth_headers(internet),
    )
    assert response.status_code == 422


def test_collection_failure_is_persisted_for_operators(platform_clients):
    _, _, internet_app, _ = platform_clients
    service = CollectorService(internet_app.state.settings, internet_app.state.database)

    class FailingAdapter:
        async def fetch(self):
            raise RuntimeError("upstream unavailable")

    service.adapter_for = lambda _config: FailingAdapter()
    with pytest.raises(RuntimeError, match="upstream unavailable"):
        asyncio.run(service.run("who-dons"))

    with internet_app.state.database.session() as session:
        failed = session.scalar(
            select(SourceRun).where(SourceRun.source == "who-dons").order_by(SourceRun.started_at.desc()).limit(1)
        )
        assert failed is not None and failed.status == "failed"
        assert failed.finished_at is not None and "upstream unavailable" in failed.error


def test_collect_all_continues_after_one_source_fails(platform_clients):
    _, _, internet_app, _ = platform_clients
    service = CollectorService(internet_app.state.settings, internet_app.state.database)
    visited = []

    async def fake_run(source_id: str):
        visited.append(source_id)
        if source_id == "broken-source":
            raise RuntimeError("source unavailable")
        return {"source": source_id, "fetched": 1, "created": 1, "deduplicated": 0}

    service.run = fake_run
    results = asyncio.run(service.run_all(["broken-source", "healthy-source"]))
    assert visited == ["broken-source", "healthy-source"]
    assert results[0]["status"] == "failed"
    assert results[1]["source"] == "healthy-source" and results[1]["created"] == 1


def test_user_source_can_use_selected_llm_for_extraction(platform_clients):
    internet, _, internet_app, _ = platform_clients
    from datetime import datetime, timezone
    from tests.conftest import auth_headers

    headers = auth_headers(internet)
    provider = internet.post(
        "/api/v1/admin/llm/providers",
        json={
            "name": "采集模型", "provider_type": "openai_compatible",
            "base_url": "https://llm.example.test/v1", "api_key": "secret",
            "selected_model": "extractor", "enabled": True,
        },
        headers=headers,
    ).json()
    source = internet.post(
        "/api/v1/sources",
        json={
            "source_id": "llm-web-source", "name": "模型解析网页", "adapter_type": "web_document",
            "url": "https://source.example.test/report", "parser_mode": "llm",
            "llm_provider_id": provider["provider_id"], "llm_model": "extractor",
            "schedule_type": "interval", "frequency_seconds": 600,
        },
        headers=headers,
    )
    assert source.status_code == 201, source.text

    class FakeGateway:
        async def extract_events(self, *_args, **_kwargs):
            return [CollectedEvent(
                title="Testland outbreak", disease="测试传染病", country="Testland", country_code="TST",
                source="模型解析网页", source_url="https://source.example.test/report", event_type="outbreak",
                cases=9, deaths=1, confidence=.9, published_at=datetime.now(timezone.utc),
            )]

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>public health report</html>")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = CollectorService(
                internet_app.state.settings, internet_app.state.database, client, llm_gateway=FakeGateway(),
            )
            return await service.run("llm-web-source")

    result = asyncio.run(run())
    assert result["created"] == 1
    with internet_app.state.database.session() as session:
        event = session.scalar(select(DiseaseEvent).where(DiseaseEvent.country_code == "TST"))
        assert event is not None and event.source == "模型解析网页"

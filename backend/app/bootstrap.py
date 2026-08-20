from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from .config import Settings
from .database import Database
from .demo_data import ALERTS, COUNTRIES, EVENTS, RISK_HISTORY, TRANSFER_LINKS
from .models import Alert, BootstrapMarker, Country, CountryRisk, CountryRiskHistory, Disease, DiseaseEvent, EventSource, Port, RuleDefinition, TransferLink, User
from .ports_data import PORTS
from .security import hash_password


SOURCE_PRESETS_PATH = Path(__file__).resolve().parents[1] / "config" / "source_presets.json"
SOURCE_PRESETS_MARKER = "internet-source-presets-v3"

SYSTEM_RULES = [
    ("RISK-v1", "RISK", "全球国家风险加权评分", "risk_score", "按六因子计算国家综合风险", {"all": True}, {"weights": {"severity": .25, "transmission": .25, "scale": .15, "travel": .15, "transit": .10, "capacity": .10}}, 10),
    ("ALERT-v1", "ALERT", "红色预警阈值", "alert_level", "综合风险分达到阈值时触发预警", {"field": "score", "operator": "gte", "value": 80}, {"level": "red"}, 20),
    ("TREND-v1", "TREND", "七日病例突增", "trend_change", "七日病例增长率达到阈值时触发预警", {"field": "growth_7d", "operator": "gt", "value": 200}, {"threshold_percent": 200}, 30),
    ("PAX-v1", "PAX", "旅客风险匹配", "passenger_match", "按旅居地风险、健康申报和中转链路匹配", {"any": [{"field": "highest_country_score", "operator": "gte", "value": 40}, {"field": "health_declaration", "operator": "eq", "value": False}, {"field": "transit_count", "operator": "gt", "value": 0}]}, {"score_adjustment": 0}, 5),
    ("PORT-v1", "PORT", "口岸分级布控", "port_advice", "按口岸类型和预警等级生成布控措施", {"all": True}, {}, 50),
]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _source_presets() -> list[dict]:
    return json.loads(SOURCE_PRESETS_PATH.read_text(encoding="utf-8"))


def bootstrap_database(database: Database, settings: Settings) -> None:
    database.create_schema()
    with database.session() as session:
        if not session.scalar(select(func.count()).select_from(User)):
            session.add(
                User(
                    username="admin",
                    display_name="系统管理员",
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role="system_admin",
                    status="active",
                )
            )

        # 开发阶段免密超级管理员（如 rfg）：不存在则创建，角色始终为 system_admin
        for dev_username in settings.dev_passwordless_users:
            dev_user = session.scalar(select(User).where(User.username == dev_username))
            if dev_user is None:
                session.add(
                    User(
                        username=dev_username,
                        display_name=f"{dev_username}（开发免密管理员）",
                        password_hash=hash_password("Aa1!" + secrets.token_urlsafe(48)),
                        role="system_admin",
                        status="active",
                    )
                )

        if settings.deployment_mode == "internet" and not session.get(BootstrapMarker, SOURCE_PRESETS_MARKER):
            presets = _source_presets()
            if not session.scalar(select(func.count()).select_from(EventSource)):
                session.add_all([
                    EventSource(
                        source_id=item["source_id"], name=item["name"], adapter_type=item["adapter_type"],
                        url=item["url"], frequency_seconds=item["frequency_seconds"],
                        config_json=item.get("config_json", {}),
                    )
                    for item in presets
                ])
            else:
                # 幂等迁移：刷新内置源的 URL / 解析配置，并补入新增内置源；不覆盖用户自行新增的源
                existing = {source.source_id: source for source in session.scalars(select(EventSource))}
                for item in presets:
                    source = existing.get(item["source_id"])
                    if source is not None:
                        source.url = item["url"]
                        source.config_json = item.get("config_json", {})
                    else:
                        session.add(
                            EventSource(
                                source_id=item["source_id"], name=item["name"], adapter_type=item["adapter_type"],
                                url=item["url"], frequency_seconds=item["frequency_seconds"],
                                config_json=item.get("config_json", {}),
                            )
                        )
            session.add(BootstrapMarker(marker_key=SOURCE_PRESETS_MARKER))
        if not session.scalar(select(func.count()).select_from(RuleDefinition)):
            published_at = datetime.now(timezone.utc)
            session.add_all([
                RuleDefinition(
                    rule_id=rule_id, rule_key=rule_key, name=name, rule_type=rule_type,
                    description=description, condition_json=condition, action_json=action,
                    version=1, status="published", priority=priority, created_by="system",
                    published_at=published_at,
                )
                for rule_id, rule_key, name, rule_type, description, condition, action, priority in SYSTEM_RULES
            ])

        # 内网口岸库：海、陆、空、铁全量口岸预生成（幂等，非演示数据，不依赖 seed_demo_data）
        if settings.deployment_mode == "intranet" and not session.scalar(select(func.count()).select_from(Port)):
            session.add_all([
                Port(
                    name=item["name"], port_type=item["type"],
                    longitude=item["lng"], latitude=item["lat"],
                    risk_level=item["risk"], enabled=True,
                )
                for item in PORTS
            ])

        if not settings.seed_demo_data:
            return
        if not session.scalar(select(func.count()).select_from(Disease)):
            session.add_all([Disease(name=name) for name in sorted({item["disease"] for item in EVENTS})])
        if session.scalar(select(func.count()).select_from(Country)):
            return

        country_codes: dict[str, str] = {}
        for item in COUNTRIES:
            factors = item["factors"]
            country = Country(
                code=item["code"], name=item["name"], region=item["region"],
                longitude=item["center"][0], latitude=item["center"][1],
                health_capacity=float(factors["capacity"]),
                travel_intensity=float(factors["travel"]), transit_risk=float(factors["transit"]),
                updated_at=_dt(item["updated_at"]),
            )
            session.add(country)
            session.add(
                CountryRisk(
                    country_code=item["code"], score=item["risk_score"], level=item["level"],
                    factors=factors, model_version="risk-v8", calculated_at=_dt(item["updated_at"]),
                )
            )
            country_codes[item["name"]] = item["code"]

        # Flush parent rows before dependent seed rows. This is explicit because
        # the seed path intentionally avoids ORM relationships between bounded contexts.
        session.flush()

        for item in EVENTS:
            fingerprint = hashlib.sha256(
                f"{item['source']}|{item['title']}|{item['country_code']}|{item['published_at']}".encode()
            ).hexdigest()
            session.add(
                DiseaseEvent(
                    event_id=item["id"], fingerprint=fingerprint, title=item["title"],
                    disease=item["disease"], country=item["country"], country_code=item["country_code"],
                    source=item["source"], event_type=item["event_type"], cases=item["cases"], deaths=item["deaths"],
                    level=item["level"],
                    longitude=item["coordinates"][0], latitude=item["coordinates"][1],
                    confidence=item["confidence"], published_at=_dt(item["published_at"]),
                )
            )

        for item in TRANSFER_LINKS:
            session.add(
                TransferLink(
                    link_id=item["id"], origin_country_code=country_codes[item["origin"]],
                    origin=item["origin"], destination=item["destination"],
                    source_coordinates=item["source"], target_coordinates=item["target"], via=item["via"],
                    risk=item["risk"], volume=item["volume"],
                )
            )

        for point in RISK_HISTORY:
            date_value = point["date"] if len(point["date"]) > 5 else f"2026-{point['date']}"
            measured = datetime.fromisoformat(f"{date_value}T00:00:00+08:00")
            for code, key in (("COD", "africa"), ("IND", "asia"), ("BRA", "americas")):
                session.add(
                    CountryRiskHistory(
                        country_code=code, score=float(point[key]),
                        level="red" if point[key] >= 80 else "orange" if point[key] >= 60 else "yellow" if point[key] >= 40 else "blue",
                        factors={}, calculated_at=measured,
                    )
                )

        for item in ALERTS:
            session.add(
                Alert(
                    alert_id=item["id"], country_code=country_codes.get(item["country"], "CHN"),
                    disease=item["disease"], title=item["title"], score=item["score"], level=item["level"],
                    advice=item["advice"], status=item["status"], issued_at=_dt(item["issued_at"]),
                )
            )

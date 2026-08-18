from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Alert, Country, CountryRisk, CountryRiskHistory, DiseaseEvent, RuleDefinition
from .risk_engine import calculate_risk


class RiskCalculationService:
    model_version = "risk-v1.0"

    def calculate_all(self, session: Session) -> dict[str, int | float]:
        started = datetime.now(timezone.utc)
        countries = session.scalars(select(Country)).all()
        rule = session.scalar(
            select(RuleDefinition).where(
                RuleDefinition.rule_type == "risk_score", RuleDefinition.status == "published",
            ).order_by(RuleDefinition.version.desc()).limit(1)
        )
        weights = (rule.action_json or {}).get("weights") if rule else None
        model_version = rule.rule_id if rule else self.model_version
        alerts_created = 0
        for country in countries:
            factors = self.factors(session, country, started)
            score, level = calculate_risk(factors, weights)
            current = session.get(CountryRisk, country.code)
            previous_level = current.level if current else None
            if not current:
                current = CountryRisk(country_code=country.code, score=score, level=level)
                session.add(current)
            current.score = score
            current.level = level
            current.factors = factors
            current.model_version = model_version
            current.calculated_at = started
            session.add(
                CountryRiskHistory(
                    country_code=country.code, score=score, level=level,
                    factors=factors, calculated_at=started,
                )
            )
            if level in {"red", "orange"} and level != previous_level:
                self._upsert_alert(session, country, score, level, started)
                alerts_created += 1
        session.flush()
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        return {"countries": len(countries), "alerts_created": alerts_created, "elapsed_seconds": round(elapsed, 3)}

    @staticmethod
    def factors(session: Session, country: Country, now: datetime) -> dict[str, float]:
        recent = session.execute(
            select(
                func.coalesce(func.sum(DiseaseEvent.cases), 0),
                func.coalesce(func.sum(DiseaseEvent.deaths), 0),
                func.coalesce(func.max(DiseaseEvent.severity), 0),
            ).where(DiseaseEvent.country_code == country.code, DiseaseEvent.published_at >= now - timedelta(days=30))
        ).one()
        current_cases = session.scalar(
            select(func.coalesce(func.sum(DiseaseEvent.cases), 0)).where(
                DiseaseEvent.country_code == country.code, DiseaseEvent.published_at >= now - timedelta(days=7)
            )
        ) or 0
        previous_cases = session.scalar(
            select(func.coalesce(func.sum(DiseaseEvent.cases), 0)).where(
                DiseaseEvent.country_code == country.code,
                DiseaseEvent.published_at >= now - timedelta(days=14),
                DiseaseEvent.published_at < now - timedelta(days=7),
            )
        ) or 0
        cases, deaths, reported_severity = (float(recent[0]), float(recent[1]), float(recent[2]))
        fatality = deaths / cases if cases else 0
        severity = min(100, max(reported_severity, fatality * 1200))
        growth = (current_cases - previous_cases) / max(previous_cases, 1)
        transmission = min(100, max(0, 50 + growth * 25))
        scale = min(100, math.log10(cases + 1) / 7 * 100)
        return {
            "severity": round(severity, 2), "transmission": round(transmission, 2),
            "scale": round(scale, 2), "travel": round(country.travel_intensity, 2),
            "transit": round(country.transit_risk, 2), "capacity": round(country.health_capacity, 2),
        }

    @staticmethod
    def _upsert_alert(session: Session, country: Country, score: float, level: str, issued: datetime) -> None:
        existing = session.scalar(
            select(Alert).where(Alert.country_code == country.code, Alert.status == "active", Alert.disease == "综合风险")
        )
        advice = {
            "red": "实施重点布控、健康申报复核、专用通道和采样检测",
            "orange": "加强健康申报、体温筛查和风险比例抽检",
        }[level]
        if existing:
            existing.score = score; existing.level = level; existing.advice = advice; existing.issued_at = issued
        else:
            session.add(
                Alert(
                    country_code=country.code, disease="综合风险", title=f"{country.name}输入风险{level}色预警",
                    score=score, level=level, advice=advice, status="active", issued_at=issued,
                )
            )

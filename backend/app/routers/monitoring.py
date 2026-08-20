from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..demo_data import geojson
from ..models import Alert, Country, CountryRisk, CountryRiskHistory, DiseaseEvent, Passenger, SourceRun, TransferLink


router = APIRouter(tags=["monitoring"])
read_access = require_roles("system_admin", "data_analyst", "port_operator", "auditor", "read_only")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _event(item: DiseaseEvent) -> dict[str, Any]:
    return {
        "id": item.event_id, "title": item.title, "country_code": item.country_code,
        "country": item.country, "disease": item.disease, "event_type": item.event_type,
        "cases": item.cases, "deaths": item.deaths, "level": item.level,
        "source": item.source, "source_url": item.source_url,
        "published_at": _iso(item.published_at), "confidence": item.confidence,
        "coordinates": [item.longitude, item.latitude] if item.longitude is not None and item.latitude is not None else [0, 0],
    }


def _country_rows(session: Session, region: str | None = None, level: str | None = None) -> list[dict[str, Any]]:
    statement = select(Country, CountryRisk).join(CountryRisk, CountryRisk.country_code == Country.code)
    if region:
        statement = statement.where(Country.region == region)
    if level:
        statement = statement.where(CountryRisk.level == level)
    rows = session.execute(statement.order_by(CountryRisk.score.desc())).all()
    output: list[dict[str, Any]] = []
    for country, risk in rows:
        cases, deaths = session.execute(
            select(func.coalesce(func.sum(DiseaseEvent.cases), 0), func.coalesce(func.sum(DiseaseEvent.deaths), 0))
            .where(DiseaseEvent.country_code == country.code)
        ).one()
        history = session.scalars(
            select(CountryRiskHistory).where(CountryRiskHistory.country_code == country.code)
            .order_by(CountryRiskHistory.calculated_at.desc()).limit(2)
        ).all()
        trend = 0.0
        if len(history) > 1 and history[1].score:
            trend = round((history[0].score - history[1].score) / history[1].score * 100, 1)
        output.append(
            {
                "code": country.code, "name": country.name, "region": country.region,
                "center": [country.longitude, country.latitude], "risk_score": risk.score, "level": risk.level,
                "active_cases": int(cases), "deaths": int(deaths), "trend_7d": trend,
                "factors": risk.factors, "updated_at": _iso(risk.calculated_at),
            }
        )
    return output


@router.get("/events")
def events(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    country: str | None = None, disease: str | None = None, level: str | None = None,
    q: str | None = None, start: datetime | None = None, end: datetime | None = None,
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    conditions = []
    if country:
        conditions.append(or_(DiseaseEvent.country.ilike(f"%{country}%"), DiseaseEvent.country_code == country.upper()))
    if disease:
        conditions.append(DiseaseEvent.disease.ilike(f"%{disease}%"))
    if level:
        conditions.append(DiseaseEvent.level == level)
    if q:
        conditions.append(or_(DiseaseEvent.title.ilike(f"%{q}%"), DiseaseEvent.country.ilike(f"%{q}%"), DiseaseEvent.disease.ilike(f"%{q}%"), DiseaseEvent.source.ilike(f"%{q}%")))
    if start:
        conditions.append(DiseaseEvent.published_at >= start)
    if end:
        conditions.append(DiseaseEvent.published_at <= end)
    count_statement = select(func.count()).select_from(DiseaseEvent)
    statement = select(DiseaseEvent)
    for condition in conditions:
        count_statement = count_statement.where(condition)
        statement = statement.where(condition)
    total = session.scalar(count_statement) or 0
    items = session.scalars(
        statement.order_by(DiseaseEvent.published_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_event(item) for item in items], "total": total, "page": page, "page_size": page_size}


@router.get("/countries")
def countries(
    request: Request,
    region: str | None = None, level: str | None = None,
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    key = f"{request.app.state.settings.deployment_mode}:countries:{region or '*'}:{level or '*'}"
    return request.app.state.cache.get_or_set(key, lambda: _country_rows(session, region, level))


@router.get("/risk-scores")
def risk_scores(
    country_code: str | None = None,
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(CountryRiskHistory, Country).join(Country, Country.code == CountryRiskHistory.country_code)
    if country_code:
        statement = statement.where(CountryRiskHistory.country_code == country_code.upper())
    rows = session.execute(statement.order_by(CountryRiskHistory.calculated_at)).all()

    region_keys = {"非洲": "africa", "亚洲": "asia", "美洲": "americas", "欧洲": "europe", "大洋洲": "oceania"}
    # 按完整日期分组（保持时间顺序），并统计每个日期覆盖的国家集合，用于判断当日是否为“部分采集”。
    dates: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for history, country in rows:
        day = history.calculated_at
        sort_key = day.strftime("%Y-%m-%d")
        if sort_key not in dates:
            dates[sort_key] = {"date": day.strftime("%m-%d"), "values": defaultdict(list), "countries": set()}
        region = region_keys.get(country.region, "other")
        dates[sort_key]["values"]["global"].append(history.score)
        dates[sort_key]["values"][region].append(history.score)
        dates[sort_key]["countries"].add(country.code)

    # 覆盖率以“历史中出现过的国家全集”为分母，避免演示数据或少量采集被误判为全量。
    total_countries: set[str] = set()
    for info in dates.values():
        total_countries |= info["countries"]

    history_output: list[dict[str, Any]] = []
    for info in dates.values():
        point: dict[str, Any] = {"date": info["date"], "forecast": None}
        for key, values in info["values"].items():
            point[key] = round(sum(values) / len(values), 1)
        coverage = round(len(info["countries"]) / len(total_countries), 3) if total_countries else 1.0
        point["coverage"] = coverage
        point["partial"] = coverage < 0.999
        history_output.append(point)

    _apply_global_forecast(history_output)

    selected_countries = _country_rows(session)
    if country_code:
        selected_countries = [item for item in selected_countries if item["code"] == country_code.upper()]
    return {"history": history_output, "countries": selected_countries}


def _apply_global_forecast(points: list[dict[str, Any]]) -> None:
    """当某日为“部分采集”时，用历史完整覆盖点的线性趋势外推全球风险预测值。

    前端据此区分呈现：完整覆盖日用实线，部分覆盖日用虚线作为预测趋势，
    避免把部分国家的加总直接当作全量风险值，导致趋势线失真。
    """
    full = [(i, p["global"]) for i, p in enumerate(points) if p.get("global") is not None and not p.get("partial")]
    if not any(p.get("partial") for p in points):
        return
    slope: float | None = None
    intercept: float | None = None
    if len(full) >= 2:
        xs = [x for x, _ in full]
        ys = [y for _, y in full]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
            intercept = my - slope * mx
    last_full = full[-1][1] if full else None
    for i, p in enumerate(points):
        if p.get("partial") and p.get("global") is not None:
            if slope is not None and intercept is not None:
                p["forecast"] = round(max(0.0, min(100.0, slope * i + intercept)), 1)
            elif last_full is not None:
                p["forecast"] = last_full


@router.get("/alerts")
def alerts(
    level: str | None = None, active_only: bool = True,
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(Alert, Country).join(Country, Country.code == Alert.country_code)
    if level:
        statement = statement.where(Alert.level == level)
    if active_only:
        statement = statement.where(Alert.status == "active")
    return [
        {
            "id": alert.alert_id, "title": alert.title, "level": alert.level, "country": country.name,
            "country_code": country.code, "disease": alert.disease, "score": alert.score,
            "status": alert.status, "issued_at": _iso(alert.issued_at), "advice": alert.advice,
        }
        for alert, country in session.execute(statement.order_by(Alert.issued_at.desc())).all()
    ]


@router.get("/stats")
def stats(request: Request, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        level_rows = session.execute(select(CountryRisk.level, func.count()).group_by(CountryRisk.level)).all()
        levels = {key: value for key, value in level_rows}
        source_total = session.scalar(select(func.count(func.distinct(SourceRun.source)))) or 0
        source_failures = session.scalar(select(func.count()).select_from(SourceRun).where(SourceRun.status == "failed", SourceRun.started_at >= now - timedelta(days=1))) or 0
        return {
            "monitored_countries": session.scalar(select(func.count()).select_from(Country)) or 0,
            "active_events": session.scalar(select(func.count()).select_from(DiseaseEvent).where(DiseaseEvent.published_at >= now - timedelta(days=30))) or 0,
            "new_events_24h": session.scalar(select(func.count()).select_from(DiseaseEvent).where(DiseaseEvent.collected_at >= now - timedelta(days=1))) or 0,
            "active_alerts": session.scalar(select(func.count()).select_from(Alert).where(Alert.status == "active")) or 0,
            "high_risk_countries": levels.get("red", 0) + levels.get("orange", 0),
            "passengers_screened_today": session.scalar(select(func.count()).select_from(Passenger).where(Passenger.entry_time >= now.replace(hour=0, minute=0, second=0, microsecond=0))) or 0,
            "level_distribution": levels,
            "source_health": {"healthy": max(0, source_total - source_failures), "degraded": source_failures, "offline": 0},
            "last_updated": now.isoformat(),
        }
    key = f"{request.app.state.settings.deployment_mode}:stats"
    return request.app.state.cache.get_or_set(key, build)


@router.get("/map/geojson")
def map_geojson(request: Request, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    def build() -> dict[str, Any]:
        collection = geojson()
        risks = {item["code"]: item for item in _country_rows(session)}
        for feature_item in collection["features"]:
            code = feature_item.get("properties", {}).get("code")
            if code in risks:
                feature_item["properties"].update(risks[code])
        return collection
    key = f"{request.app.state.settings.deployment_mode}:map:geojson"
    return request.app.state.cache.get_or_set(key, build)


@router.get("/map/events")
def map_events(level: str | None = None, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    statement = select(DiseaseEvent)
    if level:
        statement = statement.where(DiseaseEvent.level == level)
    items = session.scalars(statement.order_by(DiseaseEvent.published_at.desc()).limit(1000)).all()
    return {"items": [_event(item) for item in items], "total": len(items)}


@router.get("/map/risk-history")
def map_risk_history(
    days: int = Query(30, ge=1, le=365),
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.scalars(
        select(CountryRiskHistory)
        .where(CountryRiskHistory.calculated_at >= cutoff)
        .order_by(CountryRiskHistory.calculated_at)
    ).all()
    return [
        {
            "country_code": item.country_code,
            "score": item.score,
            "level": item.level,
            "factors": item.factors,
            "calculated_at": _iso(item.calculated_at),
        }
        for item in rows
    ]


@router.get("/map/transfer-links")
def map_transfer_links(_: Principal = Depends(read_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {"id": item.link_id, "origin": item.origin, "destination": item.destination,
         "source": item.source_coordinates, "target": item.target_coordinates, "risk": item.risk,
         "volume": item.volume, "via": item.via}
        for item in session.scalars(select(TransferLink).order_by(TransferLink.risk.desc())).all()
    ]


@router.get("/map/passenger-flows")
def map_passenger_flows(_: Principal = Depends(read_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {"country_code": country.code, "country": country.name, "source": [country.longitude, country.latitude],
         "target": [104.2, 35.86], "intensity": country.travel_intensity}
        for country in session.scalars(select(Country).order_by(Country.travel_intensity.desc())).all()
    ]

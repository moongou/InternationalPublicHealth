from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..models import Alert, Country, CountryRisk, Passenger, ReceivedPackage, RuleDefinition
from ..passenger_files import parse_passenger_file
from ..risk_engine import calculate_passenger_risk, risk_level
from ..rule_engine import RuleEngine
from ..schemas import PassengerCreate, PortAdviceRequest


router = APIRouter(tags=["intranet"])
port_access = require_roles("system_admin", "data_analyst", "port_operator")
read_access = require_roles("system_admin", "data_analyst", "port_operator", "auditor", "read_only")
admin_access = require_roles("system_admin")


def _mask(value: str) -> str:
    return "*" * max(0, len(value) - 4) + value[-4:]


def _risk_for_country(session: Session, name: str) -> tuple[str, float, bool]:
    country = session.scalar(select(Country).where((Country.name == name) | (Country.code == name.upper())))
    if not country:
        return name, 20.0, False
    risk = session.get(CountryRisk, country.code)
    active_red = bool(session.scalar(select(Alert.alert_id).where(Alert.country_code == country.code, Alert.level == "red", Alert.status == "active")))
    score = max(float(risk.score if risk else 20), 80.0 if active_red else 0)
    return country.name, score, active_red


def _serialize_passenger(item: Passenger, request: Request) -> dict[str, Any]:
    cipher = request.app.state.field_cipher
    name = cipher.decrypt_text(item.name_encrypted, context=f"passenger:{item.passenger_id}:name")
    document = cipher.decrypt_text(item.document_encrypted, context=f"passenger:{item.passenger_id}:document")
    return {
        "passenger_id": item.passenger_id, "document_type": item.document_type,
        "document_number": _mask(document), "name": name[:1] + "*" * max(1, len(name) - 1),
        "gender": item.gender, "birth_date": item.birth_date.isoformat() if item.birth_date else None,
        "nationality": item.nationality, "travel_history": item.travel_history,
        "transit_countries": item.transit_countries, "entry_port": item.entry_port,
        "entry_time": item.entry_time.isoformat(), "flight_no": item.flight_no, "seat_no": item.seat_no,
        "health_declaration": item.health_declaration,
        "contact_info": {"phone": "已加密", "email": "已加密"} if item.contact_encrypted else None,
        "risk_analysis": {"score": item.risk_score, "level": item.risk_level, "reasons": item.risk_reasons,
                          "advice": item.advice, "rule_version": item.matched_rule_version,
                          "matched_at": item.created_at.isoformat()},
    }


def _add_passenger(session: Session, request: Request, model: PassengerCreate) -> Passenger:
    if session.get(Passenger, model.passenger_id):
        raise HTTPException(409, f"旅客记录 {model.passenger_id} 已存在")
    arrival_date = model.entry_time.date()
    cutoff = arrival_date - timedelta(days=14)
    scores: list[tuple[str, float]] = []
    for trip in model.travel_history:
        if trip.exit_date < cutoff or trip.entry_date > arrival_date:
            continue
        country, score, red = _risk_for_country(session, trip.country)
        scores.append((f"{country}（生效红色预警）" if red else country, score))
    for transit in model.transit_countries:
        country, score, red = _risk_for_country(session, transit)
        scores.append((f"中转·{country}（生效红色预警）" if red else f"中转·{country}", score))
    result = calculate_passenger_risk(scores, model.health_declaration, len(model.transit_countries))
    passenger_rule = session.scalar(
        select(RuleDefinition).where(
            RuleDefinition.rule_type == "passenger_match", RuleDefinition.status == "published",
        ).order_by(RuleDefinition.version.desc()).limit(1)
    )
    rule_output: dict[str, Any] = {}
    if passenger_rule:
        highest_score = max((score for _, score in scores), default=0.0)
        execution = RuleEngine().execute(session, passenger_rule, {
            "highest_country_score": highest_score,
            "health_declaration": model.health_declaration,
            "transit_count": len(model.transit_countries),
            "computed_score": result.score,
            "computed_level": result.level,
        })
        if execution["matched"]:
            rule_output = execution["output"]
    try:
        adjustment = float(rule_output.get("score_adjustment", 0))
        minimum_score = float(rule_output.get("minimum_score", 0))
    except (TypeError, ValueError):
        adjustment = minimum_score = 0
    adjusted_score = round(min(100.0, max(0.0, max(result.score + adjustment, minimum_score))), 1)
    adjusted_level = risk_level(adjusted_score)
    reasons = list(result.reasons)
    if adjusted_score != result.score and passenger_rule:
        reasons.append(f"规则 {passenger_rule.rule_id} 调整风险分至 {adjusted_score:.1f}")
    advice_by_level = {
        "red": ["引导至专用检疫通道", "开展流行病学调查", "按病种要求采样检测", "通知属地联防联控"],
        "orange": ["加强健康申报核验", "实施体温复测", "按比例开展核酸抽检"],
        "yellow": ["核验健康申报", "常规体温监测", "发放健康提示"],
        "blue": ["执行常态卫生检疫"],
    }
    configured_advice = rule_output.get("advice")
    advice = configured_advice if isinstance(configured_advice, list) and all(isinstance(item, str) for item in configured_advice) else advice_by_level[adjusted_level]
    cipher = request.app.state.field_cipher
    contact = model.contact_info.model_dump(mode="json") if model.contact_info else None
    item = Passenger(
        passenger_id=model.passenger_id, document_type=model.document_type,
        document_hash=cipher.blind_index(model.document_number),
        document_encrypted=cipher.encrypt_text(model.document_number, context=f"passenger:{model.passenger_id}:document"),
        name_encrypted=cipher.encrypt_text(model.name, context=f"passenger:{model.passenger_id}:name"),
        contact_encrypted=cipher.encrypt_json(contact, context=f"passenger:{model.passenger_id}:contact") if contact else None,
        gender=model.gender, birth_date=model.birth_date, nationality=model.nationality,
        travel_history=[trip.model_dump(mode="json") for trip in model.travel_history],
        transit_countries=model.transit_countries, entry_port=model.entry_port, entry_time=model.entry_time,
        flight_no=model.flight_no, seat_no=model.seat_no, health_declaration=model.health_declaration,
        risk_score=adjusted_score, risk_level=adjusted_level, risk_reasons=reasons, advice=advice,
        matched_rule_version=passenger_rule.rule_id if passenger_rule else "builtin-passenger-v1",
    )
    session.add(item)
    session.flush()
    return item


@router.post("/passengers/risk-batch")
def passenger_risk_batch(
    items: list[PassengerCreate], request: Request, _: Principal = Depends(port_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    results = [_serialize_passenger(_add_passenger(session, request, item), request) for item in items]
    return {"items": results, "total": len(results)}


@router.post("/passengers", status_code=status.HTTP_201_CREATED)
def create_passengers(
    body: PassengerCreate | list[PassengerCreate], request: Request,
    _: Principal = Depends(port_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    models = body if isinstance(body, list) else [body]
    results = [_serialize_passenger(_add_passenger(session, request, item), request) for item in models]
    return {"items": results, "total": len(results)}


@router.get("/passengers/{passenger_id}")
def get_passenger(
    passenger_id: str, request: Request, _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(Passenger, passenger_id)
    if not item: raise HTTPException(404, "未找到旅客风险记录")
    return _serialize_passenger(item, request)


@router.get("/passengers")
def list_passengers(
    request: Request, level: str | None = None, port: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(Passenger); count = select(func.count()).select_from(Passenger)
    if level: statement=statement.where(Passenger.risk_level==level); count=count.where(Passenger.risk_level==level)
    if port: statement=statement.where(Passenger.entry_port==port); count=count.where(Passenger.entry_port==port)
    items = session.scalars(statement.order_by(Passenger.entry_time.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [_serialize_passenger(item, request) for item in items], "total": session.scalar(count) or 0, "page": page, "page_size": page_size}


@router.post("/passengers/import", status_code=status.HTTP_201_CREATED)
async def import_passengers(
    request: Request, file: UploadFile = File(...), _: Principal = Depends(port_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    content = await file.read()
    try:
        models = parse_passenger_file(content, file.filename or "")
    except (UnicodeDecodeError, csv.Error, json.JSONDecodeError, KeyError, ValidationError, ValueError) as exc:
        raise HTTPException(422, f"导入文件格式错误: {exc}") from exc
    results = [_serialize_passenger(_add_passenger(session, request, item), request) for item in models]
    return {"items": results, "total": len(results)}


@router.post("/passengers/import/scan")
def scan_passenger_inbox(request: Request, _: Principal = Depends(admin_access)) -> dict[str, Any]:
    results = request.app.state.passenger_scanner.scan()
    return {"items": results, "total": len(results)}


@router.get("/health-alerts")
def health_alerts(_: Principal = Depends(read_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [{"alert_id": a.alert_id,"country_code":a.country_code,"title":a.title,"level":a.level,"score":a.score,"advice":a.advice,"issued_at":a.issued_at.isoformat()} for a in session.scalars(select(Alert).where(Alert.status=="active").order_by(Alert.score.desc())).all()]


@router.post("/port-advice")
def port_advice(body: PortAdviceRequest, _: Principal = Depends(port_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    rule = session.scalar(select(RuleDefinition).where(RuleDefinition.rule_type=="port_advice",RuleDefinition.status=="published").order_by(RuleDefinition.version.desc()).limit(1))
    context={"port":{"name":body.port_name,"type":body.port_type},"alert":{"level":body.alert_level}}
    output=RuleEngine().execute(session,rule,context)["output"] if rule else {}
    common={"red":["设置专用检疫通道","100%健康申报复核","开展流行病学调查","异常人员闭环转运"],"orange":["加强健康申报核验","100%体温复测","按风险比例采样抽检"],"yellow":["常规申报核验","体温监测","发放健康提示卡"],"blue":["执行常态卫生检疫"]}
    specific={"airport":"协调航空公司开展机上广播","seaport":"加强船员换班与登临检疫","land":"优化车辆与人员分流"}[body.port_type]
    return {"port_name":body.port_name,"alert_level":body.alert_level,"measures":output.get("measures",common[body.alert_level]+[specific]),"priority":output.get("priority","urgent" if body.alert_level=="red" else "normal"),"legal_basis":output.get("legal_basis",["《中华人民共和国国境卫生检疫法》","口岸突发公共卫生事件应急预案"]),"generated_at":datetime.now(timezone.utc).isoformat()}


@router.get("/transfer/receiver/status")
def receiver_status(request: Request, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    latest=session.scalar(select(ReceivedPackage).order_by(ReceivedPackage.received_at.desc()).limit(1)); failed=session.scalar(select(func.count()).select_from(ReceivedPackage).where(ReceivedPackage.status=="failed")) or 0
    return {"status":"online","last_package":latest.package_id if latest else None,"last_received_at":latest.received_at.isoformat() if latest else None,"packages_total":session.scalar(select(func.count()).select_from(ReceivedPackage)) or 0,"signature_failures":failed,"api_polling_enabled":request.app.state.settings.enable_api_polling}


@router.post("/transfer/receiver/scan")
def scan_receiver(request: Request, _: Principal = Depends(admin_access)) -> dict[str, Any]:
    results=request.app.state.transfer_receiver.scan_directory();return {"items":results,"total":len(results)}


@router.post("/transfer/receiver/consume-queue")
def consume_receiver(request: Request, _: Principal = Depends(admin_access)) -> dict[str, Any]:
    results=request.app.state.transfer_receiver.consume_queue();return {"items":results,"total":len(results)}


@router.post("/transfer/receiver/poll-api")
def poll_receiver_api(request: Request, _: Principal = Depends(admin_access)) -> dict[str, Any]:
    settings = request.app.state.settings
    if not settings.enable_api_polling:
        raise HTTPException(409, "API 轮询通道未在配置中启用")
    results = request.app.state.transfer_receiver.poll_api(settings.api_poll_base_url, settings.transfer_api_key)
    return {"items": results, "total": len(results)}


@router.post("/transfer/receiver/upload")
async def upload_package(request: Request, file: UploadFile = File(...), _: Principal = Depends(admin_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    package=await file.read()
    if len(package)>500*1024*1024: raise HTTPException(413,"数据包不得超过 500MB")
    return request.app.state.transfer_receiver.process(session,package)

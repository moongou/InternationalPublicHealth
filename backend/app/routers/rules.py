from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..models import RuleDefinition, RuleExecutionLog
from ..risk_engine import calculate_risk
from ..rule_engine import RuleEngine, evaluate_conditions
from ..schemas import RuleCreate, RuleTestRequest, RuleUpdate


router = APIRouter(prefix="/rules", tags=["rules"])
read_access = require_roles("system_admin", "data_analyst", "port_operator", "auditor", "read_only")
edit_access = require_roles("system_admin", "data_analyst")


def _serialize(rule: RuleDefinition) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id, "rule_key": rule.rule_key, "name": rule.name, "type": rule.rule_type,
        "description": rule.description, "condition_json": rule.condition_json, "action_json": rule.action_json,
        "priority": rule.priority, "version": rule.version, "status": rule.status,
        "updated_at": (rule.published_at or rule.created_at).isoformat(),
        "published_at": rule.published_at.isoformat() if rule.published_at else None,
    }


@router.get("")
def list_rules(
    type: str | None = None, status_filter: str | None = Query(None, alias="status"), history: bool = False,
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(RuleDefinition).order_by(RuleDefinition.rule_key, RuleDefinition.version.desc())
    if type:
        statement = statement.where(RuleDefinition.rule_type == type)
    if status_filter:
        statement = statement.where(RuleDefinition.status == status_filter)
    items = session.scalars(statement).all()
    if not history:
        latest: dict[str, RuleDefinition] = {}
        for item in items:
            latest.setdefault(item.rule_key, item)
        items = list(latest.values())
    return [_serialize(item) for item in items]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(
    body: RuleCreate, principal: Principal = Depends(edit_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    rule_key = f"R{secrets.token_hex(3).upper()}"
    item = RuleDefinition(
        rule_id=f"{rule_key}-v1", rule_key=rule_key, name=body.name, rule_type=body.type,
        description=body.description, condition_json=body.condition_json, action_json=body.action_json,
        priority=body.priority, version=1, status="draft", created_by=principal.user_id,
    )
    session.add(item)
    session.flush()
    return _serialize(item)


@router.put("/{rule_id}")
def update_rule(
    rule_id: str, body: RuleUpdate, principal: Principal = Depends(edit_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    current = session.get(RuleDefinition, rule_id)
    if not current:
        raise HTTPException(404, "规则不存在")
    latest = session.scalar(
        select(RuleDefinition).where(RuleDefinition.rule_key == current.rule_key)
        .order_by(RuleDefinition.version.desc()).limit(1)
    )
    values = body.model_dump(exclude_none=True)
    version = latest.version + 1
    item = RuleDefinition(
        rule_id=f"{current.rule_key}-v{version}", rule_key=current.rule_key,
        name=values.get("name", current.name), rule_type=current.rule_type,
        description=values.get("description", current.description),
        condition_json=values.get("condition_json", current.condition_json),
        action_json=values.get("action_json", current.action_json),
        priority=values.get("priority", current.priority), version=version, status="draft",
        created_by=principal.user_id,
    )
    session.add(item)
    session.flush()
    return _serialize(item)


@router.post("/{rule_id}/publish")
def publish_rule(
    rule_id: str, _: Principal = Depends(edit_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(RuleDefinition, rule_id)
    if not item:
        raise HTTPException(404, "规则不存在")
    validation_context = {
        "score": 50, "growth_7d": 0, "current": 100, "previous": 100,
        "highest_country_score": 50, "health_declaration": True, "transit_count": 0,
        "port": {"name": "测试口岸", "type": "airport"}, "alert": {"level": "yellow"},
    }
    try:
        evaluate_conditions(item.condition_json, validation_context)
        if item.rule_type == "risk_score":
            calculate_risk(
                {"severity": 50, "transmission": 50, "scale": 50, "travel": 50, "transit": 50, "capacity": 50},
                (item.action_json or {}).get("weights"),
            )
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"规则定义校验失败: {exc}") from exc
    siblings = session.scalars(select(RuleDefinition).where(RuleDefinition.rule_key == item.rule_key)).all()
    for sibling in siblings:
        if sibling.status == "published":
            sibling.status = "retired"
    item.status = "published"
    item.published_at = datetime.now(timezone.utc)
    session.flush()
    return _serialize(item)


@router.post("/{rule_id}/test")
def test_rule(
    rule_id: str, body: RuleTestRequest, _: Principal = Depends(edit_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(RuleDefinition, rule_id)
    if not item:
        raise HTTPException(404, "规则不存在")
    execution = RuleEngine().execute(session, item, body.context)
    return {
        "rule_id": item.rule_id, "version": item.version, "success": True,
        "execution_ms": execution["execution_ms"],
        "output": {"matched": execution["matched"], **execution["output"]},
    }


@router.get("/{rule_id}/executions")
def execution_logs(
    rule_id: str, limit: int = Query(50, ge=1, le=500),
    _: Principal = Depends(read_access), session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    items = session.scalars(
        select(RuleExecutionLog).where(RuleExecutionLog.rule_id == rule_id)
        .order_by(RuleExecutionLog.executed_at.desc()).limit(limit)
    ).all()
    return [
        {"execution_id": item.execution_id, "matched": item.matched, "output": item.output_json,
         "execution_ms": item.execution_ms, "executed_at": item.executed_at.isoformat()}
        for item in items
    ]

from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import RuleDefinition, RuleExecutionLog
from .risk_engine import calculate_risk, risk_level


def _path(context: dict[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator in {"eq", "=="}:
        return actual == expected
    if operator in {"ne", "!="}:
        return actual != expected
    if operator in {"gt", ">"}:
        return actual is not None and actual > expected
    if operator in {"gte", ">="}:
        return actual is not None and actual >= expected
    if operator in {"lt", "<"}:
        return actual is not None and actual < expected
    if operator in {"lte", "<="}:
        return actual is not None and actual <= expected
    if operator == "in":
        return actual in expected if isinstance(expected, (list, tuple, set, str)) else False
    if operator == "contains":
        return expected in actual if isinstance(actual, (list, tuple, set, str)) else False
    if operator == "exists":
        return (actual is not None) is bool(expected)
    if operator == "within_days":
        if actual is None:
            return False
        actual_date = date.fromisoformat(actual) if isinstance(actual, str) else actual.date() if isinstance(actual, datetime) else actual
        return actual_date >= datetime.now(timezone.utc).date() - timedelta(days=int(expected))
    raise ValueError(f"不支持的规则操作符: {operator}")


def evaluate_conditions(definition: Any, context: dict[str, Any]) -> bool:
    if definition in ({}, None, True) or definition == {"all": True}:
        return True
    if isinstance(definition, list):
        return all(evaluate_conditions(item, context) for item in definition)
    if not isinstance(definition, dict):
        return bool(definition)
    if "all" in definition:
        value = definition["all"]
        return bool(value) if isinstance(value, bool) else all(evaluate_conditions(item, context) for item in value)
    if "any" in definition:
        value = definition["any"]
        return any(evaluate_conditions(item, context) for item in value)
    if "not" in definition:
        return not evaluate_conditions(definition["not"], context)
    return _compare(_path(context, str(definition.get("field", ""))), str(definition.get("operator", "eq")), definition.get("value"))


class RuleEngine:
    def execute(self, session: Session, rule: RuleDefinition, context: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        matched = evaluate_conditions(rule.condition_json, context)
        output: dict[str, Any] = {}
        if matched:
            output = self._action(rule, context)
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        context_hash = hashlib.sha256(
            json.dumps(context, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
        session.add(
            RuleExecutionLog(
                rule_id=rule.rule_id, context_hash=context_hash, matched=matched,
                output_json=output, execution_ms=elapsed,
            )
        )
        return {"matched": matched, "output": output, "execution_ms": elapsed}

    @staticmethod
    def _action(rule: RuleDefinition, context: dict[str, Any]) -> dict[str, Any]:
        action = dict(rule.action_json or {})
        if rule.rule_type == "risk_score":
            score, level = calculate_risk(context.get("factors", {}), action.get("weights"))
            return {"score": score, "level": level}
        if rule.rule_type == "alert_level":
            score = float(context.get("score", 0))
            return {"score": score, "level": risk_level(score), **{k: v for k, v in action.items() if k != "thresholds"}}
        if rule.rule_type == "trend_change":
            current = float(context.get("current", 0))
            previous = float(context.get("previous", 0))
            change = 0.0 if previous == 0 else round((current - previous) / previous * 100, 2)
            threshold = float(action.get("threshold_percent", 200))
            return {"change_percent": change, "triggered": change >= threshold, **action}
        return action

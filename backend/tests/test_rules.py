from __future__ import annotations

from tests.conftest import auth_headers


def test_rule_version_publish_test_and_execution_log(platform_clients):
    internet, _, _, _ = platform_clients
    headers = auth_headers(internet)
    rules = internet.get("/api/v1/rules", headers=headers).json()
    current = next(item for item in rules if item["type"] == "risk_score")
    updated = internet.put(
        f"/api/v1/rules/{current['rule_id']}",
        json={"condition_json": {"all": True}, "action_json": current["action_json"]}, headers=headers,
    )
    assert updated.status_code == 200, updated.text
    draft = updated.json()
    assert draft["version"] == current["version"] + 1
    assert draft["status"] == "draft"
    published = internet.post(f"/api/v1/rules/{draft['rule_id']}/publish", headers=headers)
    assert published.status_code == 200
    factors = {"severity": 90, "transmission": 80, "scale": 70, "travel": 60, "transit": 50, "capacity": 20}
    tested = internet.post(f"/api/v1/rules/{draft['rule_id']}/test", json={"context": {"factors": factors}}, headers=headers)
    assert tested.status_code == 200
    assert tested.json()["output"]["level"] == "orange"
    executions = internet.get(f"/api/v1/rules/{draft['rule_id']}/executions", headers=headers)
    assert executions.status_code == 200
    assert len(executions.json()) == 1


def test_rule_any_and_not_conditions(platform_clients):
    internet, _, _, _ = platform_clients
    headers = auth_headers(internet)
    created = internet.post(
        "/api/v1/rules",
        json={
            "name": "趋势条件测试", "type": "trend_change",
            "condition_json": {"all": [{"field": "country", "operator": "eq", "value": "BRA"}, {"not": {"field": "disabled", "operator": "eq", "value": True}}]},
            "action_json": {"threshold_percent": 100}, "priority": 20,
        }, headers=headers,
    ).json()
    result = internet.post(
        f"/api/v1/rules/{created['rule_id']}/test",
        json={"context": {"country": "BRA", "disabled": False, "current": 300, "previous": 100}}, headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["output"]["triggered"] is True


def test_published_risk_weights_drive_country_recalculation(platform_clients):
    internet, _, _, _ = platform_clients
    headers = auth_headers(internet)
    current = next(item for item in internet.get("/api/v1/rules", headers=headers).json() if item["type"] == "risk_score")
    weights = {"severity": 1.0, "transmission": 0.0, "scale": 0.0, "travel": 0.0, "transit": 0.0, "capacity": 0.0}
    draft = internet.put(
        f"/api/v1/rules/{current['rule_id']}", json={"action_json": {"weights": weights}}, headers=headers,
    ).json()
    assert internet.post(f"/api/v1/rules/{draft['rule_id']}/publish", headers=headers).status_code == 200
    assert internet.post("/api/v1/risk-scores/recalculate", headers=headers).status_code == 200
    country = internet.get("/api/v1/countries", headers=headers).json()[0]
    assert country["risk_score"] == country["factors"]["severity"]


def test_invalid_risk_weights_cannot_be_published(platform_clients):
    internet, _, _, _ = platform_clients
    headers = auth_headers(internet)
    current = next(item for item in internet.get("/api/v1/rules", headers=headers).json() if item["type"] == "risk_score")
    draft = internet.put(
        f"/api/v1/rules/{current['rule_id']}",
        json={"action_json": {"weights": {"severity": 0.9, "transmission": 0.9}}},
        headers=headers,
    ).json()
    response = internet.post(f"/api/v1/rules/{draft['rule_id']}/publish", headers=headers)
    assert response.status_code == 422

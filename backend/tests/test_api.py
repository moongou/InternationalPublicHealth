from __future__ import annotations

from datetime import date

from app.models import Passenger
from tests.conftest import auth_headers


def test_platform_routes_are_physically_isolated(platform_clients):
    internet, intranet, _, _ = platform_clients
    internet_paths = set(internet.get("/openapi.json").json()["paths"])
    intranet_paths = set(intranet.get("/openapi.json").json()["paths"])
    assert "/api/v1/passengers" not in internet_paths
    assert "/api/v1/transfer/receiver/upload" not in internet_paths
    assert "/api/v1/sources/run" in internet_paths
    assert "/api/v1/passengers" in intranet_paths
    assert "/api/v1/sources/run" not in intranet_paths


def test_authenticated_monitoring_and_filters(platform_clients):
    internet, _, _, _ = platform_clients
    assert internet.get("/api/v1/stats").status_code == 401
    headers = auth_headers(internet)
    stats = internet.get("/api/v1/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["monitored_countries"] >= 10
    response = internet.get("/api/v1/events", params={"level": "red", "page_size": 5}, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert all(item["level"] == "red" for item in response.json()["items"])
    assert internet.get("/api/v1/map/geojson", headers=headers).json()["type"] == "FeatureCollection"


def test_passenger_is_calculated_masked_and_encrypted(platform_clients):
    _, intranet, _, intranet_app = platform_clients
    headers = auth_headers(intranet)
    payload = {
        "passenger_id": "PAX-TEST-001", "document_number": "G12345678", "name": "张三", "nationality": "中国",
        "travel_history": [{"country": "刚果民主共和国", "entry_date": "2026-08-10", "exit_date": "2026-08-15"}],
        "transit_countries": ["新加坡"], "entry_port": "北京首都国际机场",
        "entry_time": "2026-08-18T10:30:00+08:00", "health_declaration": True,
        "contact_info": {"phone": "13800138000", "email": "zhangsan@example.com"},
    }
    response = intranet.post("/api/v1/passengers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result = response.json()["items"][0]
    assert result["risk_analysis"]["level"] == "red"
    assert result["risk_analysis"]["rule_version"] == "PAX-v1"
    assert result["document_number"] == "*****5678"
    assert result["name"] == "张*"
    with intranet_app.state.database.session() as session:
        stored = session.get(Passenger, payload["passenger_id"])
        assert b"G12345678" not in stored.document_encrypted
        assert b"13800138000" not in stored.contact_encrypted
        assert stored.document_hash != payload["document_number"]
    executions = intranet.get("/api/v1/rules/PAX-v1/executions", headers=headers)
    assert executions.status_code == 200 and len(executions.json()) == 1


def test_old_travel_is_ignored_and_batch_supported(platform_clients):
    _, intranet, _, _ = platform_clients
    headers = auth_headers(intranet)
    payload = {
        "passenger_id": "PAX-OLD", "document_number": "G87654321", "name": "李四", "nationality": "中国",
        "travel_history": [{"country": "刚果民主共和国", "entry_date": "2026-06-01", "exit_date": "2026-07-01"}],
        "entry_port": "北京首都国际机场", "entry_time": "2026-08-18T10:30:00+08:00", "health_declaration": True,
    }
    response = intranet.post("/api/v1/passengers/risk-batch", json=[payload], headers=headers)
    assert response.status_code == 200
    assert response.json()["items"][0]["risk_analysis"]["level"] == "blue"


def test_csv_passenger_import(platform_clients):
    _, intranet, _, _ = platform_clients
    headers = auth_headers(intranet)
    csv_content = (
        "passenger_id,document_number,name,nationality,travel_country,travel_entry_date,travel_exit_date,entry_port,entry_time,health_declaration\n"
        "PAX-CSV-1,P99887766,王五,中国,巴西,2026-08-10,2026-08-15,上海浦东国际机场,2026-08-18T12:00:00+08:00,true\n"
    )
    response = intranet.post(
        "/api/v1/passengers/import", headers=headers,
        files={"file": ("passengers.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["total"] == 1


def test_configured_passenger_inbox_is_scanned_and_archived_encrypted(platform_clients):
    _, intranet, _, intranet_app = platform_clients
    root = intranet_app.state.settings.passenger_inbound_roots[0]
    path = root / "PASSENGER_20260818_001.jsonl"
    path.write_text(
        '{"passenger_id":"P-SCAN-1","document_type":"护照","document_number":"G87654321",'
        '"name":"扫描旅客","nationality":"中国","travel_history":[],"transit_countries":[],'
        '"entry_port":"上海浦东国际机场","entry_time":"2026-08-18T10:30:00Z",'
        '"health_declaration":true}\n',
        encoding="utf-8",
    )
    results = intranet_app.state.passenger_scanner.scan()
    assert results == [{"file": path.name, "status": "imported", "records": 1}]
    assert not path.exists()
    archive = list((root / "processed").glob("*.enc"))
    assert len(archive) == 1
    assert b"G87654321" not in archive[0].read_bytes()
    response = intranet.get("/api/v1/passengers/P-SCAN-1", headers=auth_headers(intranet))
    assert response.status_code == 200
    assert response.json()["document_number"].endswith("4321")


def test_port_advice_and_health_alerts(platform_clients):
    _, intranet, _, _ = platform_clients
    headers = auth_headers(intranet)
    response = intranet.post(
        "/api/v1/port-advice",
        json={"port_name": "北京首都国际机场", "port_type": "airport", "alert_level": "red"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["priority"] == "urgent"
    assert intranet.get("/api/v1/health-alerts", headers=headers).status_code == 200

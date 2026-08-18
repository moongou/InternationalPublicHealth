from __future__ import annotations

import time

from tests.conftest import auth_headers


def test_acceptance_performance_thresholds(platform_clients):
    internet, intranet, _, _ = platform_clients
    internet_headers = auth_headers(internet)
    intranet_headers = auth_headers(intranet)

    started = time.perf_counter()
    recalculated = internet.post("/api/v1/risk-scores/recalculate", headers=internet_headers)
    full_score_seconds = time.perf_counter() - started
    assert recalculated.status_code == 200, recalculated.text
    assert full_score_seconds < 10, f"全量国家评分耗时 {full_score_seconds:.3f}s"

    payload = {
        "passenger_id": "P-PERF-001",
        "document_number": "P12345678",
        "name": "性能测试",
        "nationality": "中国",
        "travel_history": [],
        "transit_countries": [],
        "entry_port": "北京首都国际机场",
        "entry_time": "2026-08-18T10:30:00+08:00",
        "health_declaration": True,
    }
    started = time.perf_counter()
    passenger = intranet.post("/api/v1/passengers", json=payload, headers=intranet_headers)
    passenger_seconds = time.perf_counter() - started
    assert passenger.status_code == 201, passenger.text
    assert passenger_seconds < 0.1, f"单旅客风险匹配耗时 {passenger_seconds * 1000:.2f}ms"

    durations = []
    for _ in range(10):
        started = time.perf_counter()
        response = internet.get("/api/v1/countries", headers=internet_headers)
        durations.append(time.perf_counter() - started)
        assert response.status_code == 200
    assert max(durations) < 2, f"API 最大响应耗时 {max(durations):.3f}s"

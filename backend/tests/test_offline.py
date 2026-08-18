from __future__ import annotations

import socket

from tests.conftest import auth_headers


def test_intranet_core_apis_make_no_external_connection(platform_clients, monkeypatch):
    _, intranet, _, _ = platform_clients

    def deny_connection(*_args, **_kwargs):
        raise AssertionError("内网核心请求尝试建立外部网络连接")

    monkeypatch.setattr(socket.socket, "connect", deny_connection)
    headers = auth_headers(intranet)
    for path in ("/api/v1/stats", "/api/v1/countries", "/api/v1/map/geojson", "/api/v1/health-alerts"):
        response = intranet.get(path, headers=headers)
        assert response.status_code == 200, response.text

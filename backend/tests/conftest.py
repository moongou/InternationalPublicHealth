from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_internet_app, create_intranet_app
from app.config import load_settings


@pytest.fixture()
def platform_clients(tmp_path):
    common = {
        "transfer_root": tmp_path / "transfer",
        "inbound_root": tmp_path / "inbound",
        "backup_root": tmp_path / "backups",
        "raw_data_root": tmp_path / "raw",
        "passenger_inbound_roots": (tmp_path / "passenger-inbound",),
        "log_root": tmp_path / "logs",
        "enable_scheduler": False,
        "transfer_secret": "test-transfer-secret-with-at-least-32-characters",
        "transfer_api_key": "test-transfer-api-key-with-32-characters",
    }
    internet_settings = replace(
        load_settings("internet"), database_url=f"sqlite:///{(tmp_path / 'internet.db').as_posix()}", **common,
    )
    intranet_settings = replace(
        load_settings("intranet"), database_url=f"sqlite:///{(tmp_path / 'intranet.db').as_posix()}", **common,
    )
    internet_app = create_internet_app(internet_settings)
    intranet_app = create_intranet_app(intranet_settings)
    with TestClient(internet_app) as internet, TestClient(intranet_app) as intranet:
        yield internet, intranet, internet_app, intranet_app


def auth_headers(client: TestClient, username: str = "admin", password: str = "LocalAdmin@2026") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

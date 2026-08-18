from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pyotp

from app.models import LlmProvider
from app.security import hash_password, verify_password
from app.directory_auth import DirectoryIdentity
from tests.conftest import auth_headers


def test_password_hash_uses_unique_bcrypt_salts():
    first = hash_password("StrongPassword@1")
    second = hash_password("StrongPassword@1")
    assert first != second
    assert first.startswith("$2")
    assert verify_password("StrongPassword@1", first)
    assert not verify_password("wrong", first)


def test_lockout_rbac_and_cross_platform_tokens(platform_clients):
    internet, intranet, _, _ = platform_clients
    admin = auth_headers(internet)
    created = internet.post(
        "/api/v1/admin/users",
        json={"username": "reader", "display_name": "只读测试", "password": "ReaderPassword@1", "role": "read_only"},
        headers=admin,
    )
    assert created.status_code == 201
    for _ in range(5):
        assert internet.post("/api/v1/auth/login", json={"username": "reader", "password": "wrong-password"}).status_code == 401
    assert internet.post("/api/v1/auth/login", json={"username": "reader", "password": "ReaderPassword@1"}).status_code == 423

    internet.post(
        f"/api/v1/admin/users/{created.json()['user_id']}/reset-password",
        json={"password": "ReaderPassword@2"}, headers=admin,
    )
    reader = auth_headers(internet, "reader", "ReaderPassword@2")
    assert internet.get("/api/v1/stats", headers=reader).status_code == 200
    assert internet.get("/api/v1/admin/backups", headers=reader).status_code == 403
    assert intranet.get("/api/v1/stats", headers=reader).status_code == 401


def test_real_backup_is_created_and_verified(platform_clients):
    internet, _, internet_app, _ = platform_clients
    headers = auth_headers(internet)
    resource = internet_app.state.settings.raw_data_root / "nested" / "event.json"
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text('{"version": 1}', encoding="utf-8")
    response = internet.post("/api/v1/admin/backups", json={"backup_type": "full"}, headers=headers)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["status"] == "verified"
    assert item["size"] > 0
    assert len(item["checksum"]) == 64
    backups = list(internet_app.state.settings.backup_root.glob("*.sqlite3"))
    assert len(backups) == 1 and backups[0].is_file()
    assets = backups[0].with_suffix(backups[0].suffix + ".assets.tar.gz")
    assert assets.is_file() and assets.stat().st_size > 0
    assert internet.get(
        f"/api/v1/admin/backups/{item['backup_id']}/assets/download", headers=headers,
    ).status_code == 200

    resource.write_text('{"version": 2}', encoding="utf-8")
    restored = internet.post(
        f"/api/v1/admin/backups/{item['backup_id']}/restore",
        json={"confirmation": item["backup_id"]},
        headers=headers,
    )
    assert restored.status_code == 202, restored.text
    assert resource.read_text(encoding="utf-8") == '{"version": 1}'


def test_audit_log_has_no_delete_route(platform_clients):
    internet, _, _, _ = platform_clients
    paths = internet.get("/openapi.json").json()["paths"]
    assert "delete" not in paths["/api/v1/admin/logs"]
    admin = auth_headers(internet)
    created = internet.post(
        "/api/v1/admin/users",
        json={"username": "auditor", "display_name": "审计员", "password": "AuditPassword@1", "role": "auditor"},
        headers=admin,
    )
    assert created.status_code == 201
    assert internet.get("/api/v1/admin/logs", headers=admin).status_code == 403
    logs = internet.get("/api/v1/admin/logs", headers=auth_headers(internet, "auditor", "AuditPassword@1"))
    assert logs.status_code == 200
    assert logs.json()["total"] >= 1


def test_mfa_enrollment_login_and_admin_enforcement(platform_clients):
    _, intranet, _, intranet_app = platform_clients
    login = intranet.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "LocalAdmin@2026"},
    )
    assert login.status_code == 200
    plain_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    setup = intranet.post("/api/v1/auth/mfa/setup", headers=plain_headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["provisioning_uri"].startswith("otpauth://totp/")

    invalid = intranet.post(
        "/api/v1/auth/mfa/enable", headers=plain_headers, json={"code": "000000"},
    )
    assert invalid.status_code == 422
    enabled = intranet.post(
        "/api/v1/auth/mfa/enable",
        headers=plain_headers,
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert enabled.status_code == 200

    no_otp = intranet.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "LocalAdmin@2026"},
    )
    assert no_otp.status_code == 401
    verified = intranet.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "LocalAdmin@2026",
            "otp": pyotp.TOTP(secret).now(),
        },
    )
    assert verified.status_code == 200
    verified_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}

    intranet_app.state.settings = replace(intranet_app.state.settings, require_admin_mfa=True)
    assert intranet.get("/api/v1/admin/stats/overview", headers=plain_headers).status_code == 403
    assert intranet.get("/api/v1/admin/stats/overview", headers=verified_headers).status_code == 200

    user_id = intranet.get("/api/v1/auth/me", headers=verified_headers).json()["user_id"]
    reset = intranet.post(f"/api/v1/admin/users/{user_id}/reset-mfa", headers=verified_headers)
    assert reset.status_code == 200
    assert intranet.get("/api/v1/admin/stats/overview", headers=verified_headers).status_code == 403


def test_ldap_user_is_provisioned_without_replacing_local_auth(platform_clients):
    _, intranet, _, intranet_app = platform_clients

    class FakeDirectory:
        settings = SimpleNamespace(ldap_default_role="read_only")

        @staticmethod
        def authenticate(username: str, password: str):
            if username == "directory.reader" and password == "DirectoryPassword@1":
                return DirectoryIdentity(username=username, display_name="目录只读用户")
            return None

    intranet_app.state.auth.directory = FakeDirectory()
    login = intranet.post(
        "/api/v1/auth/login",
        json={"username": "directory.reader", "password": "DirectoryPassword@1"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = intranet.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["auth_source"] == "ldap"
    assert me.json()["role"] == "read_only"
    assert intranet.get("/api/v1/stats", headers=headers).status_code == 200

    # A directory with the same username cannot bypass a local account password.
    assert intranet.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "DirectoryPassword@1"},
    ).status_code == 401


def test_llm_provider_settings_are_encrypted_isolated_and_testable(platform_clients):
    internet, intranet, internet_app, _ = platform_clients
    internet_headers = auth_headers(internet)
    intranet_headers = auth_headers(intranet)
    payload = {
        "name": "互联网 OpenAI 兼容服务", "provider_type": "openai_compatible",
        "base_url": "https://llm.example.test/v1", "api_key": "secret-api-key",
        "selected_model": "model-a", "enabled": True, "is_default": True,
    }
    created = internet.post("/api/v1/admin/llm/providers", json=payload, headers=internet_headers)
    assert created.status_code == 201, created.text
    provider_id = created.json()["provider_id"]
    assert created.json()["has_api_key"] is True
    assert "api_key" not in created.json()
    assert intranet.get("/api/v1/admin/llm/providers", headers=intranet_headers).json() == []

    with internet_app.state.database.session() as session:
        stored = session.get(LlmProvider, provider_id)
        assert b"secret-api-key" not in stored.api_key_encrypted

    async def fake_models(_provider):
        return ["model-a", "model-b"]

    async def fake_test(_provider, model=None):
        return {"status": "success", "model": model or "model-a", "latency_ms": 12.5, "message": "连接成功", "models": []}

    internet_app.state.llm_gateway.fetch_models = fake_models
    internet_app.state.llm_gateway.test_connection = fake_test
    models = internet.post(f"/api/v1/admin/llm/providers/{provider_id}/models", headers=internet_headers)
    assert models.status_code == 200 and models.json()["models"] == ["model-a", "model-b"]
    tested = internet.post(f"/api/v1/admin/llm/providers/{provider_id}/test", headers=internet_headers)
    assert tested.status_code == 200 and tested.json()["status"] == "success"

    async def fake_chat(_provider, model, _prompt, **_kwargs):
        return f"使用 {model} 形成的真实研判"

    internet_app.state.llm_gateway.chat = fake_chat
    analysis = internet.post(
        "/api/v1/ai/analyze-event",
        json={
            "title": "测试事件", "country": "巴西", "disease": "登革热", "cases": 10,
            "deaths": 1, "level": "yellow", "source": "WHO", "published_at": "2026-08-18T00:00:00Z",
            "confidence": .9,
        },
        headers=internet_headers,
    )
    assert analysis.status_code == 200
    assert analysis.json()["analysis"] == "使用 model-a 形成的真实研判"

    local = intranet.post(
        "/api/v1/admin/llm/providers",
        json={"name": "内网 Ollama", "provider_type": "ollama", "base_url": "http://127.0.0.1:11434", "selected_model": "qwen3"},
        headers=intranet_headers,
    )
    assert local.status_code == 201
    assert local.json()["provider_id"] != provider_id


def test_llm_defaults_source_references_and_no_provider_behavior(platform_clients):
    internet, intranet, _, _ = platform_clients
    internet_headers = auth_headers(internet)
    intranet_headers = auth_headers(intranet)

    no_provider = intranet.post(
        "/api/v1/ai/analyze-event",
        json={
            "title": "Test event", "country": "Testland", "disease": "Test disease",
            "cases": 1, "deaths": 0, "level": "blue", "source": "Test source",
            "published_at": "2026-08-18T00:00:00Z", "confidence": 0.8,
        },
        headers=intranet_headers,
    )
    assert no_provider.status_code == 409

    first = internet.post(
        "/api/v1/admin/llm/providers",
        json={
            "name": "First provider", "provider_type": "openai_compatible",
            "base_url": "https://first-llm.example.test/v1", "api_key": "first-key",
            "selected_model": "model-a", "enabled": True, "is_default": True,
        },
        headers=internet_headers,
    )
    second = internet.post(
        "/api/v1/admin/llm/providers",
        json={
            "name": "Second provider", "provider_type": "openai_compatible",
            "base_url": "https://second-llm.example.test/v1", "api_key": "second-key",
            "selected_model": "model-b", "enabled": True, "is_default": True,
        },
        headers=internet_headers,
    )
    assert first.status_code == 201 and second.status_code == 201
    providers = internet.get("/api/v1/admin/llm/providers", headers=internet_headers).json()
    defaults = [item for item in providers if item["is_default"]]
    assert len(defaults) == 1 and defaults[0]["provider_id"] == second.json()["provider_id"]

    source = internet.post(
        "/api/v1/sources",
        json={
            "source_id": "provider-reference-source", "name": "Provider reference source",
            "adapter_type": "rss", "url": "https://feeds.example.test/reference.xml",
            "parser_mode": "hybrid", "llm_provider_id": second.json()["provider_id"],
            "llm_model": "model-b", "frequency_seconds": 600,
        },
        headers=internet_headers,
    )
    assert source.status_code == 201, source.text
    blocked = internet.delete(
        f"/api/v1/admin/llm/providers/{second.json()['provider_id']}", headers=internet_headers,
    )
    assert blocked.status_code == 409

    reset = internet.patch(
        "/api/v1/sources/provider-reference-source",
        json={"parser_mode": "builtin"},
        headers=internet_headers,
    )
    assert reset.status_code == 200
    assert reset.json()["llm_provider_id"] is None and reset.json()["llm_model"] is None
    deleted = internet.delete(
        f"/api/v1/admin/llm/providers/{second.json()['provider_id']}", headers=internet_headers,
    )
    assert deleted.status_code == 200

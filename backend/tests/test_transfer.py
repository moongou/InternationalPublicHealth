from __future__ import annotations

import json

import pytest
from gmssl import sm2

from app.transfer import PackageIntegrityError, TransferCryptoConfig, TransferPackageCodec
from tests.conftest import auth_headers


def test_aes_package_roundtrip_tamper_detection_and_chunks():
    codec = TransferPackageCodec(b"a sufficiently long portable development key")
    payload = {"disease_events": [{"id": "E1", "title": "测试事件"}], "alerts": []}
    package = codec.pack(payload, package_id="PKG-TEST-1")
    metadata, restored = codec.unpack(package)
    assert metadata["package_id"] == "PKG-TEST-1"
    assert metadata["encryption"] == "AES-256-GCM"
    assert restored == payload
    chunks = codec.chunks(package, chunk_size=37)
    assert codec.reassemble(list(reversed(chunks))) == package
    envelope = json.loads(package)
    envelope["ciphertext"] = envelope["ciphertext"][:-2] + "AA"
    with pytest.raises(PackageIntegrityError):
        codec.unpack(json.dumps(envelope).encode())


def test_sm4_sm2_sm3_package_roundtrip():
    private_key = "1".zfill(64)
    generator = sm2.CryptSM2(public_key="", private_key=private_key)
    public_key = generator._kg(int(private_key, 16), generator.ecc_table["g"])
    config = TransferCryptoConfig(
        encryption="SM4-CBC", symmetric_key=b"0123456789abcdef",
        sm2_private_key=private_key, sm2_public_key=public_key,
    )
    codec = TransferPackageCodec(config)
    package = codec.pack({"alerts": [{"id": "A1"}]})
    metadata, restored = codec.unpack(package)
    assert metadata["signature"] == "SM2-SM3"
    assert restored["alerts"][0]["id"] == "A1"


def test_file_transfer_is_received_idempotently(platform_clients):
    internet, intranet, internet_app, _ = platform_clients
    internet_headers = auth_headers(internet)
    intranet_headers = auth_headers(intranet)
    response = internet.post(
        "/api/v1/transfer/tasks", json={"channel": "file", "data_type": "full"}, headers=internet_headers,
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["status"] == "completed"
    package_path = internet_app.state.settings.transfer_root / "outbound" / f"GPH_{task['package_id']}.gpack"
    assert package_path.is_file()
    files = {"file": (package_path.name, package_path.read_bytes(), "application/vnd.gph.package+json")}
    imported = intranet.post("/api/v1/transfer/receiver/upload", files=files, headers=intranet_headers)
    assert imported.status_code == 200, imported.text
    assert imported.json()["status"] == "imported"
    duplicate = intranet.post("/api/v1/transfer/receiver/upload", files=files, headers=intranet_headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"


def test_api_polling_outbox_download(platform_clients):
    internet, _, _, _ = platform_clients
    headers = auth_headers(internet)
    created = internet.post(
        "/api/v1/transfer/tasks", json={"channel": "api_polling", "data_type": "incremental"}, headers=headers,
    )
    assert created.status_code == 201
    package_id = created.json()["package_id"]
    machine_headers = {"X-API-Key": "test-transfer-api-key-with-32-characters"}
    assert internet.get("/api/v1/transfer/outbox", headers=headers).status_code == 401
    listing = internet.get("/api/v1/transfer/outbox", headers=machine_headers).json()
    assert package_id in {item["package_id"] for item in listing}
    download = internet.get(f"/api/v1/transfer/outbox/{package_id}", headers=machine_headers)
    assert download.status_code == 200
    assert download.content.startswith(b"{")


def test_intranet_api_polling_is_rejected_when_disabled(platform_clients):
    _, intranet, _, _ = platform_clients
    response = intranet.post(
        "/api/v1/transfer/receiver/poll-api", headers=auth_headers(intranet),
    )
    assert response.status_code == 409

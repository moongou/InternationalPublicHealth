from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from gmssl import func, sm2, sm4

from .config import Settings


class PackageIntegrityError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


@dataclass(frozen=True)
class TransferCryptoConfig:
    encryption: str
    symmetric_key: bytes
    sm2_private_key: str = ""
    sm2_public_key: str = ""
    sm2_recipient_private_key: str = ""
    sm2_recipient_public_key: str = ""
    sm2_signing_private_key: str = ""
    sm2_signing_public_key: str = ""
    ed25519_private_key: bytes | None = None
    ed25519_public_key: bytes | None = None

    @classmethod
    def development(cls, seed: bytes, encryption: str = "AES-256-GCM") -> "TransferCryptoConfig":
        symmetric = hashlib.sha256(seed + b":encryption").digest()
        private = hashlib.sha256(seed + b":signature").digest()
        public = Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes_raw()
        return cls(encryption, symmetric, ed25519_private_key=private, ed25519_public_key=public)


def crypto_config_from_settings(settings: Settings) -> TransferCryptoConfig:
    seed = settings.transfer_secret.encode("utf-8")
    if settings.transfer_encryption == "SM4-CBC":
        return TransferCryptoConfig(
            encryption="SM4-CBC",
            symmetric_key=hashlib.sha256(seed + b":sm4").digest()[:16],
            sm2_private_key=settings.sm2_private_key,
            sm2_public_key=settings.sm2_public_key,
            sm2_recipient_private_key=settings.sm2_recipient_private_key,
            sm2_recipient_public_key=settings.sm2_recipient_public_key,
            sm2_signing_private_key=settings.sm2_signing_private_key,
            sm2_signing_public_key=settings.sm2_signing_public_key,
        )
    return TransferCryptoConfig.development(seed, "AES-256-GCM")


class TransferPackageCodec:
    """Encrypted, signed transfer package shared by sender and receiver.

    Supported production profiles:
    - SM4-CBC + SM2/SM3 (Chinese commercial cryptography)
    - AES-256-GCM + Ed25519
    """

    def __init__(self, config: TransferCryptoConfig | bytes):
        self.config = config if isinstance(config, TransferCryptoConfig) else TransferCryptoConfig.development(config)
        if self.config.encryption not in {"SM4-CBC", "AES-256-GCM"}:
            raise ValueError("encryption 必须是 SM4-CBC 或 AES-256-GCM")
        expected = 16 if self.config.encryption == "SM4-CBC" else 32
        if len(self.config.symmetric_key) < expected:
            raise ValueError(f"{self.config.encryption} 密钥长度不足")

    def pack(self, payload: dict[str, Any], data_type: str = "incremental", package_id: str | None = None) -> bytes:
        if data_type not in {"full", "incremental"}:
            raise ValueError("data_type 必须是 full 或 incremental")
        serialized = _canonical(payload)
        compressed = gzip.compress(serialized, compresslevel=6, mtime=0)
        checksum = hashlib.sha256(compressed).hexdigest()
        ciphertext, encryption_meta = self._encrypt(compressed)
        metadata = {
            "package_id": package_id or str(uuid.uuid4()),
            "schema_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_type": data_type,
            "checksum": checksum,
            "encryption": self.config.encryption,
            "signature": "SM2-SM3" if self.config.encryption == "SM4-CBC" else "Ed25519",
            "compression": "gzip",
            "source": "internet",
            "destination": "intranet",
            **encryption_meta,
        }
        signature = self._sign(_canonical(metadata) + ciphertext)
        return _canonical({"metadata": metadata, "signature": _b64(signature), "ciphertext": _b64(ciphertext)})

    def unpack(self, package: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            envelope = json.loads(package)
            metadata = envelope["metadata"]
            ciphertext = _unb64(envelope["ciphertext"])
            signature = _unb64(envelope["signature"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise PackageIntegrityError("数据包结构无效") from exc
        if metadata.get("destination") != "intranet" or metadata.get("source") != "internet":
            raise PackageIntegrityError("数据包源或目标不符合单向摆渡策略")
        if metadata.get("encryption") != self.config.encryption:
            raise PackageIntegrityError("数据包加密配置不匹配")
        self._verify(_canonical(metadata) + ciphertext, signature)
        compressed = self._decrypt(ciphertext, metadata)
        if not secrets.compare_digest(hashlib.sha256(compressed).hexdigest(), metadata["checksum"]):
            raise PackageIntegrityError("数据包校验和不一致")
        try:
            return metadata, json.loads(gzip.decompress(compressed))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackageIntegrityError("数据包解压或 JSON 校验失败") from exc

    def _encrypt(self, value: bytes) -> tuple[bytes, dict[str, str]]:
        if self.config.encryption == "AES-256-GCM":
            nonce = secrets.token_bytes(12)
            encrypted = AESGCM(self.config.symmetric_key[:32]).encrypt(nonce, value, b"global-health-transfer-v1")
            return encrypted, {"nonce": _b64(nonce)}
        recipient_public = self.config.sm2_recipient_public_key or self.config.sm2_public_key
        if not recipient_public:
            raise RuntimeError("发送端缺少内网 SM2 加密公钥")
        package_key = secrets.token_bytes(16)
        wrapped_key = sm2.CryptSM2(public_key=recipient_public, private_key="").encrypt(package_key)
        iv = secrets.token_bytes(16)
        cipher = sm4.CryptSM4()
        cipher.set_key(package_key, sm4.SM4_ENCRYPT)
        return bytes(cipher.crypt_cbc(iv, value)), {"iv": _b64(iv), "wrapped_key": _b64(wrapped_key)}

    def _decrypt(self, value: bytes, metadata: dict[str, Any]) -> bytes:
        try:
            if self.config.encryption == "AES-256-GCM":
                return AESGCM(self.config.symmetric_key[:32]).decrypt(
                    _unb64(metadata["nonce"]), value, b"global-health-transfer-v1"
                )
            recipient_private = self.config.sm2_recipient_private_key or self.config.sm2_private_key
            if not recipient_private:
                raise RuntimeError("接收端缺少内网 SM2 解密私钥")
            recipient_public = self.config.sm2_recipient_public_key or self.config.sm2_public_key
            package_key = sm2.CryptSM2(public_key=recipient_public, private_key=recipient_private).decrypt(_unb64(metadata["wrapped_key"]))
            cipher = sm4.CryptSM4()
            cipher.set_key(package_key, sm4.SM4_DECRYPT)
            return bytes(cipher.crypt_cbc(_unb64(metadata["iv"]), value))
        except Exception as exc:
            raise PackageIntegrityError("数据包解密失败") from exc

    def _sign(self, value: bytes) -> bytes:
        if self.config.encryption == "SM4-CBC":
            signing_private = self.config.sm2_signing_private_key or self.config.sm2_private_key
            signing_public = self.config.sm2_signing_public_key or self.config.sm2_public_key
            if not signing_private:
                raise RuntimeError("发送端缺少 SM2 签名私钥")
            signer = sm2.CryptSM2(public_key=signing_public, private_key=signing_private)
            signature_hex = signer.sign_with_sm3(value, func.random_hex(signer.para_len))
            return bytes.fromhex(signature_hex)
        if not self.config.ed25519_private_key:
            raise RuntimeError("发送端缺少 Ed25519 私钥")
        return Ed25519PrivateKey.from_private_bytes(self.config.ed25519_private_key).sign(value)

    def _verify(self, value: bytes, signature: bytes) -> None:
        try:
            if self.config.encryption == "SM4-CBC":
                signing_public = self.config.sm2_signing_public_key or self.config.sm2_public_key
                if not signing_public:
                    raise RuntimeError("接收端缺少互联网 SM2 验签公钥")
                verifier = sm2.CryptSM2(public_key=signing_public, private_key="")
                if not verifier.verify_with_sm3(signature.hex(), value):
                    raise PackageIntegrityError("SM2/SM3 数字签名校验失败")
                return
            if not self.config.ed25519_public_key:
                raise RuntimeError("接收端缺少 Ed25519 公钥")
            Ed25519PublicKey.from_public_bytes(self.config.ed25519_public_key).verify(signature, value)
        except PackageIntegrityError:
            raise
        except Exception as exc:
            raise PackageIntegrityError("数据包数字签名校验失败") from exc

    @staticmethod
    def chunks(package: bytes, chunk_size: int = 1024 * 1024) -> list[dict[str, Any]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        count = max(1, (len(package) + chunk_size - 1) // chunk_size)
        package_checksum = hashlib.sha256(package).hexdigest()
        return [
            {
                "index": index,
                "count": count,
                "package_checksum": package_checksum,
                "checksum": hashlib.sha256(part).hexdigest(),
                "data": part,
            }
            for index in range(count)
            for part in [package[index * chunk_size : (index + 1) * chunk_size]]
        ]

    @staticmethod
    def reassemble(chunks: list[dict[str, Any]]) -> bytes:
        if not chunks:
            raise PackageIntegrityError("缺少数据包分片")
        ordered = sorted(chunks, key=lambda item: item["index"])
        count = ordered[0]["count"]
        if len(ordered) != count or [item["index"] for item in ordered] != list(range(count)):
            raise PackageIntegrityError("数据包分片不完整")
        expected_package = ordered[0]["package_checksum"]
        for item in ordered:
            if item["count"] != count or item["package_checksum"] != expected_package:
                raise PackageIntegrityError("数据包分片元数据不一致")
            if hashlib.sha256(item["data"]).hexdigest() != item["checksum"]:
                raise PackageIntegrityError(f"数据包分片 {item['index']} 校验失败")
        package = b"".join(item["data"] for item in ordered)
        if hashlib.sha256(package).hexdigest() != expected_package:
            raise PackageIntegrityError("重组数据包校验失败")
        return package


class FileTransferChannel:
    def __init__(self, outbound: Path):
        self.outbound = outbound
        self.outbound.mkdir(parents=True, exist_ok=True)

    def send(self, package_id: str, package: bytes) -> Path:
        target = self.outbound / f"GPH_{package_id}.gpack"
        temporary = target.with_suffix(".part")
        with temporary.open("wb") as handle:
            handle.write(package)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return target

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings, settings as default_settings


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("密码长度至少为 10 位")
    if not all((any(char.isupper() for char in password), any(char.islower() for char in password), any(char.isdigit() for char in password), any(not char.isalnum() for char in password))):
        raise ValueError("密码必须同时包含大写字母、小写字母、数字和特殊字符")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, encoded: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("ascii"))
    except (ValueError, TypeError):
        return False


class FieldCipher:
    """Authenticated encryption for intranet PII fields.

    FIELD_ENCRYPTION_KEY accepts URL-safe base64 for a 32-byte key. Development
    derives an isolated key from SECRET_KEY; production settings reject that path.
    """

    def __init__(self, config: Settings):
        if config.field_encryption_key:
            padded = config.field_encryption_key + "=" * (-len(config.field_encryption_key) % 4)
            key = base64.urlsafe_b64decode(padded)
        else:
            key = hashlib.sha256(f"{config.deployment_mode}:{config.secret_key}".encode()).digest()
        if len(key) != 32:
            raise RuntimeError("FIELD_ENCRYPTION_KEY 解码后必须为 32 字节")
        self._aes = AESGCM(key)
        self._index_key = hashlib.sha256(key + b":index").digest()

    def encrypt_text(self, value: str, *, context: str) -> bytes:
        nonce = secrets.token_bytes(12)
        payload = self._aes.encrypt(nonce, value.encode("utf-8"), context.encode("utf-8"))
        return nonce + payload

    def decrypt_text(self, value: bytes, *, context: str) -> str:
        if len(value) < 29:
            raise ValueError("密文字段格式无效")
        return self._aes.decrypt(value[:12], value[12:], context.encode("utf-8")).decode("utf-8")

    def encrypt_json(self, value: dict[str, Any], *, context: str) -> bytes:
        return self.encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), context=context)

    def decrypt_json(self, value: bytes, *, context: str) -> dict[str, Any]:
        return json.loads(self.decrypt_text(value, context=context))

    def blind_index(self, value: str) -> str:
        normalized = value.strip().upper().encode("utf-8")
        return hmac.new(self._index_key, normalized, hashlib.sha256).hexdigest()


TokenType = Literal["access", "refresh"]


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class TokenService:
    def __init__(self, config: Settings):
        self.config = config
        self.audience = f"global-health-{config.deployment_mode}"

    def _encode(self, subject: str, role: str, token_type: TokenType, expires: timedelta, mfa: bool = False) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": subject,
                "role": role,
                "type": token_type,
                "platform": self.config.deployment_mode,
                "mfa": mfa,
                "aud": self.audience,
                "iat": now,
                "nbf": now,
                "exp": now + expires,
                "jti": secrets.token_urlsafe(18),
            },
            self.config.secret_key,
            algorithm="HS256",
        )

    def issue(self, subject: str, role: str, mfa: bool = False) -> TokenPair:
        access_seconds = self.config.access_token_minutes * 60
        return TokenPair(
            access_token=self._encode(subject, role, "access", timedelta(seconds=access_seconds), mfa),
            refresh_token=self._encode(subject, role, "refresh", timedelta(days=self.config.refresh_token_days), mfa),
            expires_in=access_seconds,
        )

    def decode(self, token: str, expected_type: TokenType = "access") -> dict[str, Any]:
        payload = jwt.decode(
            token,
            self.config.secret_key,
            algorithms=["HS256"],
            audience=self.audience,
            options={"require": ["sub", "role", "type", "platform", "exp", "iat", "jti"]},
        )
        if payload["type"] != expected_type or payload["platform"] != self.config.deployment_mode:
            raise jwt.InvalidTokenError("令牌类型或平台不匹配")
        return payload


# Compatibility functions for legacy imports while endpoints migrate to TokenService.
def create_access_token(subject: str, role: str, expires_in: int | None = None) -> str:
    service = TokenService(default_settings)
    if expires_in is None:
        return service.issue(subject, role).access_token
    return service._encode(subject, role, "access", timedelta(seconds=expires_in))


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return TokenService(default_settings).decode(token)
    except jwt.PyJWTError:
        return None

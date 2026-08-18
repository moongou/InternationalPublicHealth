from __future__ import annotations

import base64
import secrets


def token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def field_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


values = {
    "INTERNET_DB_PASSWORD": token(24), "INTRANET_DB_PASSWORD": token(24),
    "INTERNET_REDIS_PASSWORD": token(24), "INTRANET_REDIS_PASSWORD": token(24),
    "TRANSFER_QUEUE_PASSWORD": token(24), "INTERNET_SECRET_KEY": token(48),
    "INTRANET_SECRET_KEY": token(48), "INTERNET_FIELD_KEY": field_key(),
    "INTRANET_FIELD_KEY": field_key(), "INTERNET_ADMIN_PASSWORD": token(18),
    "INTRANET_ADMIN_PASSWORD": token(18), "TRANSFER_SECRET": token(48),
    "TRANSFER_API_KEY": token(40),
    "TRANSFER_ENCRYPTION": "AES-256-GCM",
}
for key, value in values.items():
    print(f"{key}={value}")

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


def _paths(value: str) -> tuple[Path, ...]:
    return tuple(Path(item.strip()) for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    deployment_mode: str
    database_url: str
    cors_origins: tuple[str, ...]
    api_prefix: str = "/api/v1"
    environment: str = "development"
    secret_key: str = ""
    field_encryption_key: str = ""
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    bootstrap_admin_password: str = ""
    seed_demo_data: bool = True
    transfer_encryption: str = "AES-256-GCM"
    transfer_secret: str = ""
    transfer_api_key: str = ""
    api_poll_base_url: str = ""
    enable_api_polling: bool = False
    sm2_private_key: str = ""
    sm2_public_key: str = ""
    sm2_recipient_private_key: str = ""
    sm2_recipient_public_key: str = ""
    sm2_signing_private_key: str = ""
    sm2_signing_public_key: str = ""
    enable_scheduler: bool = False
    message_queue_url: str = ""
    enable_receiver: bool = False
    enable_maintenance: bool = False
    require_admin_mfa: bool = False
    auth_mode: str = "local"
    ldap_server_url: str = ""
    ldap_base_dn: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_filter: str = "(sAMAccountName={username})"
    ldap_default_role: str = "read_only"
    redis_url: str = ""
    cache_ttl_seconds: int = 30
    transfer_root: Path = PROJECT_ROOT / "runtime" / "transfer"
    inbound_root: Path = PROJECT_ROOT / "runtime" / "inbound"
    backup_root: Path = PROJECT_ROOT / "runtime" / "backups"
    raw_data_root: Path = PROJECT_ROOT / "runtime" / "raw"
    passenger_inbound_roots: tuple[Path, ...] = (PROJECT_ROOT / "runtime" / "passenger_inbound",)
    log_root: Path = PROJECT_ROOT / "runtime" / "logs"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate(self) -> None:
        if self.deployment_mode not in {"internet", "intranet"}:
            raise RuntimeError("DEPLOYMENT_MODE 必须是 internet 或 intranet")
        if self.auth_mode not in {"local", "local+ldap"}:
            raise RuntimeError("AUTH_MODE 必须是 local 或 local+ldap")
        if self.auth_mode == "local+ldap":
            if self.deployment_mode != "intranet":
                raise RuntimeError("LDAP/AD 认证仅允许在内网端启用")
            if not self.ldap_server_url or not self.ldap_base_dn or not self.ldap_bind_dn or not self.ldap_bind_password:
                raise RuntimeError("LDAP/AD 认证必须配置服务器、搜索基准和只读绑定账号")
            if self.ldap_default_role not in {"system_admin", "data_analyst", "port_operator", "auditor", "read_only"}:
                raise RuntimeError("LDAP_DEFAULT_ROLE 不是有效角色")
        if self.is_production:
            if len(self.secret_key) < 32 or self.secret_key == "development-only-secret-change-me":
                raise RuntimeError("生产环境 SECRET_KEY 必须至少 32 字符且不可使用开发默认值")
            if not self.field_encryption_key:
                raise RuntimeError("生产环境必须配置 FIELD_ENCRYPTION_KEY")
            if not self.bootstrap_admin_password:
                raise RuntimeError("生产环境必须配置 BOOTSTRAP_ADMIN_PASSWORD")
            if len(self.transfer_secret) < 32 or self.transfer_secret == "development-transfer-secret-change-me":
                raise RuntimeError("生产环境 TRANSFER_SECRET 必须至少 32 字符")
            if len(self.transfer_api_key) < 24:
                raise RuntimeError("生产环境 TRANSFER_API_KEY 必须至少 24 字符")
            if self.enable_api_polling and (not self.api_poll_base_url.startswith("https://") or len(self.transfer_api_key) < 24):
                raise RuntimeError("生产 API 轮询必须配置 HTTPS 白名单网关地址和至少 24 字符的 TRANSFER_API_KEY")
            if self.transfer_encryption == "SM4-CBC":
                if self.deployment_mode == "internet" and (not self.sm2_recipient_public_key or not self.sm2_signing_private_key):
                    raise RuntimeError("互联网端 SM4-CBC 必须配置内网加密公钥和互联网签名私钥")
                if self.deployment_mode == "intranet" and (not self.sm2_recipient_private_key or not self.sm2_signing_public_key):
                    raise RuntimeError("内网端 SM4-CBC 必须配置内网解密私钥和互联网验签公钥")


def load_settings(mode: str | None = None) -> Settings:
    deployment_mode = mode or os.getenv("DEPLOYMENT_MODE", "internet")
    environment = os.getenv("APP_ENV", "development")
    default_db = PROJECT_ROOT / "runtime" / f"{deployment_mode}.db"
    default_origin = "http://localhost:5173" if deployment_mode == "internet" else "http://localhost:5174"
    settings = Settings(
        app_name=(
            "全球公共卫生互联网监测平台"
            if deployment_mode == "internet"
            else "口岸公共卫生内网预警平台"
        ),
        deployment_mode=deployment_mode,
        database_url=os.getenv(
            f"{deployment_mode.upper()}_DATABASE_URL",
            os.getenv("DATABASE_URL", f"sqlite:///{default_db.as_posix()}"),
        ),
        cors_origins=_origins(os.getenv("CORS_ORIGINS", default_origin)),
        environment=environment,
        secret_key=os.getenv("SECRET_KEY", "development-only-secret-change-me"),
        field_encryption_key=os.getenv("FIELD_ENCRYPTION_KEY", ""),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "30")),
        refresh_token_days=int(os.getenv("REFRESH_TOKEN_DAYS", "7")),
        bootstrap_admin_password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "LocalAdmin@2026" if environment != "production" else ""),
        seed_demo_data=os.getenv("SEED_DEMO_DATA", "true" if environment != "production" else "false").lower() == "true",
        transfer_encryption=os.getenv("TRANSFER_ENCRYPTION", "AES-256-GCM"),
        transfer_secret=os.getenv("TRANSFER_SECRET", "development-transfer-secret-change-me" if environment != "production" else ""),
        transfer_api_key=os.getenv("TRANSFER_API_KEY", "development-transfer-api-key" if environment != "production" else ""),
        api_poll_base_url=os.getenv("API_POLL_BASE_URL", ""),
        enable_api_polling=os.getenv("ENABLE_API_POLLING", "false").lower() == "true",
        sm2_private_key=os.getenv("SM2_PRIVATE_KEY", ""),
        sm2_public_key=os.getenv("SM2_PUBLIC_KEY", ""),
        sm2_recipient_private_key=os.getenv("SM2_RECIPIENT_PRIVATE_KEY", ""),
        sm2_recipient_public_key=os.getenv("SM2_RECIPIENT_PUBLIC_KEY", ""),
        sm2_signing_private_key=os.getenv("SM2_SIGNING_PRIVATE_KEY", ""),
        sm2_signing_public_key=os.getenv("SM2_SIGNING_PUBLIC_KEY", ""),
        enable_scheduler=os.getenv("ENABLE_SCHEDULER", "true" if os.getenv("APP_ENV") == "production" and deployment_mode == "internet" else "false").lower() == "true",
        message_queue_url=os.getenv("MESSAGE_QUEUE_URL", "amqp://guest:guest@localhost:5672/%2F"),
        enable_receiver=os.getenv("ENABLE_RECEIVER", "true" if environment == "production" and deployment_mode == "intranet" else "false").lower() == "true",
        enable_maintenance=os.getenv("ENABLE_MAINTENANCE", "true" if environment == "production" else "false").lower() == "true",
        require_admin_mfa=os.getenv("REQUIRE_ADMIN_MFA", "true" if environment == "production" and deployment_mode == "intranet" else "false").lower() == "true",
        auth_mode=os.getenv("AUTH_MODE", "local"),
        ldap_server_url=os.getenv("LDAP_SERVER_URL", ""),
        ldap_base_dn=os.getenv("LDAP_BASE_DN", ""),
        ldap_bind_dn=os.getenv("LDAP_BIND_DN", ""),
        ldap_bind_password=os.getenv("LDAP_BIND_PASSWORD", ""),
        ldap_user_filter=os.getenv("LDAP_USER_FILTER", "(sAMAccountName={username})"),
        ldap_default_role=os.getenv("LDAP_DEFAULT_ROLE", "read_only"),
        redis_url=os.getenv("REDIS_URL", ""),
        cache_ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "30")),
        transfer_root=Path(os.getenv("TRANSFER_ROOT", str(PROJECT_ROOT / "runtime" / "transfer"))),
        inbound_root=Path(os.getenv("INBOUND_ROOT", str(PROJECT_ROOT / "runtime" / "inbound"))),
        backup_root=Path(os.getenv("BACKUP_ROOT", str(PROJECT_ROOT / "runtime" / "backups"))),
        raw_data_root=Path(os.getenv("RAW_DATA_ROOT", str(PROJECT_ROOT / "runtime" / "raw"))),
        passenger_inbound_roots=_paths(os.getenv("PASSENGER_INBOUND_ROOTS", str(PROJECT_ROOT / "runtime" / "passenger_inbound"))),
        log_root=Path(os.getenv("LOG_ROOT", str(PROJECT_ROOT / "runtime" / "logs"))),
    )
    settings.validate()
    return settings


# Compatibility for pure domain modules. Runtime applications use load_settings(mode)
# explicitly so internet and intranet processes cannot silently share a mode.
settings = load_settings()

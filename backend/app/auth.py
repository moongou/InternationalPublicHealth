from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from typing import Annotated

import jwt
import pyotp
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, User
from .config import Settings
from .directory_auth import LdapAuthenticator
from .security import FieldCipher, TokenPair, TokenService, hash_password, verify_password


ROLES = {"system_admin", "data_analyst", "port_operator", "auditor", "read_only"}
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str
    mfa: bool


class AuthService:
    MAX_FAILED_ATTEMPTS = 5
    LOCK_MINUTES = 15

    def __init__(self, tokens: TokenService, cipher: FieldCipher, directory: LdapAuthenticator):
        self.tokens = tokens
        self.cipher = cipher
        self.directory = directory

    def authenticate(self, session: Session, username: str, password: str, ip_address: str, otp: str | None = None) -> tuple[User, TokenPair]:
        user = session.scalar(select(User).where(User.username == username))
        now = datetime.now(timezone.utc)
        if user and user.locked_until:
            locked_until = user.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                raise HTTPException(status.HTTP_423_LOCKED, "账号已锁定，请稍后重试")
            user.locked_until = None
            user.failed_attempts = 0

        valid = bool(
            user and user.status == "active" and user.auth_source == "local"
            and verify_password(password, user.password_hash)
        )
        if not valid and (not user or user.auth_source == "ldap"):
            try:
                identity = self.directory.authenticate(username, password)
            except Exception:
                identity = None
            if identity and not user:
                user = User(
                    username=identity.username,
                    display_name=identity.display_name,
                    password_hash=hash_password("Aa1!" + secrets.token_urlsafe(48)),
                    role=self.directory.settings.ldap_default_role,
                    auth_source="ldap",
                    status="active",
                )
                session.add(user)
                session.flush()
            valid = bool(identity and user and user.status == "active" and user.auth_source == "ldap")
        if not valid:
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= self.MAX_FAILED_ATTEMPTS:
                    user.locked_until = now + timedelta(minutes=self.LOCK_MINUTES)
                session.add(
                    AuditLog(
                        log_type="security", level="warning", actor=username, actor_role=user.role,
                        ip_address=ip_address, action="用户登录", detail="认证失败", result="failed",
                    )
                )
                session.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")

        mfa_verified = False
        if user.mfa_enabled:
            if not user.mfa_secret_encrypted:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "账号多因素配置损坏")
            secret = self.cipher.decrypt_text(user.mfa_secret_encrypted, context=f"user:{user.user_id}:mfa")
            if not otp or not pyotp.TOTP(secret).verify(otp, valid_window=1):
                user.failed_attempts += 1
                if user.failed_attempts >= self.MAX_FAILED_ATTEMPTS:
                    user.locked_until = now + timedelta(minutes=self.LOCK_MINUTES)
                session.add(
                    AuditLog(
                        log_type="security", level="warning", actor=username, actor_role=user.role,
                        ip_address=ip_address, action="用户登录", detail="动态验证码认证失败", result="failed",
                    )
                )
                session.commit()
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "需要有效的动态验证码")
            mfa_verified = True

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = now
        session.add(
            AuditLog(
                log_type="security", actor=user.username, actor_role=user.role,
                ip_address=ip_address, action="用户登录", detail="认证成功", result="success",
            )
        )
        session.commit()
        return user, self.tokens.issue(user.user_id, user.role, mfa_verified)


def get_session(request: Request):
    yield from request.app.state.database.dependency()


def get_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Principal:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "缺少访问令牌")
    try:
        payload = request.app.state.tokens.decode(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "访问令牌无效或已过期") from exc
    user = session.get(User, payload["sub"])
    if not user or user.status != "active" or user.role != payload["role"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户已禁用或权限已变更")
    return Principal(user.user_id, user.username, user.role, bool(payload.get("mfa")) and user.mfa_enabled)


def require_roles(*allowed: str, require_mfa: bool = False):
    invalid = set(allowed) - ROLES
    if invalid:
        raise ValueError(f"未知角色: {sorted(invalid)}")

    def dependency(request: Request, principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "当前角色无权执行此操作")
        if require_mfa and request.app.state.settings.require_admin_mfa and not principal.mfa:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "该操作要求管理员完成双因素认证")
        return principal

    return dependency

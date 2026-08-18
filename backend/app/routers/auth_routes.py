from __future__ import annotations

import jwt
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth import Principal, get_principal, get_session
from ..models import User
from ..schemas import LoginRequest, MfaEnableRequest, RefreshRequest


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, session: Session = Depends(get_session)) -> dict:
    ip = request.client.host if request.client else "unknown"
    user, pair = request.app.state.auth.authenticate(session, body.username, body.password, ip, body.otp)
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
        "expires_in": pair.expires_in,
        "user": {"user_id": user.user_id, "username": user.username, "display_name": user.display_name, "role": user.role},
    }


@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request, session: Session = Depends(get_session)) -> dict:
    try:
        payload = request.app.state.tokens.decode(body.refresh_token, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "刷新令牌无效或已过期") from exc
    user = session.get(User, payload["sub"])
    if not user or user.status != "active" or user.role != payload["role"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户已禁用或权限已变更")
    pair = request.app.state.tokens.issue(user.user_id, user.role, bool(payload.get("mfa")) and user.mfa_enabled)
    return {"access_token": pair.access_token, "refresh_token": pair.refresh_token, "token_type": "bearer", "expires_in": pair.expires_in}


@router.get("/me")
def me(principal: Principal = Depends(get_principal), session: Session = Depends(get_session)) -> dict:
    user = session.get(User, principal.user_id)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "auth_source": user.auth_source,
        "status": user.status,
        "last_login": user.last_login,
        "mfa_enabled": user.mfa_enabled,
        "mfa_verified": principal.mfa,
    }


@router.post("/mfa/setup")
def setup_mfa(request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)) -> dict:
    user = session.get(User, principal.user_id)
    if user.mfa_enabled:
        raise HTTPException(409, "双因素认证已启用；如需重新绑定，请由另一名系统管理员重置")
    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = request.app.state.field_cipher.encrypt_text(secret, context=f"user:{user.user_id}:mfa")
    session.flush()
    return {
        "secret": secret,
        "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=request.app.state.settings.app_name),
    }


@router.post("/mfa/enable")
def enable_mfa(body: MfaEnableRequest, request: Request, principal: Principal = Depends(get_principal), session: Session = Depends(get_session)) -> dict:
    user = session.get(User, principal.user_id)
    if not user.mfa_secret_encrypted:
        raise HTTPException(409, "请先初始化双因素认证")
    secret = request.app.state.field_cipher.decrypt_text(user.mfa_secret_encrypted, context=f"user:{user.user_id}:mfa")
    if not pyotp.TOTP(secret).verify(body.code, valid_window=1):
        raise HTTPException(422, "动态验证码错误")
    user.mfa_enabled = True
    session.flush()
    return {"status": "enabled"}

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..llm import LlmProviderError, validate_provider_url
from ..models import ApiRequestMetric, Alert, AuditLog, BackupRecord, DiseaseEvent, EventSource, LlmProvider, Passenger, ReceivedPackage, RuleExecutionLog, TransferTask, User
from ..schemas import BackupCreate, BackupRestore, LlmProviderCreate, LlmProviderUpdate, PasswordReset, UserCreate, UserUpdate
from ..security import hash_password


router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles("system_admin", require_mfa=True)
audit_access = require_roles("auditor")


def _user(item: User) -> dict[str, Any]:
    return {
        "user_id": item.user_id, "username": item.username, "display_name": item.display_name,
        "role": item.role, "status": item.status, "failed_attempts": item.failed_attempts,
        "mfa_enabled": item.mfa_enabled, "auth_source": item.auth_source,
        "locked_until": item.locked_until.isoformat() if item.locked_until else None,
        "last_login": item.last_login.isoformat() if item.last_login else None,
        "created_at": item.created_at.isoformat(),
    }


def _backup(item: BackupRecord) -> dict[str, Any]:
    return {
        "backup_id": item.backup_id, "type": item.backup_type, "status": item.status,
        "size": item.size, "checksum": item.checksum, "created_at": item.created_at.isoformat(),
        "retention_until": item.retention_until.isoformat() if item.retention_until else None,
        "verified_at": item.verified_at.isoformat() if item.verified_at else None,
    }


def _llm_provider(item: LlmProvider) -> dict[str, Any]:
    return {
        "provider_id": item.provider_id, "name": item.name, "provider_type": item.provider_type,
        "base_url": item.base_url, "has_api_key": bool(item.api_key_encrypted),
        "selected_model": item.selected_model, "available_models": item.available_models or [],
        "config_json": item.config_json or {}, "enabled": item.enabled, "is_default": item.is_default,
        "last_test_status": item.last_test_status, "last_test_message": item.last_test_message,
        "last_tested_at": item.last_tested_at.isoformat() if item.last_tested_at else None,
        "created_at": item.created_at.isoformat(), "updated_at": item.updated_at.isoformat(),
    }


def _set_default_provider(session: Session, selected: LlmProvider) -> None:
    if selected.is_default:
        for item in session.scalars(select(LlmProvider).where(LlmProvider.provider_id != selected.provider_id)).all():
            item.is_default = False


@router.get("/stats/overview")
def overview(
    hours: int = Query(24, ge=1, le=24 * 90),
    _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, Any]:
    transfer_total = session.scalar(select(func.count()).select_from(TransferTask)) or 0
    transfer_ok = session.scalar(select(func.count()).select_from(TransferTask).where(TransferTask.status == "completed")) or 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    durations = list(session.scalars(select(ApiRequestMetric.duration_ms).where(ApiRequestMetric.created_at >= cutoff)).all())
    sorted_durations = sorted(durations)
    p95_index = max(0, min(len(sorted_durations) - 1, int(len(sorted_durations) * 0.95))) if sorted_durations else 0
    return {
        "data_records": session.scalar(select(func.count()).select_from(DiseaseEvent)) or 0,
        "transfer_success_rate": round(transfer_ok / transfer_total * 100, 2) if transfer_total else 100.0,
        "active_alerts": session.scalar(select(func.count()).select_from(Alert).where(Alert.status == "active")) or 0,
        "active_users": session.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0,
        "passengers": session.scalar(select(func.count()).select_from(Passenger)) or 0,
        "received_packages": session.scalar(select(func.count()).select_from(ReceivedPackage)) or 0,
        "rule_executions_24h": session.scalar(
            select(func.count()).select_from(RuleExecutionLog).where(RuleExecutionLog.executed_at >= cutoff)
        ) or 0,
        "transfer_bytes": session.scalar(select(func.coalesce(func.sum(TransferTask.size), 0)).where(TransferTask.status == "completed")) or 0,
        "user_operations_24h": session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= cutoff, AuditLog.log_type == "operation")) or 0,
        "api_requests_24h": len(durations),
        "api_errors_24h": session.scalar(select(func.count()).select_from(ApiRequestMetric).where(ApiRequestMetric.created_at >= cutoff, ApiRequestMetric.status_code >= 500)) or 0,
        "avg_response_ms": round(sum(durations) / len(durations), 2) if durations else 0,
        "p95_response_ms": round(sorted_durations[p95_index], 2) if sorted_durations else 0,
        "window_hours": hours,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/logs")
def logs(
    type: str | None = None, level: str | None = None, actor: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    _: Principal = Depends(audit_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    statement = select(AuditLog)
    count = select(func.count()).select_from(AuditLog)
    conditions = []
    if type: conditions.append(AuditLog.log_type == type)
    if level: conditions.append(AuditLog.level == level)
    if actor: conditions.append(AuditLog.actor.ilike(f"%{actor}%"))
    if start: conditions.append(AuditLog.created_at >= start)
    if end: conditions.append(AuditLog.created_at <= end)
    for condition in conditions:
        statement = statement.where(condition)
        count = count.where(condition)
    items = session.scalars(statement.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [
            {"id": item.log_id, "type": item.log_type, "level": item.level, "user": item.actor,
             "role": item.actor_role, "ip": item.ip_address, "action": item.action,
             "resource": item.resource, "detail": item.detail, "result": item.result,
             "request_id": item.request_id, "timestamp": item.created_at.isoformat()}
            for item in items
        ],
        "total": session.scalar(count) or 0, "page": page, "page_size": page_size,
    }


@router.get("/users")
def users(_: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_user(item) for item in session.scalars(select(User).order_by(User.created_at)).all()]


@router.get("/llm/providers")
def llm_providers(_: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_llm_provider(item) for item in session.scalars(select(LlmProvider).order_by(LlmProvider.created_at)).all()]


@router.post("/llm/providers", status_code=status.HTTP_201_CREATED)
def create_llm_provider(
    body: LlmProviderCreate, request: Request, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        base_url = validate_provider_url(body.base_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    item = LlmProvider(
        name=body.name, provider_type=body.provider_type, base_url=base_url,
        selected_model=body.selected_model, config_json=body.config_json,
        enabled=body.enabled, is_default=body.is_default,
    )
    session.add(item)
    session.flush()
    if body.api_key:
        item.api_key_encrypted = request.app.state.field_cipher.encrypt_text(
            body.api_key, context=f"llm-provider:{item.provider_id}:api-key",
        )
    _set_default_provider(session, item)
    session.flush()
    return _llm_provider(item)


@router.patch("/llm/providers/{provider_id}")
def update_llm_provider(
    provider_id: str, body: LlmProviderUpdate, request: Request,
    _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(LlmProvider, provider_id)
    if not item:
        raise HTTPException(404, "大语言模型供应商不存在")
    values = body.model_dump(exclude_none=True, exclude={"api_key"})
    if "base_url" in values:
        try:
            values["base_url"] = validate_provider_url(values["base_url"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    for key, value in values.items():
        setattr(item, key, value)
    if body.api_key:
        item.api_key_encrypted = request.app.state.field_cipher.encrypt_text(
            body.api_key, context=f"llm-provider:{item.provider_id}:api-key",
        )
    _set_default_provider(session, item)
    session.flush()
    return _llm_provider(item)


@router.delete("/llm/providers/{provider_id}")
def delete_llm_provider(
    provider_id: str, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, str]:
    item = session.get(LlmProvider, provider_id)
    if not item:
        raise HTTPException(404, "大语言模型供应商不存在")
    referenced = any(
        (source.config_json or {}).get("llm_provider_id") == provider_id
        for source in session.scalars(select(EventSource)).all()
    )
    if referenced:
        raise HTTPException(409, "该供应商仍被信息源使用，请先调整信息源配置")
    session.delete(item)
    return {"status": "deleted", "provider_id": provider_id}


@router.post("/llm/providers/{provider_id}/models")
async def discover_llm_models(
    provider_id: str, request: Request, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(LlmProvider, provider_id)
    if not item:
        raise HTTPException(404, "大语言模型供应商不存在")
    try:
        models = await request.app.state.llm_gateway.fetch_models(item)
    except LlmProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    item.available_models = models
    if not item.selected_model and models:
        item.selected_model = models[0]
    session.flush()
    return {"provider_id": provider_id, "models": models, "selected_model": item.selected_model}


@router.post("/llm/providers/{provider_id}/test")
async def test_llm_provider(
    provider_id: str, request: Request, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(LlmProvider, provider_id)
    if not item:
        raise HTTPException(404, "大语言模型供应商不存在")
    try:
        result = await request.app.state.llm_gateway.test_connection(item)
    except LlmProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    if result.get("models"):
        item.available_models = result["models"]
    item.last_test_status = "success"
    item.last_test_message = str(result["message"])[:500]
    item.last_tested_at = datetime.now(timezone.utc)
    session.flush()
    return result


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, _: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> dict[str, Any]:
    item = User(username=body.username, display_name=body.display_name, password_hash=hash_password(body.password), role=body.role)
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "用户名已存在") from exc
    return _user(item)


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, _: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> dict[str, Any]:
    item = session.get(User, user_id)
    if not item: raise HTTPException(404, "用户不存在")
    for key, value in body.model_dump(exclude_none=True).items(): setattr(item, key, value)
    session.flush()
    return _user(item)


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, body: PasswordReset, _: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> dict[str, str]:
    item = session.get(User, user_id)
    if not item: raise HTTPException(404, "用户不存在")
    if item.auth_source != "local": raise HTTPException(409, "目录用户密码必须在 LDAP/AD 中重置")
    item.password_hash = hash_password(body.password)
    item.failed_attempts = 0
    item.locked_until = None
    return {"status": "password_reset"}


@router.post("/users/{user_id}/reset-mfa")
def reset_user_mfa(user_id: str, _: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> dict[str, str]:
    item = session.get(User, user_id)
    if not item: raise HTTPException(404, "用户不存在")
    item.mfa_secret_encrypted = None
    item.mfa_enabled = False
    return {"status": "mfa_reset"}


@router.delete("/users/{user_id}")
def disable_user(user_id: str, principal: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> dict[str, str]:
    if user_id == principal.user_id: raise HTTPException(409, "不能停用当前登录用户")
    item = session.get(User, user_id)
    if not item: raise HTTPException(404, "用户不存在")
    item.status = "disabled"
    return {"status": "disabled"}


@router.get("/backups")
def backups(_: Principal = Depends(admin_only), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_backup(item) for item in session.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc())).all()]


@router.post("/backups", status_code=status.HTTP_201_CREATED)
def create_backup(
    _body: BackupCreate, request: Request, principal: Principal = Depends(admin_only),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _backup(request.app.state.backups.create(session, principal.user_id))


@router.get("/backups/{backup_id}/download")
def download_backup(
    backup_id: str, request: Request, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
):
    item = session.get(BackupRecord, backup_id)
    if not item: raise HTTPException(404, "备份不存在")
    path = Path(item.path).resolve()
    root = request.app.state.settings.backup_root.resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404, "备份文件不存在")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.get("/backups/{backup_id}/assets/download")
def download_backup_assets(
    backup_id: str, request: Request, _: Principal = Depends(admin_only), session: Session = Depends(get_session),
):
    item = session.get(BackupRecord, backup_id)
    if not item: raise HTTPException(404, "备份不存在")
    database_path = Path(item.path).resolve()
    path = database_path.with_suffix(database_path.suffix + ".assets.tar.gz")
    root = request.app.state.settings.backup_root.resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404, "备份资源归档不存在")
    return FileResponse(path, filename=path.name, media_type="application/gzip")


@router.delete("/backups/{backup_id}")
def delete_backup(
    backup_id: str, confirmation: str, request: Request,
    _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, str]:
    if confirmation != backup_id: raise HTTPException(400, "删除确认码必须与备份编号一致")
    item = session.get(BackupRecord, backup_id)
    if not item: raise HTTPException(404, "备份不存在")
    path = Path(item.path).resolve()
    root = request.app.state.settings.backup_root.resolve()
    if root not in path.parents: raise HTTPException(400, "备份文件路径越界")
    for candidate in (path, path.with_suffix(path.suffix + ".assets.tar.gz")):
        if candidate.is_file():
            candidate.unlink()
    session.delete(item)
    return {"status": "deleted", "backup_id": backup_id}


@router.post("/backups/{backup_id}/restore", status_code=status.HTTP_202_ACCEPTED)
def restore_backup(
    backup_id: str, body: BackupRestore, request: Request,
    _: Principal = Depends(admin_only), session: Session = Depends(get_session),
) -> dict[str, str]:
    if body.confirmation != backup_id: raise HTTPException(400, "恢复确认码必须与备份编号一致")
    item = session.get(BackupRecord, backup_id)
    if not item: raise HTTPException(404, "备份不存在")
    request.app.state.backups.restore(session, item)
    return {"status": "restored", "backup_id": backup_id}

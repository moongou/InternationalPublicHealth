from __future__ import annotations

import asyncio
import hmac
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import Principal, get_session, require_roles
from ..llm import validate_provider_url
from ..models import EventSource, LlmProvider, SourceRun, TransferTask
from ..risk_service import RiskCalculationService
from ..schemas import SourceCreate, SourceRunRequest, SourceUpdate, TransferTaskCreate


router = APIRouter(tags=["internet"])
analyst_access = require_roles("system_admin", "data_analyst")
read_access = require_roles("system_admin", "data_analyst", "auditor", "read_only")


def transfer_api_access(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = request.app.state.settings.transfer_api_key
    if not expected or not x_api_key or not hmac.compare_digest(expected, x_api_key):
        raise HTTPException(401, "摆渡 API 密钥无效")


def _task(item: TransferTask) -> dict[str, Any]:
    return {
        "task_id": item.task_id, "package_id": item.package_id, "channel": item.channel,
        "data_type": item.data_type, "status": item.status, "records": item.records,
        "size": item.size, "progress": item.progress, "error": item.error,
        "created_at": item.created_at.isoformat(), "completed_at": item.completed_at.isoformat() if item.completed_at else None,
    }


SOURCE_CONFIG_FIELDS = {"schedule_type", "schedule_timezone", "cron_expression", "parser_mode", "llm_provider_id", "llm_model", "prompt_template"}


def _validate_source_config(item: EventSource, session: Session) -> None:
    try:
        item.url = validate_provider_url(item.url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    config = item.config_json or {}
    try:
        ZoneInfo(str(config.get("schedule_timezone", "Asia/Shanghai")))
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "周期计划时区无效") from exc
    if config.get("schedule_type", "interval") == "cron":
        try:
            CronTrigger.from_crontab(
                str(config.get("cron_expression", "")),
                timezone=str(config.get("schedule_timezone", "Asia/Shanghai")),
            )
        except ValueError as exc:
            raise HTTPException(422, f"Cron 表达式无效: {exc}") from exc
    parser_mode = config.get("parser_mode", "builtin")
    if item.adapter_type == "web_document" and parser_mode == "builtin":
        raise HTTPException(422, "网页文档信息源必须选择大语言模型或混合解析")
    if parser_mode in {"llm", "hybrid"}:
        provider = session.get(LlmProvider, config.get("llm_provider_id"))
        if not provider or not provider.enabled:
            raise HTTPException(422, "请选择已启用的大语言模型供应商")
        if not (config.get("llm_model") or provider.selected_model):
            raise HTTPException(422, "请选择用于信息采集的大语言模型")


def _source(item: EventSource, latest: SourceRun | None, request: Request) -> dict[str, Any]:
    config = item.config_json or {}
    job = request.app.state.scheduler.scheduler.get_job(f"collector-{item.source_id}")
    next_run = getattr(job, "next_run_time", None) if job else None
    return {
        "id": item.source_id, "name": item.name, "adapter_type": item.adapter_type,
        "status": "disabled" if not item.enabled else latest.status if latest else "never_run",
        "url": item.url, "frequency_seconds": item.frequency_seconds, "enabled": item.enabled,
        "schedule_type": config.get("schedule_type", "interval"),
        "schedule_timezone": config.get("schedule_timezone", "Asia/Shanghai"),
        "cron_expression": config.get("cron_expression"), "parser_mode": config.get("parser_mode", "builtin"),
        "llm_provider_id": config.get("llm_provider_id"), "llm_model": config.get("llm_model"),
        "prompt_template": config.get("prompt_template"),
        "last_run": latest.finished_at.isoformat() if latest and latest.finished_at else None,
        "next_run": next_run.isoformat() if next_run else None,
        "records": latest.records_created if latest else 0, "error": latest.error if latest else None,
    }


@router.get("/sources/status")
def source_status(request: Request, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    items = session.scalars(select(EventSource).order_by(EventSource.name)).all()
    return [
        _source(
            item,
            session.scalar(select(SourceRun).where(SourceRun.source == item.source_id).order_by(SourceRun.started_at.desc()).limit(1)),
            request,
        )
        for item in items
    ]


@router.get("/sources/llm-providers")
def source_llm_providers(_: Principal = Depends(analyst_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {"provider_id": item.provider_id, "name": item.name, "provider_type": item.provider_type,
         "selected_model": item.selected_model, "available_models": item.available_models or []}
        for item in session.scalars(select(LlmProvider).where(LlmProvider.enabled.is_(True)).order_by(LlmProvider.name)).all()
    ]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
def create_source(
    body: SourceCreate, request: Request, _: Principal = Depends(analyst_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    config = {key: value for key, value in body.model_dump().items() if key in SOURCE_CONFIG_FIELDS and value is not None}
    item = EventSource(
        source_id=body.source_id, name=body.name, adapter_type=body.adapter_type,
        url=body.url, frequency_seconds=body.frequency_seconds, enabled=body.enabled,
        config_json=config,
    )
    _validate_source_config(item, session)
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "信息源编号已存在") from exc
    request.app.state.scheduler.configure(item)
    return _source(item, None, request)


@router.patch("/sources/{source_id}")
def update_source(
    source_id: str, body: SourceUpdate, request: Request,
    _: Principal = Depends(analyst_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(EventSource, source_id)
    if not item: raise HTTPException(404, "数据源不存在")
    values = body.model_dump(exclude_none=True)
    config = dict(item.config_json or {})
    for key in SOURCE_CONFIG_FIELDS:
        if key in values:
            config[key] = values.pop(key)
    for key, value in values.items():
        setattr(item, key, value)
    item.config_json = config
    if config.get("parser_mode", "builtin") == "builtin":
        for key in ("llm_provider_id", "llm_model"):
            config.pop(key, None)
        item.config_json = config
    _validate_source_config(item, session)
    session.flush()
    request.app.state.scheduler.configure(item)
    latest = session.scalar(select(SourceRun).where(SourceRun.source == source_id).order_by(SourceRun.started_at.desc()).limit(1))
    return _source(item, latest, request)


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: str, request: Request, _: Principal = Depends(analyst_access), session: Session = Depends(get_session),
) -> dict[str, str]:
    item = session.get(EventSource, source_id)
    if not item:
        raise HTTPException(404, "数据源不存在")
    request.app.state.scheduler.remove(source_id)
    session.delete(item)
    return {"status": "deleted", "source_id": source_id}


@router.post("/sources/run", status_code=status.HTTP_202_ACCEPTED)
async def run_sources(body: SourceRunRequest, request: Request, _: Principal = Depends(analyst_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    sources = body.sources
    if not sources:
        sources = list(session.scalars(select(EventSource.source_id).where(EventSource.enabled.is_(True))).all())
    job = request.app.state.collection_jobs.create(sources)
    asyncio.create_task(request.app.state.collectors.run_job(job))
    return {"job_id": job.job_id, "status": "started"}


@router.get("/sources/run/{job_id}")
def run_snapshot(job_id: str, request: Request, _: Principal = Depends(analyst_access)) -> dict[str, Any]:
    job = request.app.state.collection_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "采集任务不存在或已过期")
    return job.snapshot()


@router.post("/sources/run/{job_id}/cancel")
def run_cancel(job_id: str, request: Request, _: Principal = Depends(analyst_access)) -> dict[str, Any]:
    if not request.app.state.collection_jobs.cancel(job_id):
        raise HTTPException(404, "采集任务不存在或已结束")
    return {"job_id": job_id, "status": "cancelling"}


@router.post("/risk-scores/recalculate")
def recalculate_risk(_: Principal = Depends(analyst_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    return RiskCalculationService().calculate_all(session)


@router.get("/transfer/tasks")
def transfer_tasks(_: Principal = Depends(read_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_task(item) for item in session.scalars(select(TransferTask).order_by(TransferTask.created_at.desc())).all()]


@router.post("/transfer/tasks", status_code=status.HTTP_201_CREATED)
def create_transfer_task(
    body: TransferTaskCreate, request: Request, principal: Principal = Depends(analyst_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _task(request.app.state.transfer_sender.create_task(session, body.channel, body.data_type, principal.user_id))


@router.get("/transfer/tasks/{task_id}")
def transfer_task(task_id: str, _: Principal = Depends(read_access), session: Session = Depends(get_session)) -> dict[str, Any]:
    item = session.get(TransferTask, task_id)
    if not item: raise HTTPException(404, "摆渡任务不存在")
    return _task(item)


@router.post("/transfer/tasks/{task_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_transfer_task(
    task_id: str, request: Request, principal: Principal = Depends(analyst_access), session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.get(TransferTask, task_id)
    if not item: raise HTTPException(404, "摆渡任务不存在")
    return _task(request.app.state.transfer_sender.retry(session, item, principal.user_id))


@router.get("/transfer/outbox")
def transfer_outbox(_: None = Depends(transfer_api_access), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    items = session.scalars(
        select(TransferTask).where(TransferTask.channel == "api_polling", TransferTask.status == "completed")
        .order_by(TransferTask.completed_at)
    ).all()
    return [{"package_id": item.package_id, "size": item.size, "created_at": item.created_at.isoformat()} for item in items]


@router.get("/transfer/outbox/{package_id}")
def download_outbox_package(
    package_id: str, request: Request, _: None = Depends(transfer_api_access), session: Session = Depends(get_session),
):
    item = session.scalar(select(TransferTask).where(TransferTask.package_id == package_id, TransferTask.channel == "api_polling"))
    if not item or not item.package_path: raise HTTPException(404, "数据包不存在")
    path = Path(item.package_path).resolve()
    root = (request.app.state.settings.transfer_root / "api-outbox").resolve()
    if root not in path.parents or not path.is_file(): raise HTTPException(404, "数据包文件不存在")
    return FileResponse(path, media_type="application/vnd.gph.package+json", filename=path.name)

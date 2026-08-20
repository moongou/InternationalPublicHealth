from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthService
from .backup import BackupService
from .cache import ResponseCache
from .bootstrap import bootstrap_database
from .collectors import CollectorService
from .collectors.jobs import CollectionJobManager
from .collectors.scheduler import CollectorScheduler
from .config import Settings, load_settings
from .database import Database
from .directory_auth import LdapAuthenticator
from .logging_config import configure_file_logging
from .llm import LlmGateway
from .models import ApiRequestMetric, AuditLog
from .maintenance import MaintenanceScheduler
from .passenger_files import PassengerFileScanner
from .routers import admin, ai, auth_routes, intranet, internet, monitoring, rules
from .security import FieldCipher, TokenService
from .transfer_service import ReceiverScheduler, TransferReceiverService, TransferSenderService


def _base_app(settings: Settings) -> FastAPI:
    configure_file_logging(settings)
    database = Database(settings.database_url)
    tokens = TokenService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            bootstrap_database(database, settings)
            # 启动时补建业务索引（对存量表生效，幂等）
            database.ensure_indexes()
            if settings.enable_maintenance:
                app.state.maintenance.start()
            if settings.deployment_mode == "internet":
                collectors = CollectorService(settings, database, llm_gateway=app.state.llm_gateway)
                scheduler = CollectorScheduler(collectors)
                app.state.collectors = collectors
                app.state.scheduler = scheduler
                if settings.enable_scheduler:
                    scheduler.start()
            elif settings.enable_receiver:
                receiver_scheduler = ReceiverScheduler(app.state.transfer_receiver, app.state.passenger_scanner)
                app.state.receiver_scheduler = receiver_scheduler
                receiver_scheduler.start()
            yield
        finally:
            if settings.deployment_mode == "internet" and hasattr(app.state, "scheduler"):
                app.state.scheduler.shutdown()
                await app.state.collectors.close()
            if settings.deployment_mode == "intranet" and hasattr(app.state, "receiver_scheduler"):
                app.state.receiver_scheduler.shutdown()
            if settings.enable_maintenance:
                app.state.maintenance.shutdown()
            app.state.cache.close()
            database.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description=f"{settings.deployment_mode} 独立运行 API",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.tokens = tokens
    app.state.field_cipher = FieldCipher(settings)
    app.state.llm_gateway = LlmGateway(settings, app.state.field_cipher)
    app.state.auth = AuthService(tokens, app.state.field_cipher, LdapAuthenticator(settings))
    app.state.backups = BackupService(settings, database)
    app.state.maintenance = MaintenanceScheduler(app.state.backups, database)
    app.state.cache = ResponseCache(settings)
    app.state.collection_jobs = CollectionJobManager()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-API-Key"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "healthy", "service": settings.app_name,
            "mode": settings.deployment_mode, "time": datetime.now(timezone.utc).isoformat(),
        }

    @app.middleware("http")
    async def security_and_audit(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        response = None
        result = "success"
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                result = "failed"
            return response
        except Exception:
            result = "error"
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            if response is not None:
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Referrer-Policy"] = "no-referrer"
                response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
                if settings.is_production:
                    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            try:
                with database.session() as session:
                    session.add(ApiRequestMetric(
                        path=request.url.path, method=request.method,
                        status_code=response.status_code if response is not None else 500,
                        duration_ms=duration_ms,
                    ))
            except Exception:
                pass
            logging.getLogger("app.access").info(
                "request_completed",
                extra={
                    "request_id": request_id, "method": request.method, "path": request.url.path,
                    "status_code": response.status_code if response is not None else 500,
                    "duration_ms": duration_ms,
                },
            )
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.endswith("/auth/login"):
                actor, role = "anonymous", "unknown"
                authorization = request.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    try:
                        payload = tokens.decode(authorization[7:])
                        actor, role = payload["sub"], payload["role"]
                    except Exception:
                        pass
                try:
                    with database.session() as session:
                        session.add(
                            AuditLog(
                                log_type="operation", actor=actor, actor_role=role,
                                ip_address=request.client.host if request.client else "unknown",
                                action=f"{request.method} {request.url.path}", resource=request.url.path,
                                detail=f"duration_ms={duration_ms}",
                                result=result, request_id=request_id,
                            )
                        )
                except Exception:
                    # Audit storage failure must not leak request bodies or mask the business exception.
                    pass

    prefix = settings.api_prefix
    app.include_router(auth_routes.router, prefix=prefix)
    app.include_router(monitoring.router, prefix=prefix)
    app.include_router(rules.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(ai.router, prefix=prefix)
    return app


def create_internet_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings("internet")
    if config.deployment_mode != "internet":
        raise RuntimeError("互联网应用必须使用 internet 配置")
    app = _base_app(config)
    app.state.transfer_sender = TransferSenderService(config, app.state.database)
    app.include_router(internet.router, prefix=config.api_prefix)
    return app


def create_intranet_app(settings: Settings | None = None) -> FastAPI:
    config = settings or load_settings("intranet")
    if config.deployment_mode != "intranet":
        raise RuntimeError("内网应用必须使用 intranet 配置")
    app = _base_app(config)
    app.state.transfer_receiver = TransferReceiverService(config, app.state.database)
    app.state.passenger_scanner = PassengerFileScanner(config, app.state.database, app.state.field_cipher)
    app.include_router(intranet.router, prefix=config.api_prefix)
    return app

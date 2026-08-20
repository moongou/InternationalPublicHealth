from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    """数据库连接管理层。

    - SQLite（开发）：WAL + busy_timeout + NORMAL 同步，避免高并发锁库
    - PostgreSQL（生产）：连接池 + 定期回收 + 取数超时
    - 提供健康检查、表统计、优化维护能力，供系统管理端调用
    """

    def __init__(self, url: str, pool_size: int = 10, max_overflow: int = 20):
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        connect_args: dict[str, Any] = {}
        engine_kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if self.is_sqlite:
            connect_args = {"check_same_thread": False, "timeout": 30}
            # SQLite 高并发读多写少场景：允许适度排队而非无限堆积连接
            engine_kwargs.update(pool_size=pool_size, max_overflow=max_overflow)
        else:
            connect_args = {"connect_timeout": 10, "application_name": "global-health"}
            engine_kwargs.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_recycle=1800,   # 30 分钟回收，防数据库端断连
                pool_timeout=30,
            )
        self.engine: Engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
        if self.is_sqlite:
            event.listen(self.engine, "connect", self._enable_sqlite_tuning)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    # ------------------------------------------------------------------ SQLite 调优
    @staticmethod
    def _enable_sqlite_tuning(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")          # 读写不互斥
        cursor.execute("PRAGMA synchronous=NORMAL")        # WAL 推荐档位，兼顾安全与性能
        cursor.execute("PRAGMA busy_timeout=5000")         # 写锁等待 5s，替代立即报 locked
        cursor.execute("PRAGMA cache_size=-32000")         # 32MB 页缓存
        cursor.execute("PRAGMA temp_store=MEMORY")         # 临时表/排序走内存
        cursor.close()

    # ------------------------------------------------------------------ 基础能力
    def create_schema(self) -> None:
        from . import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def ensure_indexes(self) -> list[str]:
        """为已有表补充业务索引（create_all 不会给存量表加索引）。

        覆盖内网 50 万旅客表的高频查询路径：
        - 默认排序 entry_time desc
        - 风险等级 + 入境时间组合过滤
        - 国籍、航班号、入境口岸筛选
        返回本次新建的索引名列表。
        """
        index_specs = [
            ("ix_passengers_entry_time", "passengers (entry_time DESC)"),
            ("ix_passengers_level_entry", "passengers (risk_level, entry_time DESC)"),
            ("ix_passengers_nationality", "passengers (nationality)"),
            ("ix_passengers_flight", "passengers (flight_no)"),
            ("ix_passengers_port_entry", "passengers (entry_port, entry_time DESC)"),
            ("ix_request_metrics_created", "api_request_metrics (created_at DESC)"),
            ("ix_audit_logs_actor_time", "audit_logs (actor, created_at DESC)"),
        ]
        created: list[str] = []
        with self.engine.begin() as connection:
            existing = self._existing_indexes(connection)
            for name, definition in index_specs:
                if name in existing:
                    continue
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {definition}"))
                created.append(name)
        return created

    def _existing_indexes(self, connection) -> set[str]:
        if self.is_sqlite:
            rows = connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )).fetchall()
        else:
            rows = connection.execute(text("SELECT indexname FROM pg_indexes")).fetchall()
        return {row[0] for row in rows}

    # ------------------------------------------------------------------ 健康检查与统计
    def health_check(self) -> dict[str, Any]:
        """连接测试：返回延迟毫秒与数据库版本。失败抛异常由调用方转 503。"""
        started = time.perf_counter()
        with self.engine.connect() as connection:
            if self.is_sqlite:
                version = connection.execute(text("SELECT sqlite_version()")).scalar()
                mode = connection.execute(text("PRAGMA journal_mode")).scalar()
            else:
                version = connection.execute(text("SELECT version()")).scalar()
                mode = "postgresql"
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms, "version": str(version), "journal_mode": str(mode)}

    def status(self) -> dict[str, Any]:
        """数据库全量状态：类型、文件大小、连接池、各表行数。"""
        info: dict[str, Any] = {
            "engine": "sqlite" if self.is_sqlite else "postgresql",
            "url_masked": self._masked_url(),
        }
        if self.is_sqlite:
            path = Path(self.url.removeprefix("sqlite:///"))
            wal, shm = path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")
            info["database_path"] = str(path)
            info["size_mb"] = round(path.stat().st_size / 1048576, 2) if path.exists() else 0
            info["wal_size_mb"] = round(wal.stat().st_size / 1048576, 2) if wal.exists() else 0
            info["shm_size_mb"] = round(shm.stat().st_size / 1048576, 2) if shm.exists() else 0
            with self.engine.connect() as connection:
                info["integrity_check"] = connection.execute(text("PRAGMA quick_check")).scalar()
                info["page_count"] = connection.execute(text("PRAGMA page_count")).scalar()
                info["freelist_pages"] = connection.execute(text("PRAGMA freelist_count")).scalar()
        pool = self.engine.pool
        info["pool"] = {
            "size": getattr(pool, "size", lambda: None)(),
            "checked_in": getattr(pool, "checkedin", lambda: None)(),
            "checked_out": getattr(pool, "checkedout", lambda: None)(),
            "overflow": getattr(pool, "overflow", lambda: None)(),
        }
        info["tables"] = self.table_stats()
        return info

    def table_stats(self) -> dict[str, int]:
        """各业务表行数（安全计数，表不存在时跳过）。"""
        result: dict[str, int] = {}
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        with self.engine.connect() as connection:
            for table in sorted(existing):
                if table.startswith("sqlite_") or table.startswith("alembic"):
                    continue
                try:
                    result[table] = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
                except Exception:
                    continue
        return result

    def optimize(self) -> dict[str, Any]:
        """维护操作：更新查询计划统计 + 截断 WAL。大库场景显著稳定查询延迟。"""
        actions: dict[str, Any] = {}
        with self.engine.begin() as connection:
            if self.is_sqlite:
                connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
                actions["wal_checkpoint"] = "truncated"
                connection.execute(text("PRAGMA optimize"))
                actions["optimize"] = "done"
            else:
                connection.execute(text("ANALYZE"))
                actions["analyze"] = "done"
        actions["indexes_ensured"] = self.ensure_indexes()
        return actions

    def _masked_url(self) -> str:
        if self.is_sqlite:
            return self.url
        # postgresql+psycopg://user:***@host:port/db
        if "://" in self.url:
            scheme, rest = self.url.split("://", 1)
            if "@" in rest:
                credentials, hostpart = rest.rsplit("@", 1)
                if ":" in credentials:
                    user = credentials.split(":", 1)[0]
                    return f"{scheme}://{user}:***@{hostpart}"
        return "masked"

    # ------------------------------------------------------------------ 会话管理
    def dependency(self) -> Generator[Session, None, None]:
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

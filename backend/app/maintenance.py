from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete

from .backup import BackupService
from .database import Database
from .models import ApiRequestMetric


class MaintenanceScheduler:
    def __init__(self, backups: BackupService, database: Database):
        self.backups = backups
        self.database = database
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    def start(self) -> None:
        self.scheduler.add_job(
            self._backup, "cron", hour=2, minute=0, id="daily-full-backup",
            max_instances=1, coalesce=True, misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self._prune, "cron", hour=2, minute=30, id="backup-retention",
            max_instances=1, coalesce=True, misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self._prune_metrics, "cron", hour=3, minute=0, id="metric-retention",
            max_instances=1, coalesce=True, misfire_grace_time=3600,
        )
        self.scheduler.start()

    def _backup(self) -> None:
        with self.database.session() as session:
            self.backups.create(session, "scheduler")

    def _prune(self) -> None:
        with self.database.session() as session:
            self.backups.prune_expired(session)

    def _prune_metrics(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=180)
        with self.database.session() as session:
            session.execute(delete(ApiRequestMetric).where(ApiRequestMetric.created_at < cutoff))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

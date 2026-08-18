from __future__ import annotations

import asyncio

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from ..models import EventSource
from .service import CollectorService


class CollectorScheduler:
    def __init__(self, service: CollectorService):
        self.service = service
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        self.reload()
        self.scheduler.start()

    def reload(self) -> None:
        with self.service.database.session() as session:
            configs = session.scalars(select(EventSource)).all()
        desired = {f"collector-{item.source_id}" for item in configs if item.enabled and self.service.supports(item)}
        for job in self.scheduler.get_jobs():
            if job.id.startswith("collector-") and job.id not in desired:
                self.scheduler.remove_job(job.id)
        for item in configs:
            self.configure(item)

    def configure(self, config: EventSource) -> None:
        source_id = config.source_id
        job_id = f"collector-{source_id}"
        if not config.enabled or not self.service.supports(config):
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            return
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        common = {
            "id": job_id, "replace_existing": True, "max_instances": 1,
            "coalesce": True, "misfire_grace_time": 300,
        }
        schedule = config.config_json or {}
        if schedule.get("schedule_type") == "cron":
            trigger = CronTrigger.from_crontab(
                str(schedule.get("cron_expression", "")),
                timezone=str(schedule.get("schedule_timezone", "Asia/Shanghai")),
            )
            self.scheduler.add_job(lambda selected=source_id: asyncio.run(self.service.run(selected)), trigger, **common)
        else:
            self.scheduler.add_job(
                lambda selected=source_id: asyncio.run(self.service.run(selected)),
                "interval", seconds=max(60, config.frequency_seconds), **common,
            )

    def remove(self, source_id: str) -> None:
        job_id = f"collector-{source_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

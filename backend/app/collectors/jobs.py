"""采集任务进度管理。

提供内存态的采集任务（CollectionJob）与每个信息源（SourceProgress）的
实时进度快照，供前端轮询展示采集细节；同时支持手动取消（已入库数据保留）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


class SourceProgress:
    """单个信息源在本次采集任务中的进度。"""

    def __init__(self, source_id: str, name: str = ""):
        self.source_id = source_id
        self.name = name or source_id
        self.status = "queued"  # queued / running / success / failed / cancelled / skipped
        self.stage = "待采集"
        self.message = ""
        self.fetched = 0
        self.created = 0
        self.deduplicated = 0
        self.error: str | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None

    def update(self, stage: str, message: str, counts: dict[str, int] | None = None) -> None:
        self.stage = stage
        self.message = message
        if counts:
            self.fetched = counts.get("fetched", self.fetched)
            self.created = counts.get("created", self.created)
            self.deduplicated = counts.get("deduplicated", self.deduplicated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "fetched": self.fetched,
            "created": self.created,
            "deduplicated": self.deduplicated,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class CollectionJob:
    """一次采集任务的整体状态。"""

    def __init__(self, job_id: str, sources: list[str]):
        self.job_id = job_id
        self.sources = sources
        self.status = "running"  # running / completed / cancelled
        self.cancel_requested = False
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: str | None = None
        self.error: str | None = None
        self.progress: dict[str, SourceProgress] = {sid: SourceProgress(sid) for sid in sources}

    def is_cancelled(self) -> bool:
        return self.cancel_requested

    def snapshot(self) -> dict[str, Any]:
        done_statuses = {"success", "failed", "cancelled", "skipped"}
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total": len(self.sources),
            "done": sum(1 for p in self.progress.values() if p.status in done_statuses),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "sources": [p.to_dict() for p in self.progress.values()],
        }


class CollectionJobManager:
    """内存态采集任务注册表。"""

    def __init__(self) -> None:
        self._jobs: dict[str, CollectionJob] = {}

    def create(self, sources: list[str]) -> CollectionJob:
        job = CollectionJob(uuid.uuid4().hex[:12], sources)
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> CollectionJob | None:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel_requested = True
        return True

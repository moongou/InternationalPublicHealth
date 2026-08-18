from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from .config import Settings
from .database import Database
from .models import BackupRecord


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundle_checksum(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
    return digest.hexdigest()


class BackupService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        settings.backup_root.mkdir(parents=True, exist_ok=True)

    def create(self, session: Session, actor: str) -> BackupRecord:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix = ".sqlite3" if self.settings.database_url.startswith("sqlite") else ".dump"
        path = self.settings.backup_root / f"{self.settings.deployment_mode}_{stamp}{suffix}"
        assets_path = path.with_suffix(path.suffix + ".assets.tar.gz")
        record = BackupRecord(
            backup_type="full", status="running", path=str(path), created_by=actor,
            retention_until=(datetime.now(timezone.utc) + timedelta(days=14)).date(),
        )
        session.add(record)
        session.flush()
        try:
            if self.settings.database_url.startswith("sqlite"):
                source_path = Path(self.settings.database_url.removeprefix("sqlite:///"))
                source = sqlite3.connect(source_path)
                target = sqlite3.connect(path)
                try:
                    source.backup(target)
                finally:
                    target.close()
                    source.close()
            else:
                args, environment = self._postgres_connection()
                subprocess.run(
                    ["pg_dump", "--format=custom", "--file", str(path), *args],
                    check=True, capture_output=True, text=True, timeout=3600, env=environment,
                )
            self._create_assets_archive(assets_path)
            record.size = path.stat().st_size + assets_path.stat().st_size
            record.checksum = bundle_checksum(path, assets_path)
            record.status = "verified"
            record.verified_at = datetime.now(timezone.utc)
        except Exception:
            record.status = "failed"
            raise
        return record

    def restore(self, session: Session, record: BackupRecord) -> None:
        path = Path(record.path).resolve()
        root = self.settings.backup_root.resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("备份文件不在允许目录或不存在")
        assets_path = path.with_suffix(path.suffix + ".assets.tar.gz")
        if not record.checksum or bundle_checksum(path, assets_path) != record.checksum:
            raise ValueError("备份文件完整性校验失败")
        if self.settings.database_url.startswith("sqlite"):
            destination = Path(self.settings.database_url.removeprefix("sqlite:///"))
            snapshot = self.settings.backup_root / f"pre_restore_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.sqlite3"
            shutil.copy2(destination, snapshot)
            self.database.engine.dispose()
            source = sqlite3.connect(path)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        else:
            args, environment = self._postgres_connection()
            subprocess.run(
                ["pg_restore", "--clean", "--if-exists", "--no-owner", *args, str(path)],
                check=True, capture_output=True, text=True, timeout=3600, env=environment,
            )
        if assets_path.is_file():
            self._restore_assets_archive(assets_path)

    def prune_expired(self, session: Session) -> int:
        today = datetime.now(timezone.utc).date()
        expired = session.query(BackupRecord).filter(BackupRecord.retention_until < today).all()
        removed = 0
        for record in expired:
            path = Path(record.path)
            for candidate in (path, path.with_suffix(path.suffix + ".assets.tar.gz")):
                if candidate.is_file() and self.settings.backup_root.resolve() in candidate.resolve().parents:
                    candidate.unlink()
            session.delete(record)
            removed += 1
        return removed

    def _postgres_connection(self) -> tuple[list[str], dict[str, str]]:
        url = self.settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        parsed = urlparse(url)
        args = [
            "--host", parsed.hostname or "localhost",
            "--port", str(parsed.port or 5432),
            "--username", parsed.username or "postgres",
            "--dbname", parsed.path.lstrip("/"),
        ]
        environment = os.environ.copy()
        if parsed.password:
            environment["PGPASSWORD"] = parsed.password
        return args, environment

    def _asset_roots(self) -> list[tuple[str, Path]]:
        roots = [
            ("raw", self.settings.raw_data_root),
            ("transfer", self.settings.transfer_root),
            ("inbound", self.settings.inbound_root),
        ]
        roots.extend((f"passenger_inbound/{index}", root) for index, root in enumerate(self.settings.passenger_inbound_roots))
        return roots

    def _create_assets_archive(self, path: Path) -> None:
        manifest = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "deployment_mode": self.settings.deployment_mode,
            "configuration": {
                "api_prefix": self.settings.api_prefix,
                "auth_mode": self.settings.auth_mode,
                "transfer_encryption": self.settings.transfer_encryption,
                "cache_ttl_seconds": self.settings.cache_ttl_seconds,
            },
            "secrets_included": False,
        }
        with tarfile.open(path, "w:gz") as archive:
            payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            info = tarfile.TarInfo("manifest.json")
            info.size = len(payload)
            info.mtime = int(datetime.now(timezone.utc).timestamp())
            archive.addfile(info, io.BytesIO(payload))
            for prefix, root in self._asset_roots():
                if not root.is_dir() or root.resolve() == self.settings.backup_root.resolve():
                    continue
                for item in root.rglob("*"):
                    if item.is_file():
                        archive.add(item, arcname=f"assets/{prefix}/{item.relative_to(root).as_posix()}", recursive=False)

    def _restore_assets_archive(self, path: Path) -> None:
        roots = dict(self._asset_roots())
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.startswith("assets/"):
                    continue
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 3:
                    raise ValueError("备份资源归档包含不安全路径")
                if relative.parts[1] == "passenger_inbound" and len(relative.parts) >= 4:
                    prefix = "/".join(relative.parts[1:3])
                    tail = relative.parts[3:]
                else:
                    prefix = relative.parts[1]
                    tail = relative.parts[2:]
                target_root = roots.get(prefix)
                if target_root is None:
                    continue
                destination = target_root.joinpath(*tail).resolve()
                if target_root.resolve() not in destination.parents:
                    raise ValueError("备份资源恢复路径越界")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source:
                    with destination.open("wb") as target:
                        shutil.copyfileobj(source, target)

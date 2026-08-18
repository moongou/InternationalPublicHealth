from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError

from .config import Settings
from .database import Database
from .models import AuditLog, Passenger
from .schemas import PassengerCreate
from .security import FieldCipher


def parse_passenger_file(content: bytes, filename: str) -> list[PassengerCreate]:
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("导入文件不得超过 20MB")
    text = content.decode("utf-8-sig")
    suffix = Path(filename).suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        raw_items = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif suffix == ".csv":
        raw_items: list[dict[str, Any]] = []
        for row in csv.DictReader(io.StringIO(text)):
            raw_items.append(
                {
                    "passenger_id": row["passenger_id"],
                    "document_type": row.get("document_type") or "护照",
                    "document_number": row["document_number"],
                    "name": row["name"],
                    "gender": row.get("gender") or None,
                    "birth_date": row.get("birth_date") or None,
                    "nationality": row["nationality"],
                    "travel_history": [
                        {
                            "country": row["travel_country"],
                            "entry_date": row["travel_entry_date"],
                            "exit_date": row["travel_exit_date"],
                        }
                    ] if row.get("travel_country") else [],
                    "transit_countries": [value for value in (row.get("transit_countries") or "").split(";") if value],
                    "entry_port": row["entry_port"],
                    "entry_time": row["entry_time"],
                    "flight_no": row.get("flight_no") or None,
                    "seat_no": row.get("seat_no") or None,
                    "health_declaration": (row.get("health_declaration") or "true").lower() in {"true", "1", "yes", "是"},
                }
            )
    else:
        raise ValueError("仅支持 UTF-8 CSV 或 JSONL")
    return [PassengerCreate.model_validate(item) for item in raw_items]


class PassengerFileScanner:
    def __init__(self, settings: Settings, database: Database, cipher: FieldCipher):
        self.settings = settings
        self.database = database
        self.cipher = cipher
        for root in settings.passenger_inbound_roots:
            root.mkdir(parents=True, exist_ok=True)

    def scan(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for root in self.settings.passenger_inbound_roots:
            for path in sorted(root.glob("PASSENGER_*")):
                if not path.is_file() or path.suffix.lower() not in {".csv", ".jsonl", ".ndjson"}:
                    continue
                results.append(self._process(root, path))
        return results

    def _archive_encrypted(self, root: Path, path: Path, content: bytes, status: str) -> None:
        archive = root / status
        archive.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        encrypted = self.cipher.encrypt_text(
            content.decode("utf-8-sig"), context=f"passenger-import:{path.name}:{stamp}",
        )
        (archive / f"{path.name}.{stamp}.enc").write_bytes(encrypted)
        path.unlink()

    def _process(self, root: Path, path: Path) -> dict[str, Any]:
        content = path.read_bytes()
        imported = 0
        try:
            models = parse_passenger_file(content, path.name)
            from .routers.intranet import _add_passenger

            request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(field_cipher=self.cipher)))
            with self.database.session() as session:
                for model in models:
                    if session.get(Passenger, model.passenger_id):
                        continue
                    _add_passenger(session, request, model)
                    imported += 1
                session.add(AuditLog(
                    log_type="integration", actor="passenger-file-scanner", actor_role="system",
                    ip_address="127.0.0.1", action="旅客文件自动导入", resource=path.name,
                    detail=f"validated={len(models)}, imported={imported}", result="success",
                ))
            self._archive_encrypted(root, path, content, "processed")
            return {"file": path.name, "status": "imported", "records": imported}
        except (UnicodeDecodeError, csv.Error, json.JSONDecodeError, KeyError, ValidationError, ValueError) as exc:
            with self.database.session() as session:
                session.add(AuditLog(
                    log_type="integration", level="warning", actor="passenger-file-scanner", actor_role="system",
                    ip_address="127.0.0.1", action="旅客文件自动导入", resource=path.name,
                    detail=type(exc).__name__, result="failed",
                ))
            self._archive_encrypted(root, path, content, "failed")
            return {"file": path.name, "status": "failed", "error": type(exc).__name__}

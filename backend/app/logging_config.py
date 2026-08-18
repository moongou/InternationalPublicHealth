from __future__ import annotations

import json
import logging
from logging.handlers import TimedRotatingFileHandler

from .config import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_file_logging(settings: Settings) -> None:
    settings.log_root.mkdir(parents=True, exist_ok=True)
    path = (settings.log_root / f"{settings.deployment_mode}.jsonl").resolve()
    root = logging.getLogger()
    if any(getattr(handler, "baseFilename", None) == str(path) for handler in root.handlers):
        return
    handler = TimedRotatingFileHandler(path, when="midnight", interval=1, backupCount=180, encoding="utf-8", utc=True)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)

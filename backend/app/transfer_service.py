from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pika
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .database import Database
from .models import Alert, Country, CountryRisk, CountryRiskHistory, DiseaseEvent, ReceivedPackage, RuleDefinition, TransferLink, TransferTask
from .transfer import FileTransferChannel, PackageIntegrityError, TransferPackageCodec, crypto_config_from_settings


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class TransferSenderService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.codec = TransferPackageCodec(crypto_config_from_settings(settings))

    def create_task(self, session: Session, channel: str, data_type: str, actor: str) -> TransferTask:
        task = TransferTask(channel=channel, data_type=data_type, created_by=actor, status="packaging", progress=5)
        session.add(task)
        session.flush()
        try:
            payload = self.build_payload(session, data_type)
            package = self.codec.pack(payload, data_type=data_type)
            envelope = json.loads(package)
            task.package_id = envelope["metadata"]["package_id"]
            task.records = sum(len(value) for value in payload.values() if isinstance(value, list))
            task.size = len(package)
            task.progress = 45
            path = self._dispatch(channel, task.package_id, package)
            task.package_path = str(path) if path else None
            task.status = "completed"
            task.progress = 100
            task.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)[:2000]
            task.progress = 0
        session.flush()
        return task

    def retry(self, session: Session, task: TransferTask, actor: str) -> TransferTask:
        return self.create_task(session, task.channel, task.data_type, actor)

    def _dispatch(self, channel: str, package_id: str, package: bytes) -> Path | None:
        if channel == "file":
            return FileTransferChannel(self.settings.transfer_root / "outbound").send(package_id, package)
        if channel == "api_polling":
            return FileTransferChannel(self.settings.transfer_root / "api-outbox").send(package_id, package)
        if channel == "message_queue":
            parameters = pika.URLParameters(self.settings.message_queue_url)
            connection = pika.BlockingConnection(parameters)
            try:
                queue = "global_health_transfer"
                channel_obj = connection.channel()
                channel_obj.queue_declare(queue=queue, durable=True)
                channel_obj.basic_publish(
                    exchange="", routing_key=queue, body=package,
                    properties=pika.BasicProperties(delivery_mode=2, content_type="application/vnd.gph.package+json", message_id=package_id),
                )
            finally:
                connection.close()
            return None
        raise ValueError("不支持的摆渡通道")

    @staticmethod
    def build_payload(session: Session, data_type: str) -> dict[str, list[dict[str, Any]]]:
        # Incremental export uses the latest successful transfer completion as watermark.
        watermark = None
        if data_type == "incremental":
            watermark = session.scalar(
                select(TransferTask.completed_at).where(TransferTask.status == "completed")
                .order_by(TransferTask.completed_at.desc()).limit(1)
            )
        event_statement = select(DiseaseEvent)
        history_statement = select(CountryRiskHistory)
        alert_statement = select(Alert)
        if watermark:
            event_statement = event_statement.where(DiseaseEvent.collected_at > watermark)
            history_statement = history_statement.where(CountryRiskHistory.calculated_at > watermark)
            alert_statement = alert_statement.where(Alert.issued_at > watermark)
        countries = session.execute(select(Country, CountryRisk).join(CountryRisk, Country.code == CountryRisk.country_code)).all()
        return {
            "disease_events": [
                {"event_id": e.event_id, "fingerprint": e.fingerprint, "title": e.title, "disease": e.disease,
                 "country": e.country, "country_code": e.country_code, "source": e.source, "source_url": e.source_url,
                 "event_type": e.event_type, "cases": e.cases, "deaths": e.deaths, "latitude": e.latitude,
                 "longitude": e.longitude, "confidence": e.confidence, "level": e.level,
                 "published_at": _iso(e.published_at), "collected_at": _iso(e.collected_at)}
                for e in session.scalars(event_statement).all()
            ],
            "countries": [
                {"code": c.code, "name": c.name, "region": c.region, "population": c.population,
                 "latitude": c.latitude, "longitude": c.longitude, "health_capacity": c.health_capacity,
                 "travel_intensity": c.travel_intensity, "transit_risk": c.transit_risk,
                 "risk_score": r.score, "risk_level": r.level, "factors": r.factors,
                 "model_version": r.model_version, "calculated_at": _iso(r.calculated_at)}
                for c, r in countries
            ],
            "country_risk_history": [
                {"country_code": h.country_code, "score": h.score, "level": h.level, "factors": h.factors,
                 "calculated_at": _iso(h.calculated_at)} for h in session.scalars(history_statement).all()
            ],
            "alerts": [
                {"alert_id": a.alert_id, "country_code": a.country_code, "disease": a.disease, "title": a.title,
                 "score": a.score, "level": a.level, "advice": a.advice, "status": a.status,
                 "issued_at": _iso(a.issued_at), "expires_at": _iso(a.expires_at)}
                for a in session.scalars(alert_statement).all()
            ],
            "transfer_risks": [
                {"link_id": x.link_id, "origin_country_code": x.origin_country_code, "origin": x.origin,
                 "destination": x.destination, "source_coordinates": x.source_coordinates,
                 "target_coordinates": x.target_coordinates, "via": x.via, "risk": x.risk, "volume": x.volume,
                 "updated_at": _iso(x.updated_at)} for x in session.scalars(select(TransferLink)).all()
            ],
            "rules": [
                {"rule_id": r.rule_id, "rule_key": r.rule_key, "name": r.name, "rule_type": r.rule_type,
                 "description": r.description, "condition_json": r.condition_json, "action_json": r.action_json,
                 "priority": r.priority, "version": r.version, "status": r.status,
                 "published_at": _iso(r.published_at)}
                for r in session.scalars(select(RuleDefinition).where(RuleDefinition.status == "published")).all()
            ],
        }


class TransferReceiverService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.codec = TransferPackageCodec(crypto_config_from_settings(settings))

    def process(self, session: Session, package: bytes) -> dict[str, Any]:
        metadata, payload = self.codec.unpack(package)
        package_id = metadata["package_id"]
        existing = session.get(ReceivedPackage, package_id)
        if existing and existing.status == "imported":
            return {"package_id": package_id, "status": "duplicate", "records": existing.records}
        record = existing or ReceivedPackage(
            package_id=package_id, checksum=metadata["checksum"], version=metadata["schema_version"], status="validating"
        )
        session.add(record)
        try:
            records = self._import(session, payload)
            record.status = "imported"
            record.records = records
            record.imported_at = datetime.now(timezone.utc)
            return {"package_id": package_id, "status": "imported", "records": records}
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)[:2000]
            raise

    def scan_directory(self) -> list[dict[str, Any]]:
        inbound = self.settings.inbound_root
        processed = inbound / "processed"
        rejected = inbound / "rejected"
        for directory in (inbound, processed, rejected): directory.mkdir(parents=True, exist_ok=True)
        results = []
        for path in sorted(inbound.glob("*.gpack")):
            try:
                with self.database.session() as session:
                    result = self.process(session, path.read_bytes())
                destination = processed / path.name
                results.append(result)
            except Exception as exc:
                destination = rejected / path.name
                results.append({"path": path.name, "status": "failed", "error": str(exc)})
            os.replace(path, destination)
        return results

    def poll_api(self, base_url: str, api_key: str) -> list[dict[str, Any]]:
        with httpx.Client(base_url=base_url, headers={"X-API-Key": api_key}, timeout=30) as client:
            packages = client.get("/api/v1/transfer/outbox").raise_for_status().json()
            results = []
            for item in packages:
                package = client.get(f"/api/v1/transfer/outbox/{item['package_id']}").raise_for_status().content
                with self.database.session() as session:
                    results.append(self.process(session, package))
            return results

    def consume_queue(self, max_messages: int = 100) -> list[dict[str, Any]]:
        parameters = pika.URLParameters(self.settings.message_queue_url)
        connection = pika.BlockingConnection(parameters)
        results: list[dict[str, Any]] = []
        try:
            channel = connection.channel()
            queue = "global_health_transfer"
            channel.queue_declare(queue=queue, durable=True)
            for _ in range(max_messages):
                method, _properties, body = channel.basic_get(queue=queue, auto_ack=False)
                if method is None:
                    break
                try:
                    with self.database.session() as session:
                        results.append(self.process(session, body))
                    channel.basic_ack(method.delivery_tag)
                except Exception as exc:
                    channel.basic_nack(method.delivery_tag, requeue=False)
                    results.append({"status": "failed", "error": str(exc)})
        finally:
            connection.close()
        return results

    @staticmethod
    def _import(session: Session, payload: dict[str, Any]) -> int:
        required = {"disease_events", "countries", "country_risk_history", "alerts", "transfer_risks", "rules"}
        if not required.issubset(payload):
            raise PackageIntegrityError(f"数据包缺少字段: {sorted(required - set(payload))}")
        records = 0
        for item in payload["countries"]:
            country = session.get(Country, item["code"]) or Country(code=item["code"], name=item["name"], region=item["region"])
            for key in ("name", "region", "population", "latitude", "longitude", "health_capacity", "travel_intensity", "transit_risk"):
                setattr(country, key, item[key])
            session.add(country)
            risk = session.get(CountryRisk, item["code"]) or CountryRisk(country_code=item["code"], score=0, level="blue")
            risk.score=item["risk_score"]; risk.level=item["risk_level"]; risk.factors=item["factors"]; risk.model_version=item["model_version"]; risk.calculated_at=datetime.fromisoformat(item["calculated_at"])
            session.add(risk); records += 1
        session.flush()
        for item in payload["disease_events"]:
            event = session.get(DiseaseEvent, item["event_id"])
            if not event:
                event = DiseaseEvent(event_id=item["event_id"], fingerprint=item["fingerprint"], title=item["title"], disease=item["disease"], country=item["country"], country_code=item["country_code"], source=item["source"], published_at=datetime.fromisoformat(item["published_at"]))
            for key in ("source_url","event_type","cases","deaths","latitude","longitude","confidence","level"):
                setattr(event, key, item.get(key))
            event.collected_at=datetime.fromisoformat(item["collected_at"]); session.add(event); records += 1
        for item in payload["country_risk_history"]:
            exists = session.scalar(select(CountryRiskHistory.history_id).where(CountryRiskHistory.country_code==item["country_code"], CountryRiskHistory.calculated_at==datetime.fromisoformat(item["calculated_at"])))
            if not exists:
                session.add(CountryRiskHistory(country_code=item["country_code"], score=item["score"], level=item["level"], factors=item["factors"], calculated_at=datetime.fromisoformat(item["calculated_at"]))); records += 1
        for item in payload["alerts"]:
            alert = session.get(Alert, item["alert_id"]) or Alert(alert_id=item["alert_id"], country_code=item["country_code"], title=item["title"], score=item["score"], level=item["level"])
            for key in ("disease","title","score","level","advice","status"): setattr(alert,key,item[key])
            alert.issued_at=datetime.fromisoformat(item["issued_at"]); alert.expires_at=datetime.fromisoformat(item["expires_at"]) if item.get("expires_at") else None; session.add(alert); records += 1
        for item in payload["transfer_risks"]:
            link = session.get(TransferLink,item["link_id"]) or TransferLink(link_id=item["link_id"],origin_country_code=item["origin_country_code"],origin=item["origin"])
            for key in ("destination","source_coordinates","target_coordinates","via","risk","volume"): setattr(link,key,item[key])
            link.updated_at=datetime.fromisoformat(item["updated_at"]); session.add(link); records += 1
        for item in payload["rules"]:
            rule = session.get(RuleDefinition,item["rule_id"])
            if not rule:
                session.add(RuleDefinition(**{**item,"published_at":datetime.fromisoformat(item["published_at"]) if item.get("published_at") else None,"created_by":"transfer"})); records += 1
        return records


class ReceiverScheduler:
    def __init__(self, receiver: TransferReceiverService, passenger_scanner=None):
        self.receiver = receiver
        self.passenger_scanner = passenger_scanner
        self.scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        self.scheduler.add_job(self._scan, "interval", seconds=10, id="receiver-file-scan", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._queue, "interval", seconds=10, id="receiver-message-queue", max_instances=1, coalesce=True)
        if self.passenger_scanner:
            self.scheduler.add_job(self._passengers, "interval", seconds=10, id="passenger-file-scan", max_instances=1, coalesce=True)
        if self.receiver.settings.enable_api_polling:
            self.scheduler.add_job(self._api, "interval", seconds=60, id="receiver-api-poll", max_instances=1, coalesce=True)
        self.scheduler.start()

    def _scan(self) -> None:
        try: self.receiver.scan_directory()
        except Exception: pass

    def _queue(self) -> None:
        try: self.receiver.consume_queue()
        except Exception: pass

    def _passengers(self) -> None:
        try: self.passenger_scanner.scan()
        except Exception: pass

    def _api(self) -> None:
        try:
            self.receiver.poll_api(
                self.receiver.settings.api_poll_base_url,
                self.receiver.settings.transfer_api_key,
            )
        except Exception:
            pass

    def shutdown(self) -> None:
        if self.scheduler.running: self.scheduler.shutdown(wait=False)

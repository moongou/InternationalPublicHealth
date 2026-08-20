from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class DiseaseEvent(Base):
    __tablename__ = "disease_events"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_event_fingerprint"),
        Index("ix_event_country_published", "country_code", "published_at"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    disease: Mapped[str] = mapped_column(String(160), nullable=False)
    country: Mapped[str] = mapped_column(String(160), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1200))
    event_type: Mapped[str] = mapped_column(String(80), default="outbreak")
    cases: Mapped[int] = mapped_column(Integer, default=0)
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    level: Mapped[str] = mapped_column(String(16), default="blue", index=True)
    severity: Mapped[float] = mapped_column(Float, default=0)
    transmission: Mapped[float] = mapped_column(Float, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_record_id: Mapped[str | None] = mapped_column(ForeignKey("raw_records.raw_record_id"))


class RawRecord(Base):
    __tablename__ = "raw_records"
    raw_record_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/json")
    storage_path: Mapped[str] = mapped_column(String(1200), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Disease(Base):
    __tablename__ = "diseases"
    disease_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), default="传染病")
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EventSource(Base):
    __tablename__ = "event_sources"
    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(1200), nullable=False)
    frequency_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BootstrapMarker(Base):
    __tablename__ = "bootstrap_markers"
    marker_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Country(Base):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    population: Mapped[int] = mapped_column(Integer, default=0)
    latitude: Mapped[float] = mapped_column(Float, default=0)
    longitude: Mapped[float] = mapped_column(Float, default=0)
    health_capacity: Mapped[float] = mapped_column(Float, default=50)
    travel_intensity: Mapped[float] = mapped_column(Float, default=0)
    transit_risk: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CountryRisk(Base):
    __tablename__ = "country_risk_scores"
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), primary_key=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    factors: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(40), default="risk-v1")
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CountryRiskHistory(Base):
    __tablename__ = "country_risk_history"
    history_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    factors: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TransferLink(Base):
    __tablename__ = "transfer_risks"
    link_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    origin_country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), index=True)
    origin: Mapped[str] = mapped_column(String(160), nullable=False)
    destination: Mapped[str] = mapped_column(String(160), default="中国")
    source_coordinates: Mapped[list[float]] = mapped_column(JSON, default=list)
    target_coordinates: Mapped[list[float]] = mapped_column(JSON, default=list)
    via: Mapped[str] = mapped_column(String(160), default="直达")
    risk: Mapped[float] = mapped_column(Float, default=0)
    volume: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), index=True)
    disease: Mapped[str] = mapped_column(String(160), default="综合风险")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    advice: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleDefinition(Base):
    __tablename__ = "rule_definitions"
    __table_args__ = (UniqueConstraint("rule_key", "version", name="uq_rule_version"),)
    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RuleExecutionLog(Base):
    __tablename__ = "rule_execution_log"
    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rule_definitions.rule_id"), index=True)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    output_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    execution_ms: Mapped[float] = mapped_column(Float, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TransferTask(Base):
    __tablename__ = "transfer_tasks"
    task_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    package_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    records: Mapped[int] = mapped_column(Integer, default=0)
    size: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    package_path: Mapped[str | None] = mapped_column(String(1200))
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReceivedPackage(Base):
    __tablename__ = "received_packages"
    package_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    records: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class Passenger(Base):
    __tablename__ = "passengers"
    passenger_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    document_type: Mapped[str] = mapped_column(String(40), default="护照")
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    contact_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    gender: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str] = mapped_column(String(80), nullable=False)
    travel_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    transit_countries: Mapped[list[str]] = mapped_column(JSON, default=list)
    entry_port: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flight_no: Mapped[str | None] = mapped_column(String(30))
    seat_no: Mapped[str | None] = mapped_column(String(20))
    health_declaration: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="blue", index=True)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    advice: Mapped[list[str]] = mapped_column(JSON, default=list)
    matched_rule_version: Mapped[str] = mapped_column(String(40), default="PAX-001/v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Port(Base):
    __tablename__ = "ports"
    __table_args__ = (
        Index("ix_port_type_risk", "port_type", "risk_level"),
    )

    port_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    port_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default="blue", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    auth_source: Mapped[str] = mapped_column(String(20), default="local")
    status: Mapped[str] = mapped_column(String(20), default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    log_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    log_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(40), default="system")
    ip_address: Mapped[str] = mapped_column(String(64), default="unknown")
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource: Mapped[str] = mapped_column(String(300), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    request_id: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    backup_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    path: Mapped[str] = mapped_column(String(1200), nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    retention_until: Mapped[date | None] = mapped_column(Date)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceRun(Base):
    __tablename__ = "source_runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_deduplicated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiRequestMetric(Base):
    __tablename__ = "api_request_metrics"
    metric_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LlmProvider(Base):
    __tablename__ = "llm_providers"
    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1200), nullable=False)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    selected_model: Mapped[str | None] = mapped_column(String(240))
    available_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    last_test_status: Mapped[str | None] = mapped_column(String(30))
    last_test_message: Mapped[str | None] = mapped_column(String(500))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


RiskLevel = Literal["red", "orange", "yellow", "blue"]


class TravelHistoryItem(BaseModel):
    country: str
    entry_date: date
    exit_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.exit_date < self.entry_date:
            raise ValueError("旅居结束日期不得早于开始日期")
        return self


class ContactInfo(BaseModel):
    phone: str | None = None
    email: str | None = None


class PassengerCreate(BaseModel):
    passenger_id: str
    document_type: str = "护照"
    document_number: str
    name: str
    gender: str | None = None
    birth_date: date | None = None
    nationality: str
    travel_history: list[TravelHistoryItem] = Field(default_factory=list)
    transit_countries: list[str] = Field(default_factory=list)
    entry_port: str
    entry_time: datetime
    flight_no: str | None = None
    seat_no: str | None = None
    health_declaration: bool = True
    contact_info: ContactInfo | None = None

    @field_validator("passenger_id", "document_number", "name", "nationality", "entry_port")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value


class PortAdviceRequest(BaseModel):
    port_name: str
    port_type: Literal["airport", "seaport", "land"] = "airport"
    alert_level: RiskLevel


class RuleCreate(BaseModel):
    name: str
    type: Literal["risk_score", "alert_level", "port_advice", "passenger_match", "trend_change"]
    description: str = ""
    condition_json: dict[str, Any] = Field(default_factory=dict)
    action_json: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    condition_json: dict[str, Any] | None = None
    action_json: dict[str, Any] | None = None
    priority: int | None = None


class RuleTestRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class TransferTaskCreate(BaseModel):
    channel: Literal["file", "message_queue", "api_polling"] = "file"
    data_type: Literal["full", "incremental"] = "incremental"


class LoginRequest(BaseModel):
    username: str
    password: str
    otp: str | None = Field(default=None, pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


class MfaEnableRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


def _strong_password(value: str) -> str:
    if not all((any(char.isupper() for char in value), any(char.islower() for char in value), any(char.isdigit() for char in value), any(not char.isalnum() for char in value))):
        raise ValueError("密码必须同时包含大写字母、小写字母、数字和特殊字符")
    return value


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["system_admin", "data_analyst", "port_operator", "auditor", "read_only"]

    _validate_password = field_validator("password")(_strong_password)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["system_admin", "data_analyst", "port_operator", "auditor", "read_only"] | None = None
    status: Literal["active", "disabled"] | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=128)

    _validate_password = field_validator("password")(_strong_password)


class BackupCreate(BaseModel):
    backup_type: Literal["full"] = "full"


class BackupRestore(BaseModel):
    confirmation: str


class SourceRunRequest(BaseModel):
    sources: list[str] | None = None


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    adapter_type: Literal["rss", "jhu_csv", "owid_csv", "web_document"] | None = None
    url: str | None = Field(default=None, max_length=1200)
    frequency_seconds: int | None = Field(default=None, ge=60, le=604800)
    enabled: bool | None = None
    schedule_type: Literal["interval", "cron"] | None = None
    schedule_timezone: str | None = Field(default=None, max_length=64)
    cron_expression: str | None = Field(default=None, max_length=120)
    parser_mode: Literal["builtin", "llm", "hybrid"] | None = None
    llm_provider_id: str | None = Field(default=None, max_length=64)
    llm_model: str | None = Field(default=None, max_length=240)
    prompt_template: str | None = Field(default=None, max_length=8000)


class SourceCreate(BaseModel):
    source_id: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=160)
    adapter_type: Literal["rss", "jhu_csv", "owid_csv", "web_document"] = "rss"
    url: str = Field(min_length=8, max_length=1200)
    frequency_seconds: int = Field(default=3600, ge=60, le=604800)
    enabled: bool = True
    schedule_type: Literal["interval", "cron"] = "interval"
    schedule_timezone: str = Field(default="Asia/Shanghai", max_length=64)
    cron_expression: str | None = Field(default=None, max_length=120)
    parser_mode: Literal["builtin", "llm", "hybrid"] = "builtin"
    llm_provider_id: str | None = Field(default=None, max_length=64)
    llm_model: str | None = Field(default=None, max_length=240)
    prompt_template: str | None = Field(default=None, max_length=8000)


class LlmProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider_type: Literal["openai", "openai_compatible", "anthropic", "gemini", "ollama"]
    base_url: str = Field(min_length=8, max_length=1200)
    api_key: str | None = Field(default=None, max_length=4000)
    selected_model: str | None = Field(default=None, max_length=240)
    enabled: bool = True
    is_default: bool = False
    config_json: dict[str, Any] = Field(default_factory=dict)


class LlmProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    provider_type: Literal["openai", "openai_compatible", "anthropic", "gemini", "ollama"] | None = None
    base_url: str | None = Field(default=None, min_length=8, max_length=1200)
    api_key: str | None = Field(default=None, max_length=4000)
    selected_model: str | None = Field(default=None, max_length=240)
    enabled: bool | None = None
    is_default: bool | None = None
    config_json: dict[str, Any] | None = None


class AiEventAnalysisRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    country: str = Field(min_length=1, max_length=160)
    disease: str = Field(min_length=1, max_length=160)
    cases: int = Field(default=0, ge=0)
    deaths: int = Field(default=0, ge=0)
    level: RiskLevel
    source: str = Field(min_length=1, max_length=160)
    published_at: datetime
    confidence: float = Field(ge=0, le=1)
    provider_id: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=240)
    focus: str | None = Field(default=None, max_length=1000)

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .timezone import ensure_beijing


def _validate_hhmm(value: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError("daily reminder time must be in HH:MM 24h format") from exc
    return value


def _normalize_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_webhook_url(value: object, *, allow_blank: bool) -> str:
    if value is None:
        if allow_blank:
            return ""
        raise ValueError("Webhook 地址不能为空")

    url = str(value).strip()
    if not url:
        if allow_blank:
            return ""
        raise ValueError("Webhook 地址不能为空")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Webhook 地址必须是有效的 http(s) 地址")

    return url


def _end_must_not_be_before_start(start_at: datetime, end_at: Optional[datetime]) -> None:
    if end_at is None:
        return
    if ensure_beijing(end_at) < ensure_beijing(start_at):
        raise ValueError("End time must be after start time")


class TaskBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    start_at: datetime
    start_all_day: bool = False
    end_at: Optional[datetime] = None
    end_all_day: bool = False
    daily_reminder: bool = False

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be blank")
        return title

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: object) -> Optional[str]:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def _ensure_end_after_start(self) -> "TaskBase":
        _end_must_not_be_before_start(self.start_at, self.end_at)
        return self


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    start_at: Optional[datetime] = None
    start_all_day: Optional[bool] = None
    end_at: Optional[datetime] = None
    end_all_day: Optional[bool] = None
    daily_reminder: Optional[bool] = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be blank")
        return title

    @field_validator("description", mode="before")
    @classmethod
    def _normalize_description(cls, value: object) -> Optional[str]:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def _ensure_end_after_start(self) -> "TaskUpdate":
        if self.start_at is not None:
            _end_must_not_be_before_start(self.start_at, self.end_at)
        return self


class Task(TaskBase):
    id: int
    start_notified: bool
    end_notified: bool
    last_daily_notified: Optional[date] = None
    created_at: datetime
    updated_at: datetime


class Settings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    webhook_url: str = Field("", max_length=500)
    deadline_notice_minutes: int = Field(30, ge=1, le=10080)
    daily_reminder_time: str = Field("09:00")

    @field_validator("daily_reminder_time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return _validate_hhmm(value)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    webhook_url: str = Field("", max_length=500)
    deadline_notice_minutes: int = Field(..., ge=1, le=10080)
    daily_reminder_time: str = Field(...)

    @field_validator("daily_reminder_time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return _validate_hhmm(value)

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, value: str) -> str:
        return _normalize_webhook_url(value, allow_blank=True)


class WebhookTestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    webhook_url: str = Field(..., min_length=1, max_length=500)

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, value: str) -> str:
        return _normalize_webhook_url(value, allow_blank=False)

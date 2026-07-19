from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Dict, List, Mapping

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.types import Scope

from . import database
from .models import Settings, SettingsUpdate, Task, TaskCreate, TaskUpdate, WebhookTestRequest
from .reminder import ReminderService
from .timezone import BEIJING_TZ, ensure_beijing

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "static"


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "no-store"
        return response


reminder_service = ReminderService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    reminder_service.start()
    try:
        yield
    finally:
        reminder_service.stop()


app = FastAPI(title="Feishu Task Reminder", version="0.2.0", lifespan=lifespan)
app.mount("/static", NoCacheStaticFiles(directory=FRONTEND_DIR), name="static")


def _file_response(filename: str) -> FileResponse:
    response = FileResponse(FRONTEND_DIR / filename)
    response.headers["Cache-Control"] = "no-store"
    return response


def _ensure_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return ensure_beijing(value)
    if isinstance(value, str) and value:
        try:
            return ensure_beijing(datetime.fromisoformat(value))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"字段 {field_name} 的时间格式不正确") from exc
    raise HTTPException(status_code=400, detail=f"字段 {field_name} 不能为空")


def _normalize_datetime(dt: datetime, all_day: bool, *, is_end: bool) -> datetime:
    normalized = ensure_beijing(dt)
    if all_day:
        target = dtime(hour=23 if is_end else 0, minute=59 if is_end else 0, tzinfo=BEIJING_TZ)
        return datetime.combine(normalized.date(), target)
    return normalized.replace(second=0, microsecond=0)


def _normalize_description(value: Any) -> str | None:
    if value is None:
        return None
    description = str(value).strip()
    return description or None


def _validate_time_window(start_at: datetime, end_at: datetime | None) -> None:
    if end_at is not None and end_at < start_at:
        raise HTTPException(status_code=400, detail="结束时间不能早于开始时间")


def _prepare_task_payload(data: Mapping[str, Any], *, existing: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    merged = {**(existing or {}), **dict(data)}
    required_fields = ["title", "start_at", "start_all_day"]
    for field in required_fields:
        if merged.get(field) in (None, ""):
            raise HTTPException(status_code=400, detail=f"字段 {field} 不能为空")

    start_all_day = bool(merged.get("start_all_day"))
    start_dt = _normalize_datetime(_ensure_datetime(merged["start_at"], "start_at"), start_all_day, is_end=False)

    end_at_value = merged.get("end_at")
    end_all_day = bool(merged.get("end_all_day"))
    end_dt = None
    if end_at_value:
        end_dt = _normalize_datetime(_ensure_datetime(end_at_value, "end_at"), end_all_day, is_end=True)

    _validate_time_window(start_dt, end_dt)
    return {
        "title": str(merged["title"]).strip(),
        "description": _normalize_description(merged.get("description")),
        "start_at": start_dt.isoformat(),
        "start_all_day": int(start_all_day),
        "end_at": end_dt.isoformat() if end_dt else None,
        "end_all_day": int(end_all_day if end_dt else False),
        "daily_reminder": int(bool(merged.get("daily_reminder"))),
    }


def _should_reset_start(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    return payload["start_at"] != existing["start_at"] or payload["start_all_day"] != int(bool(existing["start_all_day"]))


def _should_reset_end(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    return payload["end_at"] != existing.get("end_at") or payload["end_all_day"] != int(bool(existing["end_all_day"]))


def _should_reset_daily(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    tracked_fields = ("start_at", "start_all_day", "end_at", "end_all_day", "daily_reminder")
    return any(payload[field] != existing.get(field) for field in tracked_fields)


@app.get("/", response_class=FileResponse)
async def read_index() -> FileResponse:
    return _file_response("index.html")


@app.get("/tasks", response_class=FileResponse)
async def read_tasks_page() -> FileResponse:
    return _file_response("tasks.html")


@app.get("/api/tasks", response_model=List[Task])
async def list_tasks() -> List[Task]:
    return database.list_tasks()


@app.post("/api/tasks", response_model=Task, status_code=201)
async def create_task(task: TaskCreate) -> Task:
    payload = _prepare_task_payload(task.model_dump())
    created = database.create_task(payload)
    return created  # type: ignore[return-value]


@app.put("/api/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task: TaskUpdate) -> Task:
    existing = database.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")

    payload = _prepare_task_payload(task.model_dump(exclude_unset=True), existing=existing)
    reset_start = _should_reset_start(existing, payload)
    reset_end = _should_reset_end(existing, payload)
    reset_daily = _should_reset_daily(existing, payload)

    if reset_start:
        payload["start_notified"] = 0
    if reset_end:
        payload["end_notified"] = 0
    if reset_daily:
        payload["last_daily_notified"] = None

    updated = database.update_task(task_id, payload)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update task")

    claim_types: list[database.NotificationType] = []
    if reset_start:
        claim_types.append("start")
    if reset_end:
        claim_types.append("end")
    if reset_daily:
        claim_types.append("daily")
    database.clear_notification_claims(task_id, claim_types)

    return updated  # type: ignore[return-value]


@app.delete("/api/tasks/{task_id}", status_code=204, response_class=Response)
async def delete_task(task_id: int) -> Response:
    existing = database.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    database.delete_task(task_id)
    return Response(status_code=204)


@app.get("/api/settings", response_model=Settings)
async def read_settings() -> Settings:
    return database.get_settings()


@app.post("/api/settings", response_model=Settings)
async def update_settings(payload: SettingsUpdate) -> Settings:
    return database.update_settings(
        payload.webhook_url.strip(),
        payload.deadline_notice_minutes,
        payload.daily_reminder_time,
    )


@app.post("/api/settings/test")
async def test_settings_connectivity(payload: WebhookTestRequest) -> Dict[str, str]:
    webhook = payload.webhook_url.strip()
    if not webhook:
        raise HTTPException(status_code=400, detail="Webhook 地址不能为空")
    success, detail = await run_in_threadpool(reminder_service.send_test_message, webhook)
    if not success:
        raise HTTPException(status_code=400, detail=detail or "Webhook 测试失败")
    return {"status": "ok", "message": "测试消息已成功发送到 Webhook"}

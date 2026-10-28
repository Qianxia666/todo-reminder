from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, time as dtime, timedelta
from http.client import HTTPException as HTTPProtocolException
from threading import Event, Lock, Thread
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import database
from .timezone import BEIJING_TZ, ensure_beijing, now_in_beijing
from .webhook_security import normalize_webhook_url

logger = logging.getLogger(__name__)

def _env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value) or value < minimum:
        return default
    return value


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return value if value >= minimum else default


WEBHOOK_TIMEOUT_SECONDS = _env_float("TODO_WEBHOOK_TIMEOUT_SECONDS", 5.0, minimum=0.1)
MIN_CLAIM_TTL_SECONDS = math.ceil(WEBHOOK_TIMEOUT_SECONDS) + 5
DEFAULT_CLAIM_TTL_SECONDS = max(
    _env_int("TODO_NOTIFICATION_CLAIM_TTL_SECONDS", 90, minimum=1),
    MIN_CLAIM_TTL_SECONDS,
)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


_WEBHOOK_OPENER = build_opener(_NoRedirectHandler())
MAX_WEBHOOK_RESPONSE_BYTES = 64 * 1024


def _open_webhook_request(request: Request):
    return _WEBHOOK_OPENER.open(request, timeout=WEBHOOK_TIMEOUT_SECONDS)


def _validated_webhook_url(webhook: str) -> Optional[str]:
    try:
        return normalize_webhook_url(webhook, allow_blank=False)
    except (TypeError, ValueError):
        return None


def _post_webhook_text(webhook: str, message: str) -> Tuple[bool, str]:
    validated_webhook = _validated_webhook_url(webhook)
    if not validated_webhook:
        return False, "Webhook 地址不符合安全策略"

    payload = {
        "msg_type": "text",
        "content": {"text": message},
    }
    request_body = json.dumps(payload).encode("utf-8")
    try:
        request = Request(
            validated_webhook,
            data=request_body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
    except ValueError:
        logger.warning("Invalid webhook URL configured")
        return False, "Webhook 地址必须是有效的 http(s) 地址"

    status_code = 0
    response_text = ""
    try:
        with _open_webhook_request(request) as response:
            status_code = getattr(response, "status", response.getcode())
            response_bytes = response.read(MAX_WEBHOOK_RESPONSE_BYTES + 1)
            if len(response_bytes) > MAX_WEBHOOK_RESPONSE_BYTES:
                logger.warning("Webhook response exceeded %s bytes", MAX_WEBHOOK_RESPONSE_BYTES)
                return False, "Webhook 返回内容过大"
            encoding = response.headers.get_content_charset("utf-8")
            response_text = response_bytes.decode(encoding, errors="replace")
    except HTTPError as exc:
        status_code = exc.code
        response_bytes = exc.read(MAX_WEBHOOK_RESPONSE_BYTES + 1)
        if len(response_bytes) > MAX_WEBHOOK_RESPONSE_BYTES:
            response_text = "<response too large>"
        else:
            response_text = response_bytes.decode("utf-8", errors="replace")
        detail = f"Feishu webhook responded with {status_code}"
        logger.warning("%s: %s", detail, response_text[:200])
        return False, detail
    except (URLError, OSError, HTTPProtocolException) as exc:
        detail = getattr(exc, "reason", None)
        logger.warning("Failed to call Feishu webhook: %s", detail or exc)
        return False, str(detail or exc)

    response_body: Any = None
    try:
        response_body = json.loads(response_text) if response_text else None
    except json.JSONDecodeError:
        response_body = None

    if status_code >= 400:
        detail = f"Feishu webhook responded with {status_code}"
        logger.warning("%s: %s", detail, response_text[:200])
        return False, detail

    if not isinstance(response_body, dict):
        logger.warning("Webhook returned a non-JSON success response")
        return False, "Webhook 返回格式不正确"

    business_code = response_body.get("code", response_body.get("StatusCode"))
    if business_code not in (0, "0"):
        detail = str(
            response_body.get("msg")
            or response_body.get("StatusMessage")
            or (
                f"Feishu webhook business error: {business_code}"
                if business_code is not None
                else "Webhook 返回体缺少业务状态码"
            )
        )
        logger.warning("Feishu webhook business failure: %s", detail)
        return False, detail

    return True, "ok"


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return ensure_beijing(datetime.fromisoformat(value))
    except ValueError:
        logger.warning("Invalid datetime stored in DB: %s", value)
        return None


def _format_human(dt: datetime) -> str:
    return ensure_beijing(dt).strftime("%Y-%m-%d %H:%M")


def _format_task_time(task: Dict[str, Any], field_prefix: str) -> str:
    dt = _parse_datetime(task.get(f"{field_prefix}_at"))
    if not dt:
        return "未设置"
    if task.get(f"{field_prefix}_all_day"):
        return ensure_beijing(dt).strftime("%Y-%m-%d 全天")
    return _format_human(dt)


def _format_description(task: Dict[str, Any]) -> str:
    description = task.get("description") or ""
    description_text = str(description).strip()
    return description_text or "无备注"


def _build_message(header: str, rows: List[Tuple[str, str]], footer: Optional[str] = None) -> str:
    lines = [header]
    lines.extend(f"{label}：{value}" for label, value in rows)
    if footer:
        lines.append(footer)
    return "\n".join(lines)


def _parse_hhmm(value: Optional[str]) -> Optional[dtime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        hour, minute = map(int, value.split(":", 1))
        return dtime(hour=hour, minute=minute, tzinfo=BEIJING_TZ)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Invalid daily reminder time configured: %s", value)
        return None


def _coerce_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


class ReminderService:
    """Single-process reminder worker with DB-backed de-duplication."""

    def __init__(self, interval_seconds: int = 30, claim_ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS) -> None:
        self.interval_seconds = max(1, int(interval_seconds))
        self.claim_ttl_seconds = max(MIN_CLAIM_TTL_SECONDS, int(claim_ttl_seconds))
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._lifecycle_lock = Lock()

    def start(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                if not self._stop_event.is_set():
                    return
                # A previous stop() timed out while this worker was finishing a
                # cycle. Give it a moment to exit, otherwise resume it instead
                # of leaving the service without an active worker.
                thread.join(timeout=max(1.0, WEBHOOK_TIMEOUT_SECONDS))
                if thread.is_alive():
                    self._stop_event.clear()
                    logger.info("Reminder worker resumed after an interrupted stop")
                    return
                self._thread = None
            self._stop_event.clear()
            self._thread = Thread(target=self._run, daemon=True, name="todo-reminder-worker")
            self._thread.start()
            logger.info("Reminder worker started")

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
        if thread:
            thread.join(timeout=max(5.0, WEBHOOK_TIMEOUT_SECONDS + 1.0))
            if thread.is_alive():
                logger.warning("Reminder worker did not stop before the shutdown timeout")
                return
            with self._lifecycle_lock:
                if self._thread is thread:
                    self._thread = None
            logger.info("Reminder worker stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Reminder worker crashed")
            finally:
                self._stop_event.wait(self.interval_seconds)

    def run_once(self) -> None:
        settings = database.get_settings()
        webhook = settings.get("webhook_url", "").strip()
        deadline_notice_minutes = _coerce_positive_int(settings.get("deadline_notice_minutes"), default=30)
        reminder_time = _parse_hhmm(settings.get("daily_reminder_time")) or dtime(hour=9, tzinfo=BEIJING_TZ)
        if not webhook:
            return

        now = now_in_beijing()
        tasks = database.list_tasks_for_reminders()
        for task in tasks:
            try:
                self._handle_start(task, now, webhook)
                self._handle_deadline(task, now, webhook, deadline_notice_minutes)
                self._handle_daily(task, now, webhook, reminder_time)
            except Exception:
                logger.exception("Failed to process reminder task %s", task.get("id"))

    def _handle_start(self, task: Dict[str, Any], now: datetime, webhook: str) -> None:
        if task.get("start_notified"):
            return
        start_at = _parse_datetime(task.get("start_at"))
        if not start_at or now < start_at:
            return
        message = _build_message(
            "【任务开始提醒】",
            [
                ("任务", task["title"]),
                ("开始时间", _format_task_time(task, "start")),
                ("备注", _format_description(task)),
            ],
            "请按计划推进任务。",
        )
        self._send_task_notification(task, "start", task.get("start_at") or "", webhook, message)

    def _handle_deadline(self, task: Dict[str, Any], now: datetime, webhook: str, lead_minutes: int) -> None:
        if task.get("end_notified"):
            return
        end_at = _parse_datetime(task.get("end_at"))
        if not end_at:
            return
        notice_point = end_at - timedelta(minutes=lead_minutes)
        if now < notice_point:
            return
        message = _build_message(
            "【任务截止提醒】",
            [
                ("任务", task["title"]),
                ("截止时间", _format_task_time(task, "end")),
                ("提前提醒", f"{lead_minutes} 分钟"),
                ("备注", _format_description(task)),
            ],
            "如已完成，请同步更新状态。",
        )
        self._send_task_notification(task, "end", task.get("end_at") or "", webhook, message)

    def _handle_daily(self, task: Dict[str, Any], now: datetime, webhook: str, reminder_time: dtime) -> None:
        if not task.get("daily_reminder"):
            return
        start_at = _parse_datetime(task.get("start_at"))
        if not start_at or now < start_at:
            return
        end_at = _parse_datetime(task.get("end_at"))
        if end_at and now.replace(second=0, microsecond=0) > end_at:
            return
        reminder_point = datetime.combine(now.date(), reminder_time)
        if now < reminder_point:
            return
        today_iso = now.date().isoformat()
        if task.get("last_daily_notified") == today_iso:
            return
        message = _build_message(
            "【今日进度提醒】",
            [
                ("任务", task["title"]),
                ("提醒时间", reminder_point.strftime("%H:%M")),
                ("开始时间", _format_task_time(task, "start")),
                ("截止时间", _format_task_time(task, "end") if end_at else "未设置"),
                ("备注", _format_description(task)),
            ],
            "请聚焦今日关键进展。",
        )
        notification_key = database.daily_notification_key(task, today_iso)
        self._send_task_notification(task, "daily", notification_key, webhook, message, daily_date=today_iso)

    def _send_task_notification(
        self,
        task: Dict[str, Any],
        notification_type: database.NotificationType,
        notification_key: str,
        webhook: str,
        message: str,
        *,
        daily_date: Optional[str] = None,
    ) -> bool:
        task_id = int(task["id"])
        claim_token = database.claim_notification_with_token(
            task_id, notification_type, notification_key, self.claim_ttl_seconds
        )
        if not claim_token:
            return False

        webhook_sent = False
        completed = False
        try:
            success, detail = _post_webhook_text(webhook, message)
            if not success:
                logger.warning(
                    "Failed to send %s reminder for task %s: %s",
                    notification_type,
                    task_id,
                    detail,
                )
                return False
            webhook_sent = True

            completed = database.complete_notification(
                task_id,
                notification_type,
                notification_key,
                daily_date=daily_date,
                claim_token=claim_token,
            )
            if not completed:
                logger.info("Reminder %s for task %s was superseded before completion", notification_type, task_id)
            return completed
        finally:
            if not webhook_sent:
                database.release_notification_claim(task_id, notification_type, notification_key, claim_token)

    def send_test_message(self, webhook: str) -> Tuple[bool, str]:
        timestamp = now_in_beijing().strftime("%Y-%m-%d %H:%M:%S")
        message = f"飞书任务提醒连通性测试（{timestamp}）"
        return _post_webhook_text(webhook, message)

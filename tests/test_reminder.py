from __future__ import annotations

import json
import unittest
from datetime import datetime, time
from email.message import Message
from unittest.mock import Mock, patch

from app.reminder import (
    MIN_CLAIM_TTL_SECONDS,
    ReminderService,
    _parse_datetime,
    _parse_hhmm,
    _post_webhook_text,
)
from app.timezone import BEIJING_TZ


def _task(**overrides: object) -> dict[str, object]:
    task: dict[str, object] = {
        "id": 1,
        "title": "Daily boundary",
        "description": None,
        "start_at": "2026-07-19T10:00:00+08:00",
        "start_all_day": False,
        "end_at": "2026-07-19T17:00:00+08:00",
        "end_all_day": False,
        "start_notified": False,
        "end_notified": False,
        "daily_reminder": True,
        "last_daily_notified": None,
    }
    task.update(overrides)
    return task


class DailyReminderBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReminderService()
        self.reminder_time = time(9, 0, tzinfo=BEIJING_TZ)

    def test_does_not_send_before_exact_start_time(self) -> None:
        now = datetime(2026, 7, 19, 9, 30, tzinfo=BEIJING_TZ)
        with patch.object(self.service, "_send_task_notification") as send:
            self.service._handle_daily(_task(), now, "https://example.com/hook", self.reminder_time)
        send.assert_not_called()

    def test_does_not_send_after_exact_end_time(self) -> None:
        now = datetime(2026, 7, 19, 17, 1, tzinfo=BEIJING_TZ)
        with patch.object(self.service, "_send_task_notification") as send:
            self.service._handle_daily(_task(), now, "https://example.com/hook", self.reminder_time)
        send.assert_not_called()

    def test_sends_once_inside_task_window_after_reminder_time(self) -> None:
        now = datetime(2026, 7, 19, 10, 30, tzinfo=BEIJING_TZ)
        with patch.object(self.service, "_send_task_notification") as send:
            self.service._handle_daily(_task(), now, "https://example.com/hook", self.reminder_time)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1:4], ("daily", "2026-07-19", "https://example.com/hook"))


class NotificationSendTests(unittest.TestCase):
    def test_uses_claim_owner_token_for_completion(self) -> None:
        service = ReminderService()
        with (
            patch("app.reminder.database.claim_notification_with_token", return_value="owner-token"),
            patch("app.reminder._post_webhook_text", return_value=(True, "ok")),
            patch("app.reminder.database.complete_notification", return_value=True) as complete,
            patch("app.reminder.database.release_notification_claim") as release,
        ):
            result = service._send_task_notification(
                _task(), "start", "2026-07-19T10:00:00+08:00", "https://example.com/hook", "message"
            )

        self.assertTrue(result)
        self.assertEqual(complete.call_args.kwargs["claim_token"], "owner-token")
        release.assert_not_called()

    def test_failed_webhook_releases_only_its_own_claim(self) -> None:
        service = ReminderService()
        with (
            patch("app.reminder.database.claim_notification_with_token", return_value="owner-token"),
            patch("app.reminder._post_webhook_text", return_value=(False, "unavailable")),
            patch("app.reminder.database.release_notification_claim") as release,
        ):
            result = service._send_task_notification(
                _task(), "start", "2026-07-19T10:00:00+08:00", "https://example.com/hook", "message"
            )

        self.assertFalse(result)
        release.assert_called_once_with(1, "start", "2026-07-19T10:00:00+08:00", "owner-token")


class WorkerLifecycleTests(unittest.TestCase):
    def test_claim_ttl_cannot_be_shorter_than_webhook_safety_window(self) -> None:
        service = ReminderService(claim_ttl_seconds=1)
        self.assertEqual(service.claim_ttl_seconds, MIN_CLAIM_TTL_SECONDS)

    def test_stop_keeps_reference_to_worker_that_has_not_exited(self) -> None:
        service = ReminderService()
        thread = Mock()
        thread.is_alive.return_value = True
        service._thread = thread

        service.stop()

        self.assertIs(service._thread, thread)
        thread.join.assert_called_once()
        with patch("app.reminder.Thread") as thread_factory:
            service.start()
        thread_factory.assert_not_called()

    def test_stop_clears_reference_after_worker_exits(self) -> None:
        service = ReminderService()
        thread = Mock()
        thread.is_alive.return_value = False
        service._thread = thread

        service.stop()

        self.assertIsNone(service._thread)

    def test_invalid_stored_values_are_ignored(self) -> None:
        self.assertIsNone(_parse_datetime(123))  # type: ignore[arg-type]
        self.assertIsNone(_parse_hhmm({}))  # type: ignore[arg-type]


class FakeWebhookResponse:
    def __init__(self, body: dict[str, object], status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(body).encode("utf-8")
        self.headers = Message()
        self.headers["Content-Type"] = "application/json; charset=utf-8"

    def __enter__(self) -> "FakeWebhookResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body


class WebhookResponseTests(unittest.TestCase):
    def test_rejects_business_error_in_successful_http_response(self) -> None:
        with patch("app.reminder.urlopen", return_value=FakeWebhookResponse({"code": 19001, "msg": "invalid"})):
            success, detail = _post_webhook_text("https://example.com/hook", "hello")
        self.assertFalse(success)
        self.assertEqual(detail, "invalid")

    def test_accepts_successful_feishu_response(self) -> None:
        with patch("app.reminder.urlopen", return_value=FakeWebhookResponse({"code": 0, "msg": "ok"})):
            success, detail = _post_webhook_text("https://example.com/hook", "hello")
        self.assertTrue(success)
        self.assertEqual(detail, "ok")

    def test_rejects_invalid_webhook_without_network_call(self) -> None:
        network = Mock()
        with patch("app.reminder.urlopen", network):
            success, _ = _post_webhook_text("file:///tmp/hook", "hello")
        self.assertFalse(success)
        network.assert_not_called()


if __name__ == "__main__":
    unittest.main()

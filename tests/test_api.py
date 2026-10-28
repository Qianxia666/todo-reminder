from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import database
from app.main import app


class TaskApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "api.db"
        database.init_db()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def _create_task(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "title": " Review release ",
            "description": " Verify the checklist ",
            "start_at": "2026-07-19T10:30:45",
            "start_all_day": False,
            "end_at": "2026-07-19T11:30:59",
            "end_all_day": False,
            "daily_reminder": True,
        }
        payload.update(overrides)
        response = self.client.post("/api/tasks", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_crud_and_partial_update(self) -> None:
        task = self._create_task()
        self.assertEqual(task["title"], "Review release")
        self.assertEqual(task["description"], "Verify the checklist")
        self.assertEqual(task["start_at"], "2026-07-19T10:30:00+08:00")
        self.assertEqual(task["end_at"], "2026-07-19T11:30:00+08:00")

        task_id = int(task["id"])
        response = self.client.put(f"/api/tasks/{task_id}", json={"description": None, "end_at": None})
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertIsNone(updated["description"])
        self.assertIsNone(updated["end_at"])
        self.assertFalse(updated["end_all_day"])

        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 204)
        self.assertEqual(self.client.get("/api/tasks").json(), [])

    def test_all_day_values_are_normalized_to_beijing_day_bounds(self) -> None:
        task = self._create_task(
            start_at="2026-08-01",
            start_all_day=True,
            end_at="2026-08-03",
            end_all_day=True,
        )
        self.assertEqual(task["start_at"], "2026-08-01T00:00:00+08:00")
        self.assertEqual(task["end_at"], "2026-08-03T23:59:00+08:00")

        same_day = self._create_task(
            start_at="2026-08-05T23:00:00",
            start_all_day=True,
            end_at="2026-08-05T01:00:00",
            end_all_day=True,
        )
        self.assertEqual(same_day["start_at"], "2026-08-05T00:00:00+08:00")
        self.assertEqual(same_day["end_at"], "2026-08-05T23:59:00+08:00")

        response = self.client.put(
            f"/api/tasks/{same_day['id']}",
            json={"start_at": "2026-08-06T23:00:00", "end_at": "2026-08-06T01:00:00"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["start_at"], "2026-08-06T00:00:00+08:00")
        self.assertEqual(response.json()["end_at"], "2026-08-06T23:59:00+08:00")

    def test_schedule_changes_reset_only_relevant_notification_state(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        database.update_task(
            task_id,
            {"start_notified": 1, "end_notified": 1, "last_daily_notified": "2026-07-19"},
        )

        response = self.client.put(f"/api/tasks/{task_id}", json={"title": "Renamed"})
        self.assertEqual(response.status_code, 200, response.text)
        renamed = response.json()
        self.assertTrue(renamed["start_notified"])
        self.assertTrue(renamed["end_notified"])
        self.assertEqual(renamed["last_daily_notified"], "2026-07-19")

        response = self.client.put(f"/api/tasks/{task_id}", json={"start_at": "2026-07-19T10:45"})
        self.assertEqual(response.status_code, 200, response.text)
        rescheduled = response.json()
        self.assertFalse(rescheduled["start_notified"])
        self.assertTrue(rescheduled["end_notified"])
        self.assertIsNone(rescheduled["last_daily_notified"])

    def test_legacy_second_precision_does_not_reset_notifications_on_unrelated_update(self) -> None:
        task = database.create_task(
            {
                "title": "Legacy precise task",
                "description": None,
                "start_at": "2026-08-01T09:30:45+08:00",
                "start_all_day": 0,
                "end_at": "2026-08-01T11:00:45+08:00",
                "end_all_day": 0,
                "daily_reminder": 1,
            }
        )
        task_id = int(task["id"])
        database.update_task(
            task_id,
            {"start_notified": 1, "end_notified": 1, "last_daily_notified": "2026-08-01"},
        )

        response = self.client.put(f"/api/tasks/{task_id}", json={"title": "Legacy renamed"})
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertEqual(updated["start_at"], "2026-08-01T09:30:00+08:00")
        self.assertEqual(updated["end_at"], "2026-08-01T11:00:00+08:00")
        self.assertTrue(updated["start_notified"])
        self.assertTrue(updated["end_notified"])
        self.assertEqual(updated["last_daily_notified"], "2026-08-01")

    def test_settings_update_requires_webhook_to_avoid_silent_clearing(self) -> None:
        base = {
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/keep",
            "deadline_notice_minutes": 45,
            "daily_reminder_time": "08:30",
        }
        self.assertEqual(self.client.post("/api/settings", json=base).status_code, 200)

        partial = self.client.post(
            "/api/settings",
            json={"deadline_notice_minutes": 5, "daily_reminder_time": "07:00"},
        )
        self.assertEqual(partial.status_code, 422)

        settings = self.client.get("/api/settings").json()
        self.assertEqual(settings["webhook_url"], base["webhook_url"])
        self.assertEqual(settings["deadline_notice_minutes"], 45)
        self.assertEqual(settings["daily_reminder_time"], "08:30")

    def test_whitespace_only_title_is_rejected_for_direct_mutations(self) -> None:
        from fastapi import HTTPException

        from app.main import _build_task_mutation

        task = self._create_task()
        existing = database.get_task(int(task["id"]))
        self.assertIsNotNone(existing)
        with self.assertRaises(HTTPException) as raised:
            _build_task_mutation(existing, {"title": "   "})  # type: ignore[arg-type]
        self.assertEqual(raised.exception.status_code, 400)

    def test_invalid_payloads_are_rejected(self) -> None:
        blank = self.client.post("/api/tasks", json={"title": " ", "start_at": "2026-07-19T10:00"})
        self.assertEqual(blank.status_code, 422)

        task = self._create_task()
        task_id = int(task["id"])
        invalid_window = self.client.put(f"/api/tasks/{task_id}", json={"end_at": "2026-07-19T09:00"})
        self.assertEqual(invalid_window.status_code, 400)

        invalid_settings = self.client.post(
            "/api/settings",
            json={
                "webhook_url": "file:///tmp/hook",
                "deadline_notice_minutes": 0,
                "daily_reminder_time": "25:00",
            },
        )
        self.assertEqual(invalid_settings.status_code, 422)

        non_padded_time = self.client.post(
            "/api/settings",
            json={"webhook_url": "", "deadline_notice_minutes": 30, "daily_reminder_time": "9:00"},
        )
        self.assertEqual(non_padded_time.status_code, 422)

    def test_missing_tasks_return_not_found(self) -> None:
        self.assertEqual(self.client.put("/api/tasks/999", json={"title": "missing"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/tasks/999").status_code, 404)

    def test_cross_origin_requests_are_not_authorized(self) -> None:
        response = self.client.options(
            "/api/tasks",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_api_responses_disable_caching_and_add_security_headers(self) -> None:
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")

    def test_webhook_policy_rejects_http_and_unapproved_hosts(self) -> None:
        base = {"deadline_notice_minutes": 30, "daily_reminder_time": "09:00"}
        insecure = self.client.post(
            "/api/settings", json={**base, "webhook_url": "http://open.feishu.cn/hook"}
        )
        self.assertEqual(insecure.status_code, 422)

        unapproved = self.client.post(
            "/api/settings", json={**base, "webhook_url": "https://127.0.0.1/internal"}
        )
        self.assertEqual(unapproved.status_code, 422)

        official = self.client.post(
            "/api/settings",
            json={**base, "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test"},
        )
        self.assertEqual(official.status_code, 200, official.text)


if __name__ == "__main__":
    unittest.main()

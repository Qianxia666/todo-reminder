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


if __name__ == "__main__":
    unittest.main()

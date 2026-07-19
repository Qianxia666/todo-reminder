from __future__ import annotations

import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app import database


class NotificationClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "claims.db"
        database.init_db()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_task(self) -> dict[str, object]:
        return database.create_task(
            {
                "title": "Claim test",
                "description": None,
                "start_at": "2026-07-19T10:00:00+08:00",
                "start_all_day": 0,
                "end_at": "2026-07-19T12:00:00+08:00",
                "end_all_day": 0,
                "daily_reminder": 1,
            }
        )

    def test_schema_migrates_claim_tokens(self) -> None:
        conn = sqlite3.connect(database.DB_PATH)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(reminder_claims)")}
        finally:
            conn.close()
        self.assertIn("claim_token", columns)

    def test_invalid_runtime_values_fall_back_to_safe_defaults(self) -> None:
        with patch.dict("os.environ", {"TODO_SQLITE_TIMEOUT_SECONDS": "not-a-number"}):
            self.assertEqual(database._env_float("TODO_SQLITE_TIMEOUT_SECONDS", 30.0, minimum=0.1), 30.0)
        with patch.dict("os.environ", {"TODO_SQLITE_TIMEOUT_SECONDS": "nan"}):
            self.assertEqual(database._env_float("TODO_SQLITE_TIMEOUT_SECONDS", 30.0, minimum=0.1), 30.0)
        with patch.dict("os.environ", {"TODO_SQLITE_BUSY_TIMEOUT_MS": "-5"}):
            self.assertEqual(database._env_int("TODO_SQLITE_BUSY_TIMEOUT_MS", 30000, minimum=0), 30000)

    def test_only_one_worker_can_claim_and_completed_slot_stays_closed(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        key = str(task["start_at"])

        token = database.claim_notification_with_token(task_id, "start", key, 90)
        self.assertIsNotNone(token)
        self.assertIsNone(database.claim_notification_with_token(task_id, "start", key, 90))
        self.assertTrue(
            database.complete_notification(task_id, "start", key, claim_token=token)
        )
        self.assertTrue(database.get_task(task_id)["start_notified"])
        self.assertIsNone(database.claim_notification_with_token(task_id, "start", key, 90))

    def test_stale_schedule_key_cannot_be_claimed_or_completed(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        old_key = str(task["start_at"])
        token = database.claim_notification_with_token(task_id, "start", old_key, 90)
        self.assertIsNotNone(token)

        database.update_task(task_id, {"start_at": "2026-07-19T11:00:00+08:00", "start_notified": 0})
        database.clear_notification_claims(task_id, ["start"])

        self.assertFalse(
            database.complete_notification(task_id, "start", old_key, claim_token=token)
        )
        self.assertFalse(database.get_task(task_id)["start_notified"])
        self.assertIsNone(database.claim_notification_with_token(task_id, "start", old_key, 90))
        self.assertIsNotNone(
            database.claim_notification_with_token(task_id, "start", "2026-07-19T11:00:00+08:00", 90)
        )

    def test_daily_completion_prevents_same_day_reclaim(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        today = "2026-07-19"
        token = database.claim_notification_with_token(task_id, "daily", today, 90)
        self.assertIsNotNone(token)
        self.assertTrue(
            database.complete_notification(
                task_id,
                "daily",
                today,
                daily_date=today,
                claim_token=token,
            )
        )
        self.assertIsNone(database.claim_notification_with_token(task_id, "daily", today, 90))


if __name__ == "__main__":
    unittest.main()

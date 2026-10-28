from __future__ import annotations

import sqlite3
import threading
import time
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
from pathlib import Path

from app import database
from app.timezone import BEIJING_TZ


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

    def test_schema_migrates_legacy_database_before_using_new_columns(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.executescript(
                """
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    start_at TEXT NOT NULL,
                    start_all_day INTEGER NOT NULL DEFAULT 0,
                    end_at TEXT,
                    end_all_day INTEGER NOT NULL DEFAULT 0,
                    start_notified INTEGER NOT NULL DEFAULT 0,
                    end_notified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    webhook_url TEXT DEFAULT '',
                    deadline_notice_minutes INTEGER NOT NULL DEFAULT 30
                );
                INSERT INTO settings (id, webhook_url, deadline_notice_minutes)
                VALUES (1, 'https://example.com/legacy', 45);
                CREATE TABLE reminder_claims (
                    task_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    notification_key TEXT NOT NULL,
                    claimed_at TEXT NOT NULL,
                    claimed_until TEXT NOT NULL,
                    PRIMARY KEY (task_id, notification_type, notification_key)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        database.DB_PATH = legacy_path
        database.init_db()

        conn = sqlite3.connect(legacy_path)
        try:
            task_columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            settings_columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)")}
            claim_columns = {row[1] for row in conn.execute("PRAGMA table_info(reminder_claims)")}
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(tasks)")}
            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()

        self.assertIn("daily_reminder", task_columns)
        self.assertIn("last_daily_notified", task_columns)
        self.assertIn("daily_reminder_time", settings_columns)
        self.assertIn("claim_token", claim_columns)
        self.assertIn("idx_tasks_daily_reminder", indexes)
        self.assertEqual(user_version, database.SCHEMA_VERSION)
        self.assertEqual(database.get_settings()["webhook_url"], "https://example.com/legacy")
        self.assertEqual(database.get_settings()["deadline_notice_minutes"], 45)
        self.assertEqual(database.get_settings()["daily_reminder_time"], "09:00")

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

        database.update_task(
            task_id,
            {"start_at": "2026-07-19T11:00:00+08:00", "start_notified": 0},
            clear_claim_types=["start"],
        )

        self.assertFalse(
            database.complete_notification(task_id, "start", old_key, claim_token=token)
        )
        self.assertFalse(database.get_task(task_id)["start_notified"])
        self.assertIsNone(database.claim_notification_with_token(task_id, "start", old_key, 90))
        self.assertIsNotNone(
            database.claim_notification_with_token(task_id, "start", "2026-07-19T11:00:00+08:00", 90)
        )

    def test_daily_claim_key_rejects_stale_schedule_snapshot(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        today = "2026-07-19"
        stale_key = database.daily_notification_key(task, today)

        database.update_task(
            task_id,
            {"start_at": "2026-07-20T10:00:00+08:00", "last_daily_notified": None},
            clear_claim_types=["daily"],
        )

        self.assertIsNone(database.claim_notification_with_token(task_id, "daily", stale_key, 90))
        current = database.get_task(task_id)
        self.assertIsNotNone(current)
        current_key = database.daily_notification_key(current, today)  # type: ignore[arg-type]
        self.assertIsNotNone(database.claim_notification_with_token(task_id, "daily", current_key, 90))

    def test_task_database_helpers_reject_unknown_columns(self) -> None:
        with self.assertRaises(ValueError):
            database.create_task({"title": "unsafe", "start_at": "2026-07-19T10:00:00+08:00", "oops": 1})

        task = self._create_task()
        with self.assertRaises(ValueError):
            database.update_task(int(task["id"]), {"oops": 1})

    def test_settings_update_recreates_missing_singleton_row(self) -> None:
        conn = sqlite3.connect(database.DB_PATH)
        try:
            conn.execute("DELETE FROM settings WHERE id = 1")
            conn.commit()
        finally:
            conn.close()

        recovered = database.get_settings()
        self.assertEqual(recovered["webhook_url"], "")
        self.assertEqual(recovered["deadline_notice_minutes"], 30)
        self.assertEqual(recovered["daily_reminder_time"], "09:00")

        conn = sqlite3.connect(database.DB_PATH)
        try:
            conn.execute("DELETE FROM settings WHERE id = 1")
            conn.commit()
        finally:
            conn.close()

        settings = database.update_settings("https://example.com/hook", 60, "08:30")
        self.assertEqual(settings["webhook_url"], "https://example.com/hook")
        self.assertEqual(settings["deadline_notice_minutes"], 60)
        self.assertEqual(settings["daily_reminder_time"], "08:30")

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

    def test_daily_task_remains_pollable_through_its_end_minute(self) -> None:
        task = self._create_task()
        task_id = int(task["id"])
        database.update_task(
            task_id,
            {
                "end_at": "2026-07-19T17:00:00+08:00",
                "start_notified": 1,
                "end_notified": 1,
            },
        )

        with patch(
            "app.database.now_in_beijing",
            return_value=datetime(2026, 7, 19, 17, 0, 30, tzinfo=BEIJING_TZ),
        ):
            during_end_minute = database.list_tasks_for_reminders()
        self.assertIn(task_id, {int(item["id"]) for item in during_end_minute})

        with patch(
            "app.database.now_in_beijing",
            return_value=datetime(2026, 7, 19, 17, 1, 0, tzinfo=BEIJING_TZ),
        ):
            after_end_minute = database.list_tasks_for_reminders()
        self.assertNotIn(task_id, {int(item["id"]) for item in after_end_minute})

    def test_rejects_database_from_newer_schema_version(self) -> None:
        conn = sqlite3.connect(database.DB_PATH)
        try:
            conn.execute("PRAGMA user_version = 999")
            conn.commit()
        finally:
            conn.close()

        with self.assertRaisesRegex(RuntimeError, "newer than this application supports"):
            database.init_db()

        conn = sqlite3.connect(database.DB_PATH)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(version, 999)

    def test_atomic_task_mutations_do_not_lose_concurrent_partial_updates(self) -> None:
        from app.main import _build_task_mutation

        task = self._create_task()
        task_id = int(task["id"])
        first_entered = threading.Event()
        errors: list[BaseException] = []

        def first_mutation(existing):
            first_entered.set()
            time.sleep(0.08)
            return _build_task_mutation(existing, {"title": "First change"})

        def worker_one() -> None:
            try:
                database.mutate_task(task_id, first_mutation)
            except BaseException as exc:
                errors.append(exc)

        def worker_two() -> None:
            try:
                first_entered.wait(timeout=1)
                database.mutate_task(
                    task_id,
                    lambda existing: _build_task_mutation(existing, {"description": "Second change"}),
                )
            except BaseException as exc:
                errors.append(exc)

        thread_one = threading.Thread(target=worker_one)
        thread_two = threading.Thread(target=worker_two)
        thread_one.start()
        thread_two.start()
        thread_one.join(timeout=2)
        thread_two.join(timeout=2)

        self.assertFalse(thread_one.is_alive())
        self.assertFalse(thread_two.is_alive())
        self.assertEqual(errors, [])
        updated = database.get_task(task_id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["title"], "First change")
        self.assertEqual(updated["description"], "Second change")


if __name__ == "__main__":
    unittest.main()

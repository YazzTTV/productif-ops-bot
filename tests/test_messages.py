import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from productif_ops_bot.db import init_db
from productif_ops_bot.messages import build_evening_checkin, build_personal_plan, build_recap
from productif_ops_bot.bot import _parse_key_value_command
from productif_ops_bot.tasks import create_task, list_tasks_for_person, recap_counts, seed_people, seed_sample_tasks


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        seed_people(self.conn)
        seed_sample_tasks(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_personal_plan_contains_task_ids(self):
        person = self.conn.execute("SELECT * FROM people WHERE id = 'noah'").fetchone()
        tasks = list_tasks_for_person(self.conn, "noah")
        text = build_personal_plan(person, tasks)
        self.assertIn("PIO-001", text)
        self.assertIn("/done PIO-001", text)

    def test_evening_checkin_uses_first_open_task_id(self):
        person = self.conn.execute("SELECT * FROM people WHERE id = 'noah'").fetchone()
        tasks = list_tasks_for_person(self.conn, "noah")
        text = build_evening_checkin(person, tasks)
        self.assertIn("/blocked PIO-001", text)

    def test_recap_contains_people(self):
        text = build_recap(recap_counts(self.conn))
        self.assertIn("Noah", text)
        self.assertIn("Gaetan", text)
        self.assertIn("Arthur", text)

    def test_parse_addtask_command(self):
        fields = _parse_key_value_command(
            "/addtask owner:noah title:Soumettre TestFlight priority:P0 due:2026-08-13 sop:app-store-submit.md"
        )
        self.assertEqual(fields["owner"], "noah")
        self.assertEqual(fields["title"], "Soumettre TestFlight")
        self.assertEqual(fields["priority"], "P0")
        self.assertEqual(fields["due"], "2026-08-13")
        self.assertEqual(fields["sop"], "app-store-submit.md")

    def test_create_task(self):
        ok = create_task(
            self.conn,
            task_id="PIO-999",
            title="Soumettre TestFlight",
            owner_id="noah",
            priority="P0",
            due_date="2026-08-13",
            sop_path="app-store-submit.md",
        )
        self.assertTrue(ok)
        tasks = list_tasks_for_person(self.conn, "noah")
        self.assertTrue(any(task["id"] == "PIO-999" for task in tasks))


if __name__ == "__main__":
    unittest.main()

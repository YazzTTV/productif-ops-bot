import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from productif_ops_bot.db import init_db
from productif_ops_bot.messages import build_personal_plan, build_recap
from productif_ops_bot.tasks import list_tasks_for_person, recap_counts, seed_people, seed_sample_tasks


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        seed_people(self.conn)
        seed_sample_tasks(self.conn)

    def test_personal_plan_contains_task_ids(self):
        person = self.conn.execute("SELECT * FROM people WHERE id = 'noah'").fetchone()
        tasks = list_tasks_for_person(self.conn, "noah")
        text = build_personal_plan(person, tasks)
        self.assertIn("PIO-001", text)
        self.assertIn("/done PIO-001", text)

    def test_recap_contains_people(self):
        text = build_recap(recap_counts(self.conn))
        self.assertIn("Noah", text)
        self.assertIn("Gaetan", text)
        self.assertIn("Arthur", text)


if __name__ == "__main__":
    unittest.main()


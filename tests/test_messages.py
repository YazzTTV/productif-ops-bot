import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from productif_ops_bot.db import init_db
from productif_ops_bot.messages import build_evening_checkin, build_personal_plan, build_recap
from productif_ops_bot.bot import _next_task_id, _parse_admin_status_command, _parse_key_value_command
from productif_ops_bot.messages import build_task_detail, build_task_list
from productif_ops_bot.tasks import (
    admin_update_task_status,
    assign_task,
    create_task,
    get_task,
    get_task_with_owner,
    list_checkins,
    list_tasks,
    list_tasks_for_person,
    recap_counts,
    seed_people,
    seed_sample_tasks,
)


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

    def test_parse_admin_status_command(self):
        parsed = _parse_admin_status_command("/setstatus PIO-001 done proof: handled manually")
        self.assertEqual(parsed, ("PIO-001", "done", "proof: handled manually"))

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

    def test_list_tasks_can_filter_owner(self):
        tasks = list_tasks(self.conn, status_filter="open", owner_id="gaetan")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["owner_name"], "Gaetan")
        self.assertIn("Gaetan", build_task_list("Taches open - gaetan", tasks))

    def test_admin_can_update_any_task_status(self):
        ok = admin_update_task_status(
            self.conn,
            task_id="PIO-010",
            person_id="noah",
            status="done",
            message="proof: admin handled",
            proof="proof: admin handled",
        )
        self.assertTrue(ok)
        task = get_task(self.conn, "PIO-010")
        self.assertEqual(task["status"], "done")
        checkins = list_checkins(self.conn, "PIO-010")
        self.assertEqual(checkins[0]["person_name"], "Noah")

    def test_assign_task(self):
        ok = assign_task(self.conn, "PIO-002", "gaetan")
        self.assertTrue(ok)
        task = get_task(self.conn, "PIO-002")
        self.assertEqual(task["owner_id"], "gaetan")

    def test_task_detail_contains_checkins(self):
        admin_update_task_status(
            self.conn,
            task_id="PIO-001",
            person_id="noah",
            status="blocked",
            message="reason: waiting",
        )
        task = get_task_with_owner(self.conn, "PIO-001")
        text = build_task_detail(task, list_checkins(self.conn, "PIO-001"))
        self.assertIn("Status: blocked", text)
        self.assertIn("reason: waiting", text)

    def test_next_task_id_filters_by_owner(self):
        self.assertEqual(_next_task_id(self.conn, "gaetan"), "PIO-G-001")


if __name__ == "__main__":
    unittest.main()

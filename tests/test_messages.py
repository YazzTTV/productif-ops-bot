import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from productif_ops_bot.config import _parse_admin_ids
from productif_ops_bot.db import init_db
from productif_ops_bot.import_plan import import_plan
from productif_ops_bot.messages import build_evening_checkin, build_personal_plan, build_recap
from productif_ops_bot.bot import (
    OpsBot,
    _next_task_id,
    _parse_admin_status_command,
    _parse_key_value_command,
    _split_telegram_text,
)
from productif_ops_bot.messages import build_task_detail, build_task_list
from productif_ops_bot.scheduler import backup_database, resolve_admin_recipients
from productif_ops_bot.tasks import (
    admin_update_task_status,
    assign_task,
    create_task,
    get_task,
    get_task_with_owner,
    list_checkins,
    list_due_tasks_for_person,
    list_tasks,
    list_tasks_for_person,
    recap_counts,
    register_telegram_user,
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

    def test_import_productif_plan(self):
        seed_path = Path(__file__).resolve().parents[1] / "seeds" / "productif_plan_2026_08_10.json"
        result = import_plan(self.conn, seed_path, archive_existing_open_tasks=True)
        self.assertGreater(result["imported"], 20)
        self.assertGreater(result["archived"], 0)
        app_task = get_task(self.conn, "APP-001")
        self.assertEqual(app_task["owner_id"], "noah")
        self.assertEqual(app_task["category"], "appstore")
        sample_task = get_task(self.conn, "PIO-002")
        self.assertEqual(sample_task["status"], "cancelled")

    def test_due_tasks_only_include_today_or_overdue(self):
        seed_path = Path(__file__).resolve().parents[1] / "seeds" / "productif_plan_2026_08_10.json"
        import_plan(self.conn, seed_path, archive_existing_open_tasks=True)
        tasks = list_due_tasks_for_person(self.conn, "noah", "2026-08-10")
        task_ids = {task["id"] for task in tasks}
        self.assertIn("APP-001", task_ids)
        self.assertIn("DEV-001", task_ids)
        self.assertNotIn("APP-003", task_ids)

    def test_parse_admin_ids_drops_placeholders(self):
        self.assertEqual(_parse_admin_ids("0"), ())
        self.assertEqual(_parse_admin_ids(""), ())
        self.assertEqual(_parse_admin_ids("nope"), ())
        self.assertEqual(_parse_admin_ids("0, 123, -5, 123"), (123,))

    def test_enroll_code_gate(self):
        guarded = OpsBot(self.conn, Path("."), enroll_code="rentree2026")
        self.assertFalse(guarded._enroll_code_matches(["gaetan"]))
        self.assertFalse(guarded._enroll_code_matches(["gaetan", "wrong"]))
        self.assertTrue(guarded._enroll_code_matches(["gaetan", "rentree2026"]))
        self.assertIn("CODE", guarded._start_usage())

        open_bot = OpsBot(self.conn, Path("."))
        self.assertEqual(open_bot.enroll_code, "")
        self.assertNotIn("CODE", open_bot._start_usage())

    def test_admin_recipients_fall_back_to_noah(self):
        register_telegram_user(self.conn, "noah", 4242)
        self.assertEqual(resolve_admin_recipients(self.conn, ()), (4242,))
        self.assertEqual(resolve_admin_recipients(self.conn, (99,)), (99,))

    def test_admin_recipients_empty_without_linked_noah(self):
        self.assertEqual(resolve_admin_recipients(self.conn, ()), ())

    def test_backup_database_creates_snapshot_and_prunes(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "productif_ops.sqlite"
            database_path.touch()
            backup_dir = database_path.parent / "backups"
            backup_dir.mkdir()
            for day in range(3):
                (backup_dir / f"productif_ops-2026-01-0{day + 1}.sqlite").touch()

            target = backup_database(self.conn, database_path, keep=2)

            self.assertTrue(target.is_file())
            snapshots = sorted(backup_dir.glob("productif_ops-*.sqlite"))
            self.assertEqual(len(snapshots), 2)
            self.assertIn(target, snapshots)

            restored = sqlite3.connect(target)
            try:
                restored.row_factory = sqlite3.Row
                people = {row["id"] for row in restored.execute("SELECT id FROM people")}
            finally:
                restored.close()
            self.assertEqual(people, {"noah", "gaetan", "arthur"})

    def test_split_telegram_text_keeps_chunks_under_limit(self):
        text = "\n".join(f"line {i} " + ("x" * 100) for i in range(100))
        chunks = _split_telegram_text(text, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))
        self.assertIn("line 0", chunks[0])


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from productif_ops_bot.api import ApiError, OpsApiService, make_handler
from productif_ops_bot.auth import authenticate_api_token, create_api_token, revoke_api_token
from productif_ops_bot.db import connect, init_db
from productif_ops_bot.tasks import create_task, get_task, seed_people


class SyncApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database_path = self.root / "ops.sqlite"
        (self.root / "sops").mkdir()
        (self.root / "sops" / "gaetan.md").write_text("# SOP Gaetan\n\nDeliver C01-C08.", encoding="utf-8")

        conn = connect(self.database_path)
        init_db(conn)
        seed_people(conn)
        create_task(
            conn,
            task_id="CONT-TEST",
            title="Deliver carousels",
            owner_id="gaetan",
            priority="P0",
            due_date="2026-08-10",
            sop_path="gaetan.md",
            proof_required=True,
        )
        create_task(
            conn,
            task_id="ART-TEST",
            title="Ship iOS build",
            owner_id="arthur",
            priority="P0",
            due_date="2026-08-10",
        )
        conn.execute("UPDATE people SET telegram_user_id = 2002 WHERE id = 'gaetan'")
        conn.commit()
        self.token_id, self.token = create_api_token(conn, "gaetan", "test")
        conn.close()

        self.notifications: list[tuple[str, tuple[int, ...]]] = []
        self.service = OpsApiService(
            database_path=self.database_path,
            repo_root=self.root,
            admin_telegram_ids=(1001,),
            notifier=self._capture_notification,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _capture_notification(self, text: str, recipients: tuple[int, ...]) -> bool:
        self.notifications.append((text, recipients))
        return True

    def test_token_is_hashed_and_can_be_revoked(self) -> None:
        conn = connect(self.database_path)
        stored = conn.execute("SELECT token_hash FROM api_tokens WHERE id = ?", (self.token_id,)).fetchone()
        self.assertNotEqual(stored["token_hash"], self.token)
        self.assertEqual(authenticate_api_token(conn, self.token)["id"], "gaetan")
        self.assertTrue(revoke_api_token(conn, self.token_id))
        self.assertIsNone(authenticate_api_token(conn, self.token))
        conn.close()

    def test_personal_plan_only_returns_authenticated_person_tasks_and_sop(self) -> None:
        payload = self.service.plan(self.token, scope="mine")
        self.assertEqual(payload["person"]["id"], "gaetan")
        self.assertEqual([task["id"] for task in payload["tasks"]], ["CONT-TEST"])
        self.assertIn("Deliver C01-C08", payload["tasks"][0]["sop"])

    def test_team_plan_is_visible_to_every_associate(self) -> None:
        payload = self.service.plan(self.token, scope="team")
        self.assertEqual({task["id"] for task in payload["tasks"]}, {"CONT-TEST", "ART-TEST"})
        owners = {task["id"]: task["owner"]["id"] for task in payload["tasks"]}
        self.assertEqual(owners, {"CONT-TEST": "gaetan", "ART-TEST": "arthur"})

    def test_done_requires_proof_without_partial_write(self) -> None:
        with self.assertRaisesRegex(ApiError, "requires proof"):
            self.service.submit(
                self.token,
                {
                    "updates": [
                        {"task_id": "CONT-TEST", "status": "done", "message": "", "proof": ""},
                    ],
                    "summary": "Finished",
                    "workspace": {"repo": "content"},
                },
            )

        conn = connect(self.database_path)
        self.assertEqual(get_task(conn, "CONT-TEST")["status"], "todo")
        self.assertEqual(conn.execute("SELECT COUNT(*) AS count FROM sync_runs").fetchone()["count"], 0)
        conn.close()

    def test_submit_updates_database_and_notifies_telegram_targets(self) -> None:
        result = self.service.submit(
            self.token,
            {
                "updates": [
                    {
                        "task_id": "CONT-TEST",
                        "status": "done",
                        "message": "Delivered",
                        "proof": "Buffer URL + C01-C08 exports",
                    }
                ],
                "summary": "Carousels delivered",
                "workspace": {"repo": "content", "branch": "main", "commit": "abc1234"},
            },
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["telegram_notified"])
        self.assertEqual(result["updates"][0]["status"], "done")
        self.assertEqual(self.notifications[0][1], (1001, 2002))
        self.assertIn("CONT-TEST -> done", self.notifications[0][0])

        conn = connect(self.database_path)
        self.assertEqual(get_task(conn, "CONT-TEST")["status"], "done")
        checkin = conn.execute("SELECT * FROM checkins WHERE task_id = 'CONT-TEST'").fetchone()
        self.assertEqual(checkin["sync_run_id"], result["sync_run_id"])
        conn.close()

    def test_cannot_update_another_person_task(self) -> None:
        with self.assertRaisesRegex(ApiError, "not assigned"):
            self.service.submit(
                self.token,
                {
                    "updates": [
                        {"task_id": "ART-TEST", "status": "in_progress", "message": "Started", "proof": ""}
                    ]
                },
            )

    def test_http_and_skill_client_end_to_end(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.service))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            api_url = f"http://127.0.0.1:{server.server_port}"
            config_path = self.root / "client-config.json"
            config_path.write_text(
                json.dumps({"api_url": api_url, "person": "gaetan", "token": self.token}),
                encoding="utf-8",
            )
            script = (
                Path(__file__).resolve().parents[1]
                / "skills"
                / "sync-productif-ops"
                / "scripts"
                / "productif_ops_sync.py"
            )
            env = os.environ.copy()
            env["PRODUCTIF_OPS_CONFIG"] = str(config_path)

            plan = subprocess.run(
                [sys.executable, str(script), "plan", "--json"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertIn('"CONT-TEST"', plan.stdout)
            self.assertIn('"ART-TEST"', plan.stdout)

            command = [
                sys.executable,
                str(script),
                "submit",
                "--workspace",
                str(self.root),
                "--done",
                "CONT-TEST",
                "--proof",
                "CONT-TEST=Export files and Buffer URL",
                "--summary",
                "Delivered",
            ]
            dry_run = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
            self.assertIn("DRY RUN - nothing was sent", dry_run.stdout)
            conn = connect(self.database_path)
            self.assertEqual(get_task(conn, "CONT-TEST")["status"], "todo")
            conn.close()

            confirmed = subprocess.run(
                [*command, "--confirm"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertIn('"telegram_notified": true', confirmed.stdout)
            conn = connect(self.database_path)
            self.assertEqual(get_task(conn, "CONT-TEST")["status"], "done")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()

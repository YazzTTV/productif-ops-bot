from __future__ import annotations

import json
import logging
import sqlite3
import urllib.error
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .auth import authenticate_api_token
from .config import ApiConfig, load_api_config
from .db import connect, init_db
from .tasks import (
    CheckinValidationError,
    apply_checkin_batch,
    list_due_tasks_for_person,
    list_tasks,
    list_tasks_for_person,
    seed_people,
)

LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 64 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class OpsApiService:
    def __init__(
        self,
        database_path: Path,
        repo_root: Path,
        telegram_bot_token: str = "",
        admin_telegram_ids: tuple[int, ...] = (),
        notifier: Callable[[str, tuple[int, ...]], bool] | None = None,
    ) -> None:
        self.database_path = database_path
        self.repo_root = repo_root
        self.telegram_bot_token = telegram_bot_token
        self.admin_telegram_ids = admin_telegram_ids
        self.notifier = notifier

    def health(self) -> dict[str, object]:
        return {"ok": True, "service": "productif-ops-api"}

    def plan(self, raw_token: str, scope: str = "mine") -> dict[str, object]:
        conn = connect(self.database_path)
        try:
            person = self._authenticate(conn, raw_token)
            if scope == "due":
                rows = list_due_tasks_for_person(conn, person["id"], date.today().isoformat())
            elif scope == "mine":
                rows = list_tasks_for_person(conn, person["id"])
            elif scope == "team":
                rows = list_tasks(conn, status_filter="open")
            else:
                raise ApiError(400, "Scope must be team, mine, or due.")
            return {
                "person": {"id": person["id"], "name": person["name"]},
                "date": date.today().isoformat(),
                "scope": scope,
                "tasks": [self._serialize_task(row) for row in rows],
            }
        finally:
            conn.close()

    def submit(self, raw_token: str, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ApiError(400, "The JSON body must be an object.")

        updates = payload.get("updates")
        summary = payload.get("summary", "")
        workspace = payload.get("workspace", {})
        if not isinstance(updates, list):
            raise ApiError(400, "The updates field must be an array.")
        if not isinstance(summary, str):
            raise ApiError(400, "The summary field must be a string.")
        if not isinstance(workspace, dict):
            raise ApiError(400, "The workspace field must be an object.")

        conn = connect(self.database_path)
        try:
            person = self._authenticate(conn, raw_token)
            try:
                result = apply_checkin_batch(
                    conn,
                    person_id=person["id"],
                    updates=updates,
                    summary=summary,
                    workspace=workspace,
                )
            except CheckinValidationError as exc:
                raise ApiError(422, str(exc)) from exc

            recipients = self._notification_recipients(person)
            notification = _build_sync_notification(person["name"], result["updates"], summary, workspace)
            telegram_notified = self._notify(notification, recipients)
            return {
                "ok": True,
                "person": person["id"],
                "sync_run_id": result["sync_run_id"],
                "updates": result["updates"],
                "telegram_notified": telegram_notified,
            }
        finally:
            conn.close()

    def _authenticate(self, conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row:
        person = authenticate_api_token(conn, raw_token)
        if not person:
            raise ApiError(401, "Invalid or revoked API token.")
        return person

    def _serialize_task(self, task: sqlite3.Row) -> dict[str, object]:
        owner_name = task["owner_name"] if "owner_name" in task.keys() else task["owner_id"].title()
        return {
            "id": task["id"],
            "title": task["title"],
            "description": task["description"],
            "priority": task["priority"],
            "status": task["status"],
            "due_date": task["due_date"],
            "category": task["category"],
            "proof_required": bool(task["proof_required"]),
            "owner": {"id": task["owner_id"], "name": owner_name},
            "sop_path": task["sop_path"],
            "sop": self._load_sop(task["sop_path"]),
        }

    def _load_sop(self, sop_path: str | None) -> str:
        if not sop_path:
            return ""
        sop_root = (self.repo_root / "sops").resolve()
        path = (sop_root / sop_path).resolve()
        if not path.is_relative_to(sop_root) or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[:12000]

    def _notification_recipients(self, person: sqlite3.Row) -> tuple[int, ...]:
        recipients = list(self.admin_telegram_ids)
        if person["telegram_user_id"] is not None:
            recipients.append(int(person["telegram_user_id"]))
        return tuple(dict.fromkeys(recipients))

    def _notify(self, text: str, recipients: tuple[int, ...]) -> bool:
        if not recipients:
            return False
        if self.notifier:
            return self.notifier(text, recipients)
        if not self.telegram_bot_token:
            return False

        success = True
        for chat_id in recipients:
            body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
            request = urllib.request.Request(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    success = success and response.status == 200
            except (urllib.error.URLError, TimeoutError):
                LOGGER.exception("Could not send Telegram sync notification to chat %s", chat_id)
                success = False
        return success


def _build_sync_notification(
    person_name: str,
    updates: object,
    summary: str,
    workspace: dict[str, object],
) -> str:
    lines = [f"Sync dossier - {person_name}", ""]
    if isinstance(updates, list):
        for update in updates:
            if not isinstance(update, dict):
                continue
            lines.append(f"- {update.get('task_id')} -> {update.get('status')}: {update.get('title')}")
            detail = update.get("proof") or update.get("message")
            if detail:
                lines.append(f"  {detail}")
    if summary:
        lines.extend(["", f"Resume: {summary}"])

    repo = workspace.get("repo") or workspace.get("workspace")
    branch = workspace.get("branch")
    commit = workspace.get("commit")
    evidence = " / ".join(str(value) for value in (repo, branch, commit) if value)
    if evidence:
        lines.extend(["", f"Source: {evidence}"])
    return "\n".join(lines)[:3900]


def _extract_bearer_token(header: str | None) -> str:
    if not header or not header.startswith("Bearer "):
        return ""
    return header[7:].strip()


def make_handler(service: OpsApiService) -> type[BaseHTTPRequestHandler]:
    class OpsApiHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._write_json(200, service.health())
                    return
                if parsed.path == "/v1/plan":
                    query = parse_qs(parsed.query)
                    scope = query.get("scope", ["mine"])[0]
                    token = _extract_bearer_token(self.headers.get("Authorization"))
                    self._write_json(200, service.plan(token, scope=scope))
                    return
                raise ApiError(404, "Route not found.")
            except ApiError as exc:
                self._write_json(exc.status, {"ok": False, "error": exc.message})
            except Exception:
                LOGGER.exception("Unhandled API GET error")
                self._write_json(500, {"ok": False, "error": "Internal server error."})

        def do_POST(self) -> None:
            try:
                parsed = urlparse(self.path)
                if parsed.path != "/v1/checkins":
                    raise ApiError(404, "Route not found.")

                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                    raise ApiError(413, "Request body is empty or too large.")
                try:
                    payload = json.loads(self.rfile.read(content_length))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ApiError(400, "Invalid JSON body.") from exc

                token = _extract_bearer_token(self.headers.get("Authorization"))
                self._write_json(200, service.submit(token, payload))
            except ApiError as exc:
                self._write_json(exc.status, {"ok": False, "error": exc.message})
            except Exception:
                LOGGER.exception("Unhandled API POST error")
                self._write_json(500, {"ok": False, "error": "Internal server error."})

        def _write_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("API %s - %s", self.address_string(), format % args)

    return OpsApiHandler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repo_root = Path(__file__).resolve().parents[2]
    config: ApiConfig = load_api_config()

    conn = connect(config.database_path)
    try:
        init_db(conn)
        seed_people(conn)
    finally:
        conn.close()

    service = OpsApiService(
        database_path=config.database_path,
        repo_root=repo_root,
        telegram_bot_token=config.telegram_bot_token,
        admin_telegram_ids=config.admin_telegram_ids,
    )
    server = ThreadingHTTPServer((config.host, config.port), make_handler(service))
    LOGGER.info("Productif Ops API listening on http://%s:%s", config.host, config.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

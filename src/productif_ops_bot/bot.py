from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .messages import build_personal_plan, build_recap, build_task_detail, build_task_list, load_sop_text
from .tasks import (
    VALID_PEOPLE,
    VALID_STATUSES,
    admin_update_task_status,
    assign_task,
    create_task,
    get_person_by_telegram,
    get_task,
    get_task_with_owner,
    list_checkins,
    list_due_tasks_for_person,
    list_tasks,
    list_tasks_for_person,
    recap_counts,
    register_telegram_user,
    update_task_status,
)


class OpsBot:
    def __init__(self, conn: sqlite3.Connection, repo_root: Path) -> None:
        self.conn = conn
        self.repo_root = repo_root

    def register_handlers(self, application: Application) -> None:
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("plan", self.plan))
        application.add_handler(CommandHandler("tasks", self.tasks))
        application.add_handler(CommandHandler("task", self.task))
        application.add_handler(CommandHandler("done", self.done))
        application.add_handler(CommandHandler("blocked", self.blocked))
        application.add_handler(CommandHandler("notdone", self.notdone))
        application.add_handler(CommandHandler("setstatus", self.setstatus))
        application.add_handler(CommandHandler("assign", self.assign))
        application.add_handler(CommandHandler("recap", self.recap))
        application.add_handler(CommandHandler("sop", self.sop))
        application.add_handler(CommandHandler("addtask", self.addtask))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return

        if not context.args:
            await update.message.reply_text("Usage: /start noah | /start gaetan | /start arthur")
            return

        person_id = context.args[0].lower().strip()
        ok = register_telegram_user(self.conn, person_id, update.effective_user.id)
        if not ok:
            await update.message.reply_text("Impossible de lier ce compte. Verifie le nom ou l'utilisateur deja lie.")
            return

        await update.message.reply_text(f"Compte Telegram lie a {person_id}. Envoie /plan.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await self._reply_long_text(
            update,
            "\n".join(
                [
                    "Commandes Productif Ops",
                    "",
                    "/plan - ton plan ouvert",
                    "/tasks [open|all|done|blocked|not_done|todo] [noah|gaetan|arthur]",
                    "/task PIO-001 - detail d'une tache",
                    "/done PIO-001 proof: ...",
                    "/blocked PIO-001 reason: ...",
                    "/notdone PIO-001 reason: ...",
                    "/sop PIO-001",
                    "/recap",
                    "",
                    "Admin Noah:",
                    "/addtask owner:noah title:... priority:P0 due:2026-08-13 sop:...",
                    "/setstatus PIO-001 done proof: ...",
                    "/assign PIO-001 gaetan",
                ]
            ),
        )

    async def plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return

        tasks = list_due_tasks_for_person(self.conn, person["id"], date.today().isoformat())
        await self._reply_long_text(update, build_personal_plan(person, tasks))

    async def tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        status_filter = "open"
        owner_id = None
        for arg in context.args:
            normalized = arg.lower().strip()
            if normalized in VALID_PEOPLE:
                owner_id = normalized
            else:
                status_filter = normalized

        rows = list_tasks(self.conn, status_filter=status_filter, owner_id=owner_id)
        if status_filter not in {"open", "all", *VALID_STATUSES}:
            await update.message.reply_text("Filtre invalide. Usage: /tasks [open|all|done|blocked|not_done|todo] [owner]")
            return

        owner_label = f" - {owner_id}" if owner_id else ""
        await self._reply_long_text(update, build_task_list(f"Taches {status_filter}{owner_label}", rows))

    async def task(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not context.args:
            await update.message.reply_text("Usage: /task PIO-001")
            return

        task = get_task_with_owner(self.conn, context.args[0].upper().strip())
        if not task:
            await update.message.reply_text("Tache introuvable.")
            return

        checkins = list_checkins(self.conn, task["id"])
        await self._reply_long_text(update, build_task_detail(task, checkins))

    async def done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "done")

    async def blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "blocked")

    async def notdone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "not_done")

    async def setstatus(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return
        if not self._is_admin(person):
            await update.message.reply_text("Commande reservee a Noah pour le MVP.")
            return

        parsed = _parse_admin_status_command(update.message.text or "")
        if not parsed:
            await update.message.reply_text("Usage: /setstatus PIO-001 done proof: ...")
            return

        task_id, status, message = parsed
        ok = admin_update_task_status(
            self.conn,
            task_id=task_id,
            person_id=person["id"],
            status=status,
            message=message,
            proof=message if status == "done" else "",
        )
        if not ok:
            await update.message.reply_text("Statut invalide ou tache introuvable.")
            return

        await update.message.reply_text(f"{task_id} -> {status}.")

    async def assign(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return
        if not self._is_admin(person):
            await update.message.reply_text("Commande reservee a Noah pour le MVP.")
            return
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /assign PIO-001 gaetan")
            return

        task_id = context.args[0].upper().strip()
        owner_id = context.args[1].lower().strip()
        ok = assign_task(self.conn, task_id=task_id, owner_id=owner_id)
        if not ok:
            await update.message.reply_text("Tache introuvable ou owner invalide.")
            return

        await update.message.reply_text(f"{task_id} assignee a {owner_id}.")

    async def recap(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await self._reply_long_text(update, build_recap(recap_counts(self.conn)))

    async def sop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not context.args:
            await update.message.reply_text("Usage: /sop PIO-001")
            return

        task = get_task(self.conn, context.args[0].upper().strip())
        if not task:
            await update.message.reply_text("Tache introuvable.")
            return

        sop_text = load_sop_text(self.repo_root, task["sop_path"])
        if not sop_text:
            await update.message.reply_text("Aucune SOP trouvee pour cette tache.")
            return

        await self._reply_long_text(update, sop_text)

    async def addtask(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return

        if not self._is_admin(person):
            await update.message.reply_text("Commande reservee a Noah pour le MVP.")
            return

        fields = _parse_key_value_command(update.message.text or "")
        required = {"owner", "title", "priority", "due"}
        missing = sorted(required - fields.keys())
        if missing:
            await update.message.reply_text(
                "Champs manquants: "
                + ", ".join(missing)
                + "\nUsage: /addtask owner:noah title:Soumettre TestFlight priority:P0 due:2026-08-13 sop:app-store-submit.md"
            )
            return

        owner = fields["owner"].lower()
        priority = fields["priority"].upper()
        due = fields["due"]
        task_id = fields.get("id") or _next_task_id(self.conn, owner)
        sop = fields.get("sop")
        proof_required = fields.get("proof", "false").lower() in {"1", "true", "yes", "required"}

        ok = create_task(
            self.conn,
            task_id=task_id,
            title=fields["title"],
            owner_id=owner,
            priority=priority,
            due_date=due,
            sop_path=sop,
            description=fields.get("description", ""),
            proof_required=proof_required,
        )
        if not ok:
            await update.message.reply_text("Impossible de creer la tache. Verifie owner, priority ou id deja existant.")
            return

        await update.message.reply_text(f"Tache creee: {task_id} -> {owner} [{priority}] {fields['title']}")

    async def _set_status(self, update: Update, status: str) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return

        text = update.message.text or ""
        parsed = _parse_status_command(text)
        if not parsed:
            await update.message.reply_text("Usage: /done PIO-001 proof: ...")
            return

        task_id, message = parsed
        ok = update_task_status(
            self.conn,
            task_id=task_id,
            person_id=person["id"],
            status=status,
            message=message,
            proof=message if status == "done" else "",
        )
        if not ok:
            await update.message.reply_text("Tache introuvable ou non assignee a toi.")
            return

        await update.message.reply_text(f"{task_id} -> {status}.")

    def _current_person(self, update: Update) -> sqlite3.Row | None:
        if not update.effective_user:
            return None
        return get_person_by_telegram(self.conn, update.effective_user.id)

    def _is_admin(self, person: sqlite3.Row) -> bool:
        return person["id"] == "noah"

    async def _reply_unregistered(self, update: Update) -> None:
        if update.message:
            await update.message.reply_text("Compte non lie. Envoie /start noah, /start gaetan ou /start arthur.")

    async def _reply_long_text(self, update: Update, text: str) -> None:
        if not update.message:
            return
        for chunk in _split_telegram_text(text):
            await update.message.reply_text(chunk)


def _parse_status_command(text: str) -> tuple[str, str] | None:
    match = re.match(r"^/\w+\s+([A-Za-z0-9-]+)\s*(.*)$", text.strip(), flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).upper(), match.group(2).strip()


def _split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in text.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > limit:
            chunks.append("\n".join(current))
            current = []
            current_length = 0

        if line_length > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            chunks.extend(line[start : start + limit] for start in range(0, len(line), limit))
            continue

        current.append(line)
        current_length += line_length

    if current:
        chunks.append("\n".join(current))
    return chunks


def _parse_admin_status_command(text: str) -> tuple[str, str, str] | None:
    match = re.match(r"^/\w+\s+([A-Za-z0-9-]+)\s+(\w+)\s*(.*)$", text.strip(), flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).upper(), match.group(2).lower(), match.group(3).strip()


def _parse_key_value_command(text: str) -> dict[str, str]:
    body = re.sub(r"^/\w+\s*", "", text.strip(), count=1)
    matches = list(re.finditer(r"(\w+):", body))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = match.group(1).lower()
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        value = body[value_start:value_end].strip()
        if value:
            fields[key] = value
    return fields


def _next_task_id(conn: sqlite3.Connection, owner_id: str) -> str:
    prefixes = {
        "noah": "PIO",
        "gaetan": "PIO-G",
        "arthur": "PIO-A",
    }
    prefix = prefixes.get(owner_id, "PIO")
    rows = conn.execute(
        "SELECT id FROM tasks WHERE owner_id = ? AND id LIKE ?",
        (owner_id, f"{prefix}-%"),
    ).fetchall()
    max_number = 0
    for row in rows:
        match = re.match(rf"^{re.escape(prefix)}-(\d+)$", row["id"])
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-{max_number + 1:03d}"

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .messages import build_personal_plan, build_recap, load_sop_text
from .tasks import (
    create_task,
    get_person_by_telegram,
    get_task,
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
        application.add_handler(CommandHandler("plan", self.plan))
        application.add_handler(CommandHandler("done", self.done))
        application.add_handler(CommandHandler("blocked", self.blocked))
        application.add_handler(CommandHandler("notdone", self.notdone))
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

    async def plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return

        tasks = list_tasks_for_person(self.conn, person["id"])
        await update.message.reply_text(build_personal_plan(person, tasks))

    async def done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "done")

    async def blocked(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "blocked")

    async def notdone(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._set_status(update, "not_done")

    async def recap(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(build_recap(recap_counts(self.conn)))

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

        await update.message.reply_text(sop_text)

    async def addtask(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        person = self._current_person(update)
        if not person or not update.message:
            await self._reply_unregistered(update)
            return

        if person["id"] != "noah":
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

    async def _reply_unregistered(self, update: Update) -> None:
        if update.message:
            await update.message.reply_text("Compte non lie. Envoie /start noah, /start gaetan ou /start arthur.")


def _parse_status_command(text: str) -> tuple[str, str] | None:
    match = re.match(r"^/\w+\s+([A-Za-z0-9-]+)\s*(.*)$", text.strip(), flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).upper(), match.group(2).strip()


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
    rows = conn.execute("SELECT id FROM tasks WHERE id LIKE ?", (f"{prefix}-%",)).fetchall()
    max_number = 0
    for row in rows:
        match = re.match(rf"^{re.escape(prefix)}-(\d+)$", row["id"])
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-{max_number + 1:03d}"

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from .messages import build_evening_checkin, build_personal_plan, build_recap
from .tasks import (
    get_person,
    list_due_tasks_for_person,
    list_linked_people,
    list_tasks_for_person,
    recap_counts,
)

LOGGER = logging.getLogger(__name__)
BACKUP_RETENTION = 14


def configure_scheduler(
    application: Application,
    conn: sqlite3.Connection,
    timezone: str,
    admin_telegram_ids: tuple[int, ...],
    database_path: Path | None = None,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=timezone)

    scheduler.add_job(
        send_morning_plans,
        CronTrigger(hour=8, minute=30, timezone=timezone),
        args=[application, conn],
        id="morning_plans",
        replace_existing=True,
    )
    scheduler.add_job(
        send_evening_checkins,
        CronTrigger(hour=19, minute=30, timezone=timezone),
        args=[application, conn],
        id="evening_checkins",
        replace_existing=True,
    )
    scheduler.add_job(
        send_admin_recap,
        CronTrigger(hour=20, minute=0, timezone=timezone),
        args=[application, conn, admin_telegram_ids],
        id="admin_recap",
        replace_existing=True,
    )
    if database_path is not None:
        scheduler.add_job(
            run_daily_backup,
            CronTrigger(hour=23, minute=30, timezone=timezone),
            args=[conn, database_path],
            id="daily_backup",
            replace_existing=True,
        )
    return scheduler


async def send_morning_plans(application: Application, conn: sqlite3.Connection) -> None:
    for person in list_linked_people(conn):
        tasks = list_due_tasks_for_person(conn, person["id"], date.today().isoformat())
        await application.bot.send_message(
            chat_id=person["telegram_user_id"],
            text=build_personal_plan(person, tasks),
        )


async def send_evening_checkins(application: Application, conn: sqlite3.Connection) -> None:
    for person in list_linked_people(conn):
        tasks = list_due_tasks_for_person(conn, person["id"], date.today().isoformat())
        await application.bot.send_message(
            chat_id=person["telegram_user_id"],
            text=build_evening_checkin(person, tasks),
        )


async def send_admin_recap(
    application: Application,
    conn: sqlite3.Connection,
    admin_telegram_ids: tuple[int, ...],
) -> None:
    recipients = resolve_admin_recipients(conn, admin_telegram_ids)
    if not recipients:
        LOGGER.warning("No admin recipient resolved, skipping the daily recap.")
        return
    text = build_recap(recap_counts(conn))
    for telegram_id in recipients:
        await application.bot.send_message(chat_id=telegram_id, text=text)


def resolve_admin_recipients(
    conn: sqlite3.Connection,
    admin_telegram_ids: tuple[int, ...],
) -> tuple[int, ...]:
    """Fall back to Noah's linked account when ADMIN_TELEGRAM_IDS is unset.

    Without this the recap silently depended on a `.env` value that is easy to
    leave empty or fill with a placeholder.
    """
    if admin_telegram_ids:
        return admin_telegram_ids
    noah = get_person(conn, "noah")
    if noah is not None and noah["telegram_user_id"] is not None:
        return (int(noah["telegram_user_id"]),)
    return ()


async def run_daily_backup(conn: sqlite3.Connection, database_path: Path) -> None:
    try:
        target = backup_database(conn, database_path)
    except Exception:
        LOGGER.exception("Daily database backup failed")
        return
    LOGGER.info("Database backed up to %s", target)


def backup_database(
    conn: sqlite3.Connection,
    database_path: Path,
    keep: int = BACKUP_RETENTION,
) -> Path:
    """Snapshot the live database, then keep only the most recent `keep` files.

    The database is the source of truth of the whole tool and it lives on a
    machine Noah does not own, so an unattended copy is the minimum.
    """
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{database_path.stem}-{date.today().isoformat()}.sqlite"

    destination = sqlite3.connect(target)
    try:
        conn.backup(destination)
    finally:
        destination.close()

    snapshots = sorted(backup_dir.glob(f"{database_path.stem}-*.sqlite"))
    for stale in snapshots[:-keep] if keep > 0 else []:
        stale.unlink(missing_ok=True)
    return target

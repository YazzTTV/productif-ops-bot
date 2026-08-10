from __future__ import annotations

import sqlite3

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application

from .messages import build_evening_checkin, build_personal_plan, build_recap
from .tasks import list_linked_people, list_tasks_for_person, recap_counts


def configure_scheduler(
    application: Application,
    conn: sqlite3.Connection,
    timezone: str,
    admin_telegram_ids: tuple[int, ...],
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
    return scheduler


async def send_morning_plans(application: Application, conn: sqlite3.Connection) -> None:
    for person in list_linked_people(conn):
        tasks = list_tasks_for_person(conn, person["id"])
        await application.bot.send_message(
            chat_id=person["telegram_user_id"],
            text=build_personal_plan(person, tasks),
        )


async def send_evening_checkins(application: Application, conn: sqlite3.Connection) -> None:
    for person in list_linked_people(conn):
        tasks = list_tasks_for_person(conn, person["id"])
        await application.bot.send_message(
            chat_id=person["telegram_user_id"],
            text=build_evening_checkin(person, tasks),
        )


async def send_admin_recap(
    application: Application,
    conn: sqlite3.Connection,
    admin_telegram_ids: tuple[int, ...],
) -> None:
    if not admin_telegram_ids:
        return
    text = build_recap(recap_counts(conn))
    for telegram_id in admin_telegram_ids:
        await application.bot.send_message(chat_id=telegram_id, text=text)


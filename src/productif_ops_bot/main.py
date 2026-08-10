from __future__ import annotations

from pathlib import Path

from telegram.ext import ApplicationBuilder

from .bot import OpsBot
from .config import load_config
from .db import connect, init_db
from .scheduler import configure_scheduler
from .tasks import seed_people, seed_sample_tasks


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config()

    conn = connect(config.database_path)
    init_db(conn)
    seed_people(conn)
    if config.seed_sample_data:
        seed_sample_tasks(conn)

    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    OpsBot(conn, repo_root).register_handlers(application)

    scheduler = configure_scheduler(
        application=application,
        conn=conn,
        timezone=config.timezone,
        admin_telegram_ids=config.admin_telegram_ids,
    )
    scheduler.start()

    application.run_polling()


if __name__ == "__main__":
    main()


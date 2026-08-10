from __future__ import annotations

import logging
from pathlib import Path

from telegram.ext import Application, ApplicationBuilder, ContextTypes

from .bot import OpsBot
from .config import load_config
from .db import connect, init_db
from .scheduler import configure_scheduler
from .tasks import seed_people, seed_sample_tasks


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    repo_root = Path(__file__).resolve().parents[2]
    config = load_config()

    conn = connect(config.database_path)
    init_db(conn)
    seed_people(conn)
    if config.seed_sample_data:
        seed_sample_tasks(conn)

    async def post_init(application: Application) -> None:
        scheduler = configure_scheduler(
            application=application,
            conn=conn,
            timezone=config.timezone,
            admin_telegram_ids=config.admin_telegram_ids,
            database_path=config.database_path,
        )
        scheduler.start()
        application.bot_data["scheduler"] = scheduler

    async def post_shutdown(application: Application) -> None:
        scheduler = application.bot_data.get("scheduler")
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Sans ce handler, une exception dans une commande ne laisse qu'une trace
        # dans les logs du serveur et l'utilisateur croit le bot mort.
        logging.error("Unhandled bot error", exc_info=context.error)
        message = getattr(update, "message", None)
        if message is None:
            return
        try:
            await message.reply_text("Erreur interne. Le detail est dans les logs du serveur.")
        except Exception:
            logging.exception("Could not report the error back to the user")

    application = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    OpsBot(conn, repo_root, enroll_code=config.enroll_code).register_handlers(application)
    application.add_error_handler(on_error)

    if not config.enroll_code:
        logging.warning(
            "OPS_ENROLL_CODE is empty: anyone who finds this bot can claim a free identity via /start."
        )

    logging.info("Productif Ops Bot running. Press Ctrl+C to stop.")
    application.run_polling()


if __name__ == "__main__":
    main()

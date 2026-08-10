from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    timezone: str
    database_path: Path
    admin_telegram_ids: tuple[int, ...]
    seed_sample_data: bool


def _parse_admin_ids(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    ids: list[int] = []
    for raw_id in value.split(","):
        raw_id = raw_id.strip()
        if raw_id:
            ids.append(int(raw_id))
    return tuple(ids)


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Copy .env.example to .env and fill it.")

    return Config(
        telegram_bot_token=token,
        timezone=os.getenv("TIMEZONE", "Europe/Paris"),
        database_path=Path(os.getenv("DATABASE_PATH", "data/productif_ops.sqlite")),
        admin_telegram_ids=_parse_admin_ids(os.getenv("ADMIN_TELEGRAM_IDS", "")),
        seed_sample_data=os.getenv("SEED_SAMPLE_DATA", "true").lower() in {"1", "true", "yes"},
    )


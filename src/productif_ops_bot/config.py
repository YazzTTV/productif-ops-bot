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
    enroll_code: str


@dataclass(frozen=True)
class ApiConfig:
    database_path: Path
    host: str
    port: int
    telegram_bot_token: str
    admin_telegram_ids: tuple[int, ...]


def _parse_admin_ids(value: str) -> tuple[int, ...]:
    """Parse a comma separated list of Telegram ids.

    Placeholders such as `0` are dropped: a chat id of 0 does not exist, and
    keeping it made every scheduled recap fail with a Telegram 400.
    """
    if not value.strip():
        return ()
    ids: list[int] = []
    for raw_id in value.split(","):
        raw_id = raw_id.strip()
        if not raw_id:
            continue
        try:
            parsed = int(raw_id)
        except ValueError:
            continue
        if parsed > 0:
            ids.append(parsed)
    return tuple(dict.fromkeys(ids))


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
        enroll_code=os.getenv("OPS_ENROLL_CODE", "").strip(),
    )


def load_api_config() -> ApiConfig:
    load_dotenv()
    return ApiConfig(
        database_path=Path(os.getenv("DATABASE_PATH", "data/productif_ops.sqlite")),
        host=os.getenv("OPS_API_HOST", "127.0.0.1").strip(),
        port=int(os.getenv("OPS_API_PORT", "8787")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        admin_telegram_ids=_parse_admin_ids(os.getenv("ADMIN_TELEGRAM_IDS", "")),
    )


def load_database_path() -> Path:
    load_dotenv()
    return Path(os.getenv("DATABASE_PATH", "data/productif_ops.sqlite"))

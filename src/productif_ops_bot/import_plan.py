from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import load_config
from .db import connect, init_db
from .tasks import OPEN_STATUSES, seed_people, upsert_task


DEFAULT_SEED_PATH = Path("seeds/productif_plan_2026_08_10.json")


def import_plan(conn: sqlite3.Connection, seed_path: Path, archive_existing_open_tasks: bool | None = None) -> dict[str, int]:
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    tasks: list[dict[str, Any]] = payload["tasks"]
    seed_ids = {task["id"] for task in tasks}

    archived = 0
    should_archive = payload.get("archive_existing_open_tasks", False)
    if archive_existing_open_tasks is not None:
        should_archive = archive_existing_open_tasks

    if should_archive:
        archived = archive_open_tasks_not_in_seed(conn, seed_ids)

    imported = 0
    skipped = 0
    for task in tasks:
        ok = upsert_task(
            conn,
            task_id=task["id"],
            title=task["title"],
            owner_id=task["owner"],
            priority=task["priority"],
            due_date=task["due"],
            sop_path=task.get("sop"),
            description=task.get("description", ""),
            proof_required=task.get("proof_required", False),
            category=task.get("category", ""),
            source=task.get("source", payload.get("name", "")),
            source_path=task.get("source_path", ""),
            status=task.get("status", "todo"),
        )
        if ok:
            imported += 1
        else:
            skipped += 1

    return {"imported": imported, "skipped": skipped, "archived": archived}


def archive_open_tasks_not_in_seed(conn: sqlite3.Connection, seed_ids: set[str]) -> int:
    placeholders = ",".join("?" for _ in seed_ids)
    params: list[str] = [*OPEN_STATUSES]
    status_placeholders = ",".join("?" for _ in OPEN_STATUSES)

    if seed_ids:
        where_not_in = f"AND id NOT IN ({placeholders})"
        params.extend(sorted(seed_ids))
    else:
        where_not_in = ""

    cursor = conn.execute(
        f"""
        UPDATE tasks
        SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
        WHERE status IN ({status_placeholders})
        {where_not_in}
        """,
        tuple(params),
    )
    conn.commit()
    return cursor.rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the productif.io operational plan into SQLite.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED_PATH), help="Path to the plan JSON seed.")
    parser.add_argument("--archive-open", action="store_true", help="Archive open tasks not present in the seed.")
    parser.add_argument("--no-archive-open", action="store_true", help="Do not archive open tasks not present in the seed.")
    args = parser.parse_args()

    archive_override = None
    if args.archive_open:
        archive_override = True
    if args.no_archive_open:
        archive_override = False

    config = load_config()
    conn = connect(config.database_path)
    init_db(conn)
    seed_people(conn)
    result = import_plan(conn, Path(args.seed), archive_existing_open_tasks=archive_override)
    conn.close()

    print(
        "Plan import complete: "
        f"{result['imported']} imported, {result['skipped']} skipped, {result['archived']} archived."
    )


if __name__ == "__main__":
    main()


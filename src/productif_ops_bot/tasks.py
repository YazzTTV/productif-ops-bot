from __future__ import annotations

import sqlite3
from datetime import date
from typing import Iterable

VALID_PEOPLE = {
    "noah": ("Noah", "Founder"),
    "gaetan": ("Gaetan", "Content / Ops"),
    "arthur": ("Arthur", "Product / Growth"),
}

VALID_STATUSES = {"todo", "in_progress", "done", "blocked", "not_done", "cancelled"}
VALID_PRIORITIES = {"P0", "P1", "P2"}


def seed_people(conn: sqlite3.Connection) -> None:
    for person_id, (name, role) in VALID_PEOPLE.items():
        conn.execute(
            """
            INSERT INTO people (id, name, role)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (person_id, name, role),
        )
    conn.commit()


def seed_sample_tasks(conn: sqlite3.Connection) -> None:
    today = date.today().isoformat()
    sample_tasks = [
        (
            "PIO-001",
            "Tester Mode Examen sur iPhone",
            "Verifier que le bouton demarre une vraie session Mode Examen.",
            "noah",
            "P0",
            today,
            "mode-examen-test-device.md",
            1,
        ),
        (
            "PIO-002",
            "Corriger la date de l'offre rentree",
            "Eviter une promesse publique intenable avant soumission App Store.",
            "noah",
            "P0",
            today,
            "app-store-submit.md",
            1,
        ),
        (
            "PIO-010",
            "Confirmer acces Buffer",
            "Dire si Buffer est accessible et envoyer une preuve ou un blocage.",
            "gaetan",
            "P0",
            today,
            "buffer-carrousel.md",
            1,
        ),
        (
            "PIO-020",
            "Lire l'etat des lieux productif.io",
            "Preparer le retour operationnel du 16 aout.",
            "arthur",
            "P1",
            today,
            "tiktok-business-setup.md",
            0,
        ),
    ]
    for task in sample_tasks:
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, description, owner_id, priority, due_date, sop_path, proof_required
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            task,
        )
    conn.commit()


def register_telegram_user(conn: sqlite3.Connection, person_id: str, telegram_user_id: int) -> bool:
    if person_id not in VALID_PEOPLE:
        return False

    existing = conn.execute(
        "SELECT telegram_user_id FROM people WHERE id = ?",
        (person_id,),
    ).fetchone()

    if existing and existing["telegram_user_id"] not in (None, telegram_user_id):
        return False

    conn.execute(
        """
        UPDATE people
        SET telegram_user_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (telegram_user_id, person_id),
    )
    conn.commit()
    return True


def get_person_by_telegram(conn: sqlite3.Connection, telegram_user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM people WHERE telegram_user_id = ? AND active = 1",
        (telegram_user_id,),
    ).fetchone()


def list_linked_people(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM people
        WHERE telegram_user_id IS NOT NULL AND active = 1
        ORDER BY id
        """
    ).fetchall()


def list_tasks_for_person(conn: sqlite3.Connection, person_id: str, only_open: bool = True) -> list[sqlite3.Row]:
    statuses = ("todo", "in_progress", "blocked") if only_open else tuple(VALID_STATUSES)
    placeholders = ",".join("?" for _ in statuses)
    return conn.execute(
        f"""
        SELECT * FROM tasks
        WHERE owner_id = ? AND status IN ({placeholders})
        ORDER BY
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            due_date ASC,
            id ASC
        """,
        (person_id, *statuses),
    ).fetchall()


def list_all_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT tasks.*, people.name AS owner_name
        FROM tasks
        JOIN people ON people.id = tasks.owner_id
        ORDER BY
            CASE tasks.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            tasks.due_date ASC,
            tasks.id ASC
        """
    ).fetchall()


def get_task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def create_task(
    conn: sqlite3.Connection,
    task_id: str,
    title: str,
    owner_id: str,
    priority: str,
    due_date: str,
    sop_path: str | None = None,
    description: str = "",
    proof_required: bool = False,
) -> bool:
    if owner_id not in VALID_PEOPLE or priority not in VALID_PRIORITIES:
        return False
    if get_task(conn, task_id):
        return False

    conn.execute(
        """
        INSERT INTO tasks (
            id, title, description, owner_id, priority, due_date, sop_path, proof_required
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            title,
            description,
            owner_id,
            priority,
            due_date,
            sop_path,
            int(proof_required),
        ),
    )
    conn.commit()
    return True


def update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    person_id: str,
    status: str,
    message: str,
    proof: str = "",
) -> bool:
    if status not in VALID_STATUSES:
        return False

    task = get_task(conn, task_id)
    if not task or task["owner_id"] != person_id:
        return False

    conn.execute(
        """
        UPDATE tasks
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, task_id),
    )
    conn.execute(
        """
        INSERT INTO checkins (task_id, person_id, status, message, proof)
        VALUES (?, ?, ?, ?, ?)
        """,
        (task_id, person_id, status, message, proof),
    )
    conn.commit()
    return True


def recap_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            people.name,
            people.id AS person_id,
            SUM(CASE WHEN tasks.status = 'done' THEN 1 ELSE 0 END) AS done_count,
            SUM(CASE WHEN tasks.status = 'blocked' THEN 1 ELSE 0 END) AS blocked_count,
            SUM(CASE WHEN tasks.status = 'not_done' THEN 1 ELSE 0 END) AS not_done_count,
            SUM(CASE WHEN tasks.status IN ('todo', 'in_progress') THEN 1 ELSE 0 END) AS open_count
        FROM people
        LEFT JOIN tasks ON tasks.owner_id = people.id
        WHERE people.active = 1
        GROUP BY people.id
        ORDER BY people.id
        """
    ).fetchall()

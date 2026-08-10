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
OPEN_STATUSES = ("todo", "in_progress", "blocked")


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
    statuses = OPEN_STATUSES if only_open else tuple(VALID_STATUSES)
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


def list_due_tasks_for_person(conn: sqlite3.Connection, person_id: str, due_on_or_before: str) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in OPEN_STATUSES)
    return conn.execute(
        f"""
        SELECT * FROM tasks
        WHERE owner_id = ?
          AND status IN ({placeholders})
          AND due_date <= ?
        ORDER BY
            due_date ASC,
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            id ASC
        """,
        (person_id, *OPEN_STATUSES, due_on_or_before),
    ).fetchall()


def list_tasks(
    conn: sqlite3.Connection,
    status_filter: str = "open",
    owner_id: str | None = None,
) -> list[sqlite3.Row]:
    statuses = _statuses_for_filter(status_filter)
    if statuses is None:
        return []

    status_clause = ""
    params: list[str] = []
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        status_clause = f"AND tasks.status IN ({placeholders})"
        params.extend(statuses)

    owner_clause = ""
    if owner_id:
        owner_clause = "AND tasks.owner_id = ?"
        params.append(owner_id)

    return conn.execute(
        f"""
        SELECT tasks.*, people.name AS owner_name
        FROM tasks
        JOIN people ON people.id = tasks.owner_id
        WHERE 1 = 1
        {status_clause}
        {owner_clause}
        ORDER BY
            CASE tasks.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            tasks.due_date ASC,
            tasks.id ASC
        """,
        tuple(params),
    ).fetchall()


def list_all_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list_tasks(conn, status_filter="all")


def get_task(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def get_task_with_owner(conn: sqlite3.Connection, task_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT tasks.*, people.name AS owner_name
        FROM tasks
        JOIN people ON people.id = tasks.owner_id
        WHERE tasks.id = ?
        """,
        (task_id,),
    ).fetchone()


def list_checkins(conn: sqlite3.Connection, task_id: str, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT checkins.*, people.name AS person_name
        FROM checkins
        JOIN people ON people.id = checkins.person_id
        WHERE checkins.task_id = ?
        ORDER BY checkins.created_at DESC
        LIMIT ?
        """,
        (task_id, limit),
    ).fetchall()


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
    category: str = "",
    source: str = "",
    source_path: str = "",
) -> bool:
    if owner_id not in VALID_PEOPLE or priority not in VALID_PRIORITIES:
        return False
    if get_task(conn, task_id):
        return False

    conn.execute(
        """
        INSERT INTO tasks (
            id, title, description, owner_id, priority, due_date, sop_path,
            category, source, source_path, proof_required
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            title,
            description,
            owner_id,
            priority,
            due_date,
            sop_path,
            category,
            source,
            source_path,
            int(proof_required),
        ),
    )
    conn.commit()
    return True


def upsert_task(
    conn: sqlite3.Connection,
    task_id: str,
    title: str,
    owner_id: str,
    priority: str,
    due_date: str,
    sop_path: str | None = None,
    description: str = "",
    proof_required: bool = False,
    category: str = "",
    source: str = "",
    source_path: str = "",
    status: str = "todo",
) -> bool:
    if owner_id not in VALID_PEOPLE or priority not in VALID_PRIORITIES or status not in VALID_STATUSES:
        return False

    conn.execute(
        """
        INSERT INTO tasks (
            id, title, description, owner_id, priority, status, due_date, sop_path,
            category, source, source_path, proof_required
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            description = excluded.description,
            owner_id = excluded.owner_id,
            priority = excluded.priority,
            due_date = excluded.due_date,
            sop_path = excluded.sop_path,
            category = excluded.category,
            source = excluded.source,
            source_path = excluded.source_path,
            proof_required = excluded.proof_required,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            task_id,
            title,
            description,
            owner_id,
            priority,
            status,
            due_date,
            sop_path,
            category,
            source,
            source_path,
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


def admin_update_task_status(
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
    if not task:
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


def assign_task(conn: sqlite3.Connection, task_id: str, owner_id: str) -> bool:
    if owner_id not in VALID_PEOPLE or not get_task(conn, task_id):
        return False

    conn.execute(
        """
        UPDATE tasks
        SET owner_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (owner_id, task_id),
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


def _statuses_for_filter(status_filter: str) -> tuple[str, ...] | None:
    normalized = status_filter.lower().strip()
    if normalized == "all":
        return ()
    if normalized == "open":
        return OPEN_STATUSES
    if normalized in VALID_STATUSES:
        return (normalized,)
    return None

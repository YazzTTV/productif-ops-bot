from __future__ import annotations

import hashlib
import secrets
import sqlite3

from .tasks import VALID_PEOPLE


def create_api_token(conn: sqlite3.Connection, person_id: str, label: str = "") -> tuple[int, str]:
    if person_id not in VALID_PEOPLE:
        raise ValueError(f"Unknown person: {person_id}")

    raw_token = f"pio_{person_id}_{secrets.token_urlsafe(32)}"
    cursor = conn.execute(
        """
        INSERT INTO api_tokens (person_id, token_hash, label)
        VALUES (?, ?, ?)
        """,
        (person_id, _hash_token(raw_token), label.strip()[:120]),
    )
    conn.commit()
    return int(cursor.lastrowid), raw_token


def authenticate_api_token(conn: sqlite3.Connection, raw_token: str) -> sqlite3.Row | None:
    if not raw_token:
        return None

    row = conn.execute(
        """
        SELECT api_tokens.id AS token_id, people.*
        FROM api_tokens
        JOIN people ON people.id = api_tokens.person_id
        WHERE api_tokens.token_hash = ?
          AND api_tokens.revoked_at IS NULL
          AND people.active = 1
        """,
        (_hash_token(raw_token),),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
            (row["token_id"],),
        )
        conn.commit()
    return row


def list_api_tokens(conn: sqlite3.Connection, person_id: str | None = None) -> list[sqlite3.Row]:
    if person_id:
        return conn.execute(
            """
            SELECT id, person_id, label, created_at, last_used_at, revoked_at
            FROM api_tokens
            WHERE person_id = ?
            ORDER BY id
            """,
            (person_id,),
        ).fetchall()
    return conn.execute(
        """
        SELECT id, person_id, label, created_at, last_used_at, revoked_at
        FROM api_tokens
        ORDER BY person_id, id
        """
    ).fetchall()


def revoke_api_token(conn: sqlite3.Connection, token_id: int) -> bool:
    cursor = conn.execute(
        """
        UPDATE api_tokens
        SET revoked_at = CURRENT_TIMESTAMP
        WHERE id = ? AND revoked_at IS NULL
        """,
        (token_id,),
    )
    conn.commit()
    return cursor.rowcount == 1


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

from __future__ import annotations

import sqlite3
from pathlib import Path


def format_task_line(task: sqlite3.Row) -> str:
    sop = f" | SOP: {task['sop_path']}" if task["sop_path"] else ""
    proof = " | proof required" if task["proof_required"] else ""
    return f"- {task['id']} [{task['priority']}] {task['title']}{sop}{proof}"


def build_personal_plan(person: sqlite3.Row, tasks: list[sqlite3.Row]) -> str:
    if not tasks:
        return f"Plan du jour - {person['name']}\n\nAucune tache ouverte."

    lines = [f"Plan du jour - {person['name']}", ""]
    for task in tasks:
        lines.append(format_task_line(task))

    lines.extend(
        [
            "",
            "Reponds pendant la journee avec:",
            "/done PIO-001 proof: ...",
            "/blocked PIO-001 reason: ...",
            "/notdone PIO-001 reason: ...",
        ]
    )
    return "\n".join(lines)


def build_evening_checkin(person: sqlite3.Row, tasks: list[sqlite3.Row]) -> str:
    if not tasks:
        return f"Check-in du soir - {person['name']}\n\nAucune tache ouverte."

    lines = [f"Check-in du soir - {person['name']}", "", "Taches encore ouvertes:"]
    lines.extend(format_task_line(task) for task in tasks)
    lines.extend(
        [
            "",
            "Marque chaque tache:",
            "/done ID proof: ...",
            "/blocked ID reason: ...",
            "/notdone ID reason: ...",
        ]
    )
    return "\n".join(lines)


def build_recap(rows: list[sqlite3.Row]) -> str:
    lines = ["Recap productif.io", ""]
    for row in rows:
        lines.extend(
            [
                f"{row['name']}:",
                f"- DONE: {row['done_count'] or 0}",
                f"- BLOCKED: {row['blocked_count'] or 0}",
                f"- NOT DONE: {row['not_done_count'] or 0}",
                f"- OPEN: {row['open_count'] or 0}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def load_sop_text(repo_root: Path, sop_path: str | None) -> str | None:
    if not sop_path:
        return None
    path = repo_root / "sops" / sop_path
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > 3500:
        return text[:3500] + "\n\n[truncated]"
    return text


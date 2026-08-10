from __future__ import annotations

import sqlite3
from pathlib import Path


def format_task_line(task: sqlite3.Row) -> str:
    owner = f" @{task['owner_name']}" if "owner_name" in task.keys() else ""
    status = f" ({task['status']})" if "status" in task.keys() else ""
    category = f" #{task['category']}" if "category" in task.keys() and task["category"] else ""
    sop = f" | SOP: {task['sop_path']}" if task["sop_path"] else ""
    proof = " | proof required" if task["proof_required"] else ""
    return f"- {task['id']} [{task['priority']}]{owner}{status}{category} {task['title']}{sop}{proof}"


def build_personal_plan(person: sqlite3.Row, tasks: list[sqlite3.Row]) -> str:
    if not tasks:
        return f"Plan du jour - {person['name']}\n\nAucune tache ouverte."

    lines = [f"Plan du jour - {person['name']}", ""]
    for task in tasks:
        lines.append(format_task_line(task))

    example_id = tasks[0]["id"]
    lines.extend(
        [
            "",
            "Reponds pendant la journee avec:",
            f"/done {example_id} proof: ...",
            f"/blocked {example_id} reason: ...",
            f"/notdone {example_id} reason: ...",
        ]
    )
    return "\n".join(lines)


def build_evening_checkin(person: sqlite3.Row, tasks: list[sqlite3.Row]) -> str:
    if not tasks:
        return f"Check-in du soir - {person['name']}\n\nAucune tache ouverte."

    lines = [f"Check-in du soir - {person['name']}", "", "Taches encore ouvertes:"]
    lines.extend(format_task_line(task) for task in tasks)
    example_id = tasks[0]["id"]
    lines.extend(
        [
            "",
            "Marque chaque tache:",
            f"/done {example_id} proof: ...",
            f"/blocked {example_id} reason: ...",
            f"/notdone {example_id} reason: ...",
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


def build_task_list(title: str, tasks: list[sqlite3.Row]) -> str:
    if not tasks:
        return f"{title}\n\nAucune tache."

    lines = [title, ""]
    lines.extend(format_task_line(task) for task in tasks)
    return "\n".join(lines)


def build_task_detail(task: sqlite3.Row, checkins: list[sqlite3.Row]) -> str:
    lines = [
        f"{task['id']} - {task['title']}",
        "",
        f"Owner: {task['owner_name']}",
        f"Priority: {task['priority']}",
        f"Status: {task['status']}",
        f"Due: {task['due_date']}",
    ]
    if task["sop_path"]:
        lines.append(f"SOP: {task['sop_path']}")
    if "category" in task.keys() and task["category"]:
        lines.append(f"Category: {task['category']}")
    if "source" in task.keys() and task["source"]:
        lines.append(f"Source: {task['source']}")
    if "source_path" in task.keys() and task["source_path"]:
        lines.append(f"Source path: {task['source_path']}")
    if task["description"]:
        lines.extend(["", task["description"]])

    lines.append("")
    lines.append("Derniers check-ins:")
    if not checkins:
        lines.append("- Aucun")
    else:
        for checkin in checkins:
            message = f" - {checkin['message']}" if checkin["message"] else ""
            lines.append(f"- {checkin['created_at']} {checkin['person_name']} -> {checkin['status']}{message}")

    return "\n".join(lines)


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

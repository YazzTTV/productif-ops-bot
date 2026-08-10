#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "productif-ops" / "config.json"
VALID_PEOPLE = {"noah", "gaetan", "arthur"}
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "vendor", "dist", "build", ".next"}


class SyncClientError(RuntimeError):
    pass


def config_path() -> Path:
    configured = os.getenv("PRODUCTIF_OPS_CONFIG", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_CONFIG_PATH


def load_config() -> dict[str, str]:
    path = config_path()
    stored: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SyncClientError(f"Could not read configuration at {path}: {exc}") from exc
        if isinstance(loaded, dict):
            stored = loaded

    config = {
        "api_url": os.getenv("PRODUCTIF_OPS_API_URL", str(stored.get("api_url", ""))).strip().rstrip("/"),
        "person": os.getenv("PRODUCTIF_OPS_PERSON", str(stored.get("person", ""))).strip().lower(),
        "token": os.getenv("PRODUCTIF_OPS_TOKEN", str(stored.get("token", ""))).strip(),
    }
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise SyncClientError(
            f"Missing configuration: {', '.join(missing)}. Run the configure command first."
        )
    _validate_api_url(config["api_url"])
    if config["person"] not in VALID_PEOPLE:
        raise SyncClientError(f"Invalid configured person: {config['person']}")
    return config


def save_config(api_url: str, person: str, token: str) -> Path:
    api_url = api_url.strip().rstrip("/")
    person = person.strip().lower()
    token = token.strip()
    _validate_api_url(api_url)
    if person not in VALID_PEOPLE:
        raise SyncClientError(f"Person must be one of: {', '.join(sorted(VALID_PEOPLE))}")
    if not token:
        raise SyncClientError("Token cannot be empty.")

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"api_url": api_url, "person": person, "token": token}, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def api_request(config: dict[str, str], method: str, path: str, payload: object | None = None) -> object:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {config['token']}",
        "User-Agent": "productif-ops-sync/1.0",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{config['api_url']}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read()).get("error", str(exc))
        except (json.JSONDecodeError, AttributeError):
            error = str(exc)
        raise SyncClientError(f"Productif Ops API rejected the request: {error}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SyncClientError(f"Could not reach Productif Ops API: {exc}") from exc


def collect_workspace_evidence(workspace: Path) -> dict[str, object]:
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise SyncClientError(f"Workspace does not exist: {workspace}")

    git_root = _git(workspace, "rev-parse", "--show-toplevel")
    if git_root:
        repo_root = Path(git_root)
        status = _git(repo_root, "status", "--short")
        changed_files = [line[3:] for line in status.splitlines() if len(line) > 3][:50]
        return {
            "type": "git",
            "repo": repo_root.name,
            "branch": _git(repo_root, "branch", "--show-current"),
            "commit": _git(repo_root, "rev-parse", "--short", "HEAD"),
            "last_commit": _git(repo_root, "log", "-1", "--pretty=%s"),
            "changed_files": changed_files,
            "diff_stat": _git(repo_root, "diff", "--stat")[:4000],
            "staged_diff_stat": _git(repo_root, "diff", "--cached", "--stat")[:4000],
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    recent_files: list[tuple[float, str]] = []
    cutoff = datetime.now().timestamp() - 24 * 60 * 60
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS and not name.startswith(".")]
        for name in files:
            path = Path(root) / name
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= cutoff:
                recent_files.append((modified, str(path.relative_to(workspace))))
    recent_files.sort(reverse=True)
    return {
        "type": "folder",
        "workspace": workspace.name,
        "recent_files_24h": [path for _, path in recent_files[:50]],
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _git(workspace: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _parse_keyed_values(values: list[str], field_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SyncClientError(f"{field_name} must use TASK-ID=text format: {value}")
        task_id, text = value.split("=", 1)
        task_id = task_id.upper().strip()
        if not task_id or not text.strip():
            raise SyncClientError(f"{field_name} cannot have an empty task id or value.")
        parsed[task_id] = text.strip()
    return parsed


def build_updates(args: argparse.Namespace) -> list[dict[str, str]]:
    statuses: dict[str, str] = {}
    for status, task_ids in (
        ("done", args.done),
        ("blocked", args.blocked),
        ("not_done", args.not_done),
        ("in_progress", args.in_progress),
    ):
        for raw_task_id in task_ids:
            task_id = raw_task_id.upper().strip()
            if task_id in statuses:
                raise SyncClientError(f"Task {task_id} has more than one status.")
            statuses[task_id] = status

    if not statuses:
        raise SyncClientError("Provide at least one --done, --blocked, --not-done, or --in-progress task.")

    messages = _parse_keyed_values(args.message, "--message")
    proofs = _parse_keyed_values(args.proof, "--proof")
    unknown_details = (set(messages) | set(proofs)) - set(statuses)
    if unknown_details:
        raise SyncClientError(f"Details reference tasks without a status: {', '.join(sorted(unknown_details))}")

    return [
        {
            "task_id": task_id,
            "status": status,
            "message": messages.get(task_id, ""),
            "proof": proofs.get(task_id, ""),
        }
        for task_id, status in statuses.items()
    ]


def _validate_api_url(api_url: str) -> None:
    parsed = urlparse(api_url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}:
        return
    raise SyncClientError("API URL must use HTTPS, except for localhost development.")


def command_configure(args: argparse.Namespace) -> None:
    token = args.token or getpass.getpass("Personal Productif Ops API token: ")
    path = save_config(args.api_url, args.person, token)
    print(f"Configuration saved securely at {path}")


def command_status(_: argparse.Namespace) -> None:
    config = load_config()
    print(f"Configured as {config['person']} against {config['api_url']}")
    print(f"Credentials file: {config_path()}")


def command_plan(args: argparse.Namespace) -> None:
    config = load_config()
    scope = "due" if args.due else "mine" if args.mine else "team"
    payload = api_request(config, "GET", f"/v1/plan?scope={scope}")
    if not isinstance(payload, dict):
        raise SyncClientError("Unexpected plan response.")
    person = payload.get("person", {})
    if isinstance(person, dict) and person.get("id") != config["person"]:
        raise SyncClientError("Configured identity does not match the API token.")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"Productif Ops plan - {person.get('name', config['person'])}")
    tasks = payload.get("tasks", [])
    if not tasks:
        print("No open tasks.")
        return
    for task in tasks:
        proof = " | proof required" if task.get("proof_required") else ""
        owner = task.get("owner", {})
        owner_name = owner.get("name", "?") if isinstance(owner, dict) else "?"
        print(
            f"- {task.get('id')} [{task.get('priority')}] @{owner_name} ({task.get('status')}) "
            f"{task.get('title')} | due {task.get('due_date')}{proof}"
        )


def command_submit(args: argparse.Namespace) -> None:
    config = load_config()
    payload = {
        "updates": build_updates(args),
        "summary": args.summary.strip(),
        "workspace": collect_workspace_evidence(Path(args.workspace)),
    }
    if not args.confirm:
        print("DRY RUN - nothing was sent")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("After explicit user approval, rerun the same command with --confirm.")
        return

    result = api_request(config, "POST", "/v1/checkins", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync a Cowork folder with Productif Ops.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="Save personal API credentials.")
    configure.add_argument("--api-url", required=True)
    configure.add_argument("--person", required=True, choices=sorted(VALID_PEOPLE))
    configure.add_argument("--token", help=argparse.SUPPRESS)
    configure.set_defaults(func=command_configure)

    status = subparsers.add_parser("status", help="Show configuration without revealing the token.")
    status.set_defaults(func=command_status)

    plan = subparsers.add_parser("plan", help="Retrieve assigned Productif Ops tasks and SOPs.")
    plan_scope = plan.add_mutually_exclusive_group()
    plan_scope.add_argument("--mine", action="store_true", help="Only show my open tasks.")
    plan_scope.add_argument("--due", action="store_true", help="Only show my tasks due today or overdue.")
    plan.add_argument("--json", action="store_true", help="Include complete task and SOP data as JSON.")
    plan.set_defaults(func=command_plan)

    submit = subparsers.add_parser("submit", help="Prepare or submit an end-of-session check-in.")
    submit.add_argument("--workspace", default=".")
    submit.add_argument("--done", action="append", default=[])
    submit.add_argument("--blocked", action="append", default=[])
    submit.add_argument("--not-done", action="append", default=[])
    submit.add_argument("--in-progress", action="append", default=[])
    submit.add_argument("--message", action="append", default=[], metavar="TASK-ID=TEXT")
    submit.add_argument("--proof", action="append", default=[], metavar="TASK-ID=TEXT")
    submit.add_argument("--summary", default="")
    submit.add_argument("--confirm", action="store_true", help="Send the check-in after user approval.")
    submit.set_defaults(func=command_submit)
    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        args.func(args)
    except SyncClientError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse

from .auth import create_api_token, list_api_tokens, revoke_api_token
from .config import load_database_path
from .db import connect, init_db
from .tasks import VALID_PEOPLE, seed_people


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Productif Ops API tokens.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a token for one teammate.")
    create_parser.add_argument("person", choices=sorted(VALID_PEOPLE))
    create_parser.add_argument("--label", default="cowork")

    list_parser = subparsers.add_parser("list", help="List tokens without revealing secrets.")
    list_parser.add_argument("person", nargs="?", choices=sorted(VALID_PEOPLE))

    revoke_parser = subparsers.add_parser("revoke", help="Revoke a token by numeric id.")
    revoke_parser.add_argument("token_id", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    conn = connect(load_database_path())
    try:
        init_db(conn)
        seed_people(conn)
        if args.command == "create":
            token_id, raw_token = create_api_token(conn, args.person, args.label)
            print(f"Token {token_id} created for {args.person}. It will only be shown once:")
            print(raw_token)
            return
        if args.command == "list":
            rows = list_api_tokens(conn, args.person)
            if not rows:
                print("No API tokens.")
                return
            for row in rows:
                state = "revoked" if row["revoked_at"] else "active"
                print(
                    f"{row['id']} {row['person_id']} {state} "
                    f"label={row['label'] or '-'} last_used={row['last_used_at'] or '-'}"
                )
            return
        if args.command == "revoke":
            if not revoke_api_token(conn, args.token_id):
                raise SystemExit(f"Active token {args.token_id} not found.")
            print(f"Token {args.token_id} revoked.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

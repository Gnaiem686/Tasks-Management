#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from agent_api.auth.api_keys import ApiKeyService
from agent_api.auth.roles import ApplicationRole
from sqlalchemy import select, update
from workforce_persistence.database import Database
from workforce_persistence.models import ApiKeyPrincipal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage workforce application API keys"
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create and display a key once")
    create.add_argument("--actor-id", required=True)
    create.add_argument("--label", required=True)
    create.add_argument(
        "--role", choices=[role.value for role in ApplicationRole], required=True
    )
    create.add_argument("--environment", choices=["dev", "prod"], required=True)
    create.add_argument("--project", action="append", required=True)
    create.add_argument("--expires-days", type=int, default=30)
    commands.add_parser("list", help="list safe metadata without keys or digests")
    revoke = commands.add_parser("revoke", help="revoke by record ID")
    revoke.add_argument("record_id", type=uuid.UUID)
    return parser


def load_pepper() -> bytes:
    value = os.getenv("API_KEY_HMAC_PEPPER")
    if not value:
        raise SystemExit("API_KEY_HMAC_PEPPER is required")
    return value.encode()


async def execute(args: argparse.Namespace) -> None:
    if not args.database_url:
        raise SystemExit("--database-url or DATABASE_URL is required")
    database = Database(args.database_url)
    try:
        if args.command == "create":
            now = datetime.now(UTC)
            raw_key, generated_record = ApiKeyService(load_pepper()).generate(
                actor_id=args.actor_id,
                display_label=args.label,
                role=ApplicationRole(args.role),
                environment=args.environment,
                project_scopes=tuple(args.project),
                now=now,
                expires_at=now + timedelta(days=args.expires_days),
            )
            async with database.transaction() as session:
                session.add(
                    ApiKeyPrincipal(
                        id=uuid.uuid4(),
                        environment=generated_record.environment,
                        created_at=generated_record.created_at,
                        actor_id=generated_record.actor_id,
                        display_label=generated_record.display_label,
                        key_digest=generated_record.key_digest,
                        role=generated_record.role.value,
                        project_scopes=list(generated_record.project_scopes),
                        expires_at=generated_record.expires_at,
                    )
                )
            print("API key (shown once):")
            print(raw_key)
        elif args.command == "list":
            async with database.transaction() as session:
                records = (await session.scalars(select(ApiKeyPrincipal))).all()
                for principal in records:
                    revoked = principal.revoked_at is not None
                    print(
                        f"{principal.id} actor={principal.actor_id} "
                        f"role={principal.role} environment={principal.environment} "
                        f"revoked={revoked}"
                    )
        else:
            async with database.transaction() as session:
                await session.execute(
                    update(ApiKeyPrincipal)
                    .where(ApiKeyPrincipal.id == args.record_id)
                    .values(revoked_at=datetime.now(UTC))
                )
            print(f"revoked record {args.record_id}")
    finally:
        await database.close()


def main() -> None:
    asyncio.run(execute(build_parser().parse_args()))


if __name__ == "__main__":
    main()

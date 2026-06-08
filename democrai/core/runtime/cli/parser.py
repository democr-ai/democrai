from __future__ import annotations

import argparse
import sys
from .migration import ALL_TARGETS, CREATE_TARGETS, ROLLBACK_TARGETS


def build_base_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=add_help)
    parser.add_argument("--mode", choices=["desktop", "server"], default="desktop")
    parser.add_argument("--http", action="store_true", help="Enable HTTP+WS server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--dev", type=int, default=0)
    parser.add_argument(
        "--client",
        choices=["qtdesktop", "webclient", "reactbootstrap", "tauri"],
        default=None,
    )
    parser.add_argument(
        "--tauri-web-client",
        choices=["webclient", "reactbootstrap"],
        default="webclient",
        help="React client to wrap when --client tauri is selected",
    )
    parser.add_argument("--desktop-client-path")
    parser.add_argument("--child-gui", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--server-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-process", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-socket", help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-policy-file", help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-refresh-seconds", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-parent-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--os-sandbox-helper-token", help=argparse.SUPPRESS)
    parser.add_argument("--listen-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--worker-index", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--pip-helper", action="store_true", help=argparse.SUPPRESS)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = build_base_parser()

    subparsers = parser.add_subparsers(dest="command")

    migrate_parser = subparsers.add_parser("migrate", help="Run Alembic migrations")
    migrate_parser.add_argument("target", choices=[*ALL_TARGETS, "all"])

    create_parser = subparsers.add_parser("create-migration", help="Create a new Alembic revision")
    create_parser.add_argument("target", choices=CREATE_TARGETS)
    create_parser.add_argument("-m", "--message", required=True)
    create_parser.add_argument("--autogenerate", action="store_true")
    create_parser.add_argument("--module", dest="module_name")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback Alembic revisions")
    rollback_parser.add_argument("target", choices=ROLLBACK_TARGETS)
    rollback_group = rollback_parser.add_mutually_exclusive_group(required=True)
    rollback_group.add_argument("--to", dest="revision")
    rollback_group.add_argument("--steps", type=int)

    status_parser = subparsers.add_parser("migration-status", help="Show current and head Alembic revisions")
    status_parser.add_argument("target", choices=[*ALL_TARGETS, "all"])

    validate_parser = subparsers.add_parser(
        "validate-config",
        help="Validate config.yaml structure and provider dependencies",
    )
    validate_parser.add_argument("--path", dest="config_path")
    validate_parser.add_argument("--json", action="store_true", dest="json_output")

    reset_parser = subparsers.add_parser(
        "reset-install",
        help="Remove the active config and optionally delete local SQLite databases",
    )
    reset_parser.add_argument(
        "--include-media",
        action="store_true",
        help="Also offer deletion of local filesystem media with separate confirmation",
    )

    module_status_parser = subparsers.add_parser(
        "module-status",
        help="Show registered module commands and their persisted runtime state",
    )
    module_status_parser.add_argument("--module", dest="module_name")
    module_status_parser.add_argument("--json", action="store_true", dest="json_output")

    knowledge_rebuild_parser = subparsers.add_parser(
        "knowledge-rebuild",
        help="Queue rebuild jobs for one knowledge source or a filtered set of sources",
    )
    rebuild_scope = knowledge_rebuild_parser.add_mutually_exclusive_group(required=True)
    rebuild_scope.add_argument("--source-id", dest="source_id")
    rebuild_scope.add_argument("--all", dest="rebuild_all", action="store_true")
    knowledge_rebuild_parser.add_argument("--user-id", dest="user_id")
    knowledge_rebuild_parser.add_argument("--organization-id", dest="organization_id")
    knowledge_rebuild_parser.add_argument("--source-type", dest="source_type")
    knowledge_rebuild_parser.add_argument("--limit", dest="limit", type=int)
    knowledge_rebuild_parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    knowledge_rebuild_parser.add_argument("--json", action="store_true", dest="json_output")

    return parser


def parse_args(argv: list[str] | None = None):
    raw_args = list(sys.argv[1:] if argv is None else argv)
    known_commands = {
        "migrate",
        "create-migration",
        "rollback",
        "migration-status",
        "validate-config",
        "reset-install",
        "module-status",
        "knowledge-rebuild",
    }
    base_parser = build_base_parser(add_help=False)
    base_args, remaining = base_parser.parse_known_args(raw_args)
    if remaining and remaining[0] not in known_commands and not remaining[0].startswith("-"):
        base_args.command = "module-callable"
        base_args.module_command = remaining[0]
        base_args.module_args = remaining[1:]
        return base_args

    if not remaining:
        return build_parser().parse_args(raw_args)

    if remaining[0].startswith("-"):
        parser = build_parser()
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")

    parser = build_parser()
    command_index = raw_args.index(remaining[0])
    args, unknown = parser.parse_known_args(raw_args[:command_index] + remaining)
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    return args

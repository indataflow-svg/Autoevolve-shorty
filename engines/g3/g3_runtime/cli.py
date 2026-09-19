from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .accounts import list_accounts, load_account
from .buffer import BufferClient
from .errors import G3Error
from .handoff import load_handoff
from .ledger import Ledger
from .r2 import R2Uploader
from .service import SCHEDULE_MODES, submit_handoff, submit_schedule


def client_from_env(account_name: str | None = None) -> BufferClient:
    account = load_account(account_name)
    return BufferClient(
        account.api_key,
        os.environ.get("BUFFER_API_ENDPOINT", "https://api.buffer.com"),
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="company-core-g3")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--account", default=None,
                      help="named Buffer account from g3.env (default: the unprefixed BUFFER_* variables)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("account", help="show Buffer organizations")
    commands.add_parser("accounts", help="list configured Buffer accounts (keys never shown)")
    channels = commands.add_parser("channels", help="list connected Buffer channels")
    channels.add_argument("--organization-id")
    doctor = commands.add_parser("doctor", help="verify Buffer, R2 configuration, and channel IDs")
    doctor.add_argument("--require", action="append", choices=["x", "instagram"], default=[])
    validate = commands.add_parser("validate", help="validate a G2-to-G3 handoff without network access")
    validate.add_argument("handoff")
    validate.add_argument("--asset-root")
    draft = commands.add_parser("draft", help="upload media to R2 and create Buffer drafts only")
    draft.add_argument("handoff")
    draft.add_argument("--asset-root")
    draft.add_argument("--ledger", default="state/g3.sqlite3")
    draft.add_argument("--dry-run", action="store_true")
    schedule = commands.add_parser("schedule", help="upload media to R2 and schedule Buffer posts (queue or timed)")
    schedule.add_argument("handoff")
    schedule.add_argument("--asset-root")
    schedule.add_argument("--ledger", default="state/g3.sqlite3")
    schedule.add_argument("--mode", choices=sorted(SCHEDULE_MODES), default="queue",
                          help="queue: next queue slot, next: share next, timed: exact due-at time")
    schedule.add_argument("--due-at", default=None,
                          help="ISO-8601 future timestamp, required for --mode timed")
    schedule.add_argument("--dry-run", action="store_true")
    return root


def _organization(client: BufferClient, provided: str | None) -> tuple[dict, str]:
    account = client.account()
    organizations = account.get("organizations") or []
    organization_id = (provided or os.environ.get("BUFFER_ORGANIZATION_ID", "")).strip()
    if not organization_id:
        if len(organizations) != 1:
            raise G3Error("set BUFFER_ORGANIZATION_ID (the account does not have exactly one organization)")
        organization_id = str(organizations[0]["id"])
    return account, organization_id


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            handoff = load_handoff(args.handoff, args.asset_root)
            result = {"ok": True, "campaign_id": handoff.campaign_id,
                      "drafts": len(handoff.entries), "draft_only": True}
        elif args.command == "accounts":
            result = {"ok": True, "accounts": list_accounts()}
        elif args.command == "account":
            account = load_account(args.account)
            result = {**client_from_env(args.account).account(), "buffer_account": account.name}
        elif args.command == "channels":
            account = load_account(args.account)
            client = client_from_env(args.account)
            _, organization_id = _organization(client, args.organization_id or account.organization_id or None)
            result = {"organization_id": organization_id, "buffer_account": account.name,
                      "channels": client.channels(organization_id)}
        elif args.command == "doctor":
            account = load_account(args.account)
            client = client_from_env(args.account)
            profile, organization_id = _organization(client, account.organization_id or None)
            channels = client.channels(organization_id)
            usable = [item for item in channels if not item.get("isDisconnected") and not item.get("isLocked")]
            by_service = {str(item.get("service")): item for item in usable}
            requested_service = {"x": "twitter", "instagram": "instagram"}
            missing = [service for service in args.require if requested_service[service] not in by_service]
            configured = {
                "x": bool(account.x_channel_id),
                "instagram": bool(account.instagram_channel_id),
            }
            R2Uploader()
            result = {"ok": not missing, "account": profile.get("email"),
                      "buffer_account": account.name,
                      "organization_id": organization_id, "usable_channels": usable,
                      "channel_ids_configured": configured, "missing": missing,
                      "r2": "configured", "draft_only": True}
            if missing:
                print(json.dumps(result, indent=2))
                return 2
        else:
            account = load_account(args.account)
            handoff = load_handoff(args.handoff, args.asset_root)
            client = BufferClient("DRY_RUN") if args.dry_run else client_from_env(args.account)
            uploader = None if args.dry_run else R2Uploader()
            if args.command == "schedule":
                result = submit_schedule(client, uploader, Ledger(args.ledger), handoff,
                                         args.mode, args.due_at, args.dry_run, account)
            else:
                result = submit_handoff(client, uploader, Ledger(args.ledger), handoff, args.dry_run, account)
        print(json.dumps(result, indent=2))
        return 0
    except G3Error as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

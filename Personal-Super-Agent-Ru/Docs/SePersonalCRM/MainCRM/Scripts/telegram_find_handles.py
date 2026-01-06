#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from dotenv import load_dotenv

from telegram_common import (
    SYNC_LIST_TELEGRAM,
    TAG_DO_NOT_SYNC,
    TAG_DO_SYNC,
    get_telegram_credentials,
    get_session_path,
    now_utc,
    upsert_sync_entry,
)


def _connect():
    from telethon import TelegramClient

    api_id, api_hash, _session_name = get_telegram_credentials()
    session_path = str(get_session_path())
    client = TelegramClient(session_path, api_id, api_hash)
    return client


def _user_to_json(u: Any) -> dict[str, Any]:
    return {
        "user_id": getattr(u, "id", None),
        "username": ("@" + u.username) if getattr(u, "username", None) else None,
        "first_name": getattr(u, "first_name", None),
        "last_name": getattr(u, "last_name", None),
        "phone": getattr(u, "phone", None),
        "bot": getattr(u, "bot", None),
        "verified": getattr(u, "verified", None),
        "scam": getattr(u, "scam", None),
        "fake": getattr(u, "fake", None),
    }


async def do_search(query: str, limit: int) -> list[dict[str, Any]]:
    from telethon import functions, types

    results: list[dict[str, Any]] = []
    q = query.strip()
    if not q:
        return results

    async with _connect() as client:
        # If looks like username, try direct resolve first
        if q.startswith("@"):
            try:
                ent = await client.get_entity(q)
                if isinstance(ent, types.User):
                    return [_user_to_json(ent)]
            except Exception:
                pass

        # Contacts search (fast)
        try:
            resp = await client(functions.contacts.SearchRequest(q=q, limit=limit))
            for u in getattr(resp, "users", []) or []:
                results.append(_user_to_json(u))
        except Exception:
            pass

        # Fallback: scan dialogs titles/usernames (best-effort)
        if not results:
            async for d in client.iter_dialogs(limit=200):
                ent = d.entity
                if not isinstance(ent, types.User):
                    continue
                username = ("@" + ent.username) if getattr(ent, "username", None) else ""
                title = (d.name or "").lower()
                if q.lower() in title or (username and q.lower().lstrip("@") in username.lower()):
                    results.append(_user_to_json(ent))
                    if len(results) >= limit:
                        break

    # Deduplicate by user_id
    seen: set[int] = set()
    uniq: list[dict[str, Any]] = []
    for r in results:
        uid = r.get("user_id")
        if isinstance(uid, int) and uid in seen:
            continue
        if isinstance(uid, int):
            seen.add(uid)
        uniq.append(r)
    return uniq


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="Find Telegram handles/user_ids and save to sync_list_telegram.txt")
    p.add_argument("--person", required=True, help="Canonical person name in sync list / Contacts/")

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--search", action="store_true", help="Search for a handle/user_id")
    mode.add_argument("--save", metavar="HANDLE_OR_DISPLAY", help="Save handle/display name for person")

    p.add_argument("--query", help="Search query (name/username/phone)")
    p.add_argument("--limit", type=int, default=10, help="Max results for --search")

    p.add_argument("--user-id", type=int, help="Telegram user_id to save (recommended)")
    p.add_argument("--tag", choices=[TAG_DO_SYNC, TAG_DO_NOT_SYNC], default=TAG_DO_SYNC)

    args = p.parse_args()

    if args.search:
        if not args.query:
            raise SystemExit("--query is required with --search")
        import asyncio

        res = asyncio.run(do_search(args.query, args.limit))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    # save mode
    handle = (args.save or "").strip()
    if not handle:
        raise SystemExit("--save requires a non-empty handle/display name")

    # Best practice: user_id strongly recommended for fast sync.
    upsert_sync_entry(
        name=args.person.strip(),
        handle=handle,
        user_id=args.user_id,
        tag=args.tag,
        done=None,
        path=SYNC_LIST_TELEGRAM,
    )

    print(
        json.dumps(
            {
                "ok": True,
                "person": args.person,
                "handle": handle,
                "user_id": args.user_id,
                "tag": args.tag,
                "sync_list": str(SYNC_LIST_TELEGRAM),
                "saved_at": now_utc().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()


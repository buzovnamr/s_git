#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv

from telegram_common import (
    SYNC_LIST_TELEGRAM,
    TAG_DO_SYNC,
    TAG_DO_NOT_SYNC,
    TAG_NOT_CONNECTED,
    TAG_NOT_ON_TELEGRAM,
    SyncEntry,
    read_sync_list,
    upsert_sync_entry,
    get_telegram_credentials,
    get_session_path,
)


def _connect():
    from telethon import TelegramClient

    api_id, api_hash, _ = get_telegram_credentials()
    return TelegramClient(str(get_session_path()), api_id, api_hash)


@dataclass
class UpdateResult:
    person: str
    updated: bool
    user_id: Optional[int]
    reason: str


async def _resolve_user_id(client, entry: SyncEntry) -> Optional[int]:
    from telethon import types, functions

    if not entry.handle:
        return None
    h = entry.handle.strip()
    if h.startswith("@"):
        try:
            ent = await client.get_entity(h)
            if isinstance(ent, types.User):
                return int(ent.id)
        except Exception:
            return None

    # Display-name fallback: search contacts; only accept unique exact match.
    try:
        resp = await client(functions.contacts.SearchRequest(q=h, limit=10))
        users = [u for u in getattr(resp, "users", []) or [] if getattr(u, "id", None)]
        if not users:
            return None
        exact = []
        for u in users:
            full = " ".join([p for p in [getattr(u, "first_name", ""), getattr(u, "last_name", "")] if p]).strip()
            if full.lower() == h.lower():
                exact.append(u)
        if len(exact) == 1:
            return int(exact[0].id)
        return None
    except Exception:
        return None


async def main_async(dry_run: bool) -> list[UpdateResult]:
    entries = read_sync_list(SYNC_LIST_TELEGRAM)
    results: list[UpdateResult] = []

    async with _connect() as client:
        for e in entries:
            if e.user_id is not None:
                continue
            if e.tag in (TAG_NOT_ON_TELEGRAM, TAG_NOT_CONNECTED):
                continue
            if not e.handle:
                results.append(UpdateResult(e.name, False, None, "no handle"))
                continue

            uid = await _resolve_user_id(client, e)
            if uid is None:
                results.append(UpdateResult(e.name, False, None, "not resolved uniquely"))
                continue

            if not dry_run:
                upsert_sync_entry(
                    name=e.name,
                    handle=e.handle,
                    user_id=uid,
                    tag=e.tag or TAG_DO_SYNC,
                    done=e.done,
                    path=SYNC_LIST_TELEGRAM,
                )
            results.append(UpdateResult(e.name, True, uid, "updated" if not dry_run else "would update"))

    return results


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Batch add missing [ID:user_id] to sync_list_telegram.txt")
    p.add_argument("--dry-run", action="store_true", help="Do not modify files, only report")
    args = p.parse_args()

    import asyncio

    res = asyncio.run(main_async(args.dry_run))
    payload = [
        {"person": r.person, "updated": r.updated, "user_id": r.user_id, "reason": r.reason}
        for r in res
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


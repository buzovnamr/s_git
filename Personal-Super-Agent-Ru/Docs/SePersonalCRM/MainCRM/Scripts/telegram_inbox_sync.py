#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from telegram_common import INBOX_DIR, get_telegram_credentials, get_session_path, parse_datetime, now_utc, iso


LAST_SYNC_FILE = INBOX_DIR / ".last_sync_timestamp"
OUT_MD = INBOX_DIR / "telegram ai inbox.md"


def _connect():
    from telethon import TelegramClient

    api_id, api_hash, _ = get_telegram_credentials()
    return TelegramClient(str(get_session_path()), api_id, api_hash)


def _load_last_sync() -> Optional[datetime]:
    if not LAST_SYNC_FILE.exists():
        return None
    raw = LAST_SYNC_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return parse_datetime(raw)
    except Exception:
        return None


def _save_last_sync(dt: datetime) -> None:
    LAST_SYNC_FILE.write_text(iso(dt) + "\n", encoding="utf-8")


def _msg_block(dt: datetime, sender: str, text: str) -> str:
    body = text.strip() if text else ""
    if not body:
        body = "[Empty message]"
    return f"**{iso(dt)}** ({sender}):\n{body}\n"


async def main_async(reload: bool, since: Optional[datetime]) -> None:
    group_id_raw = os.getenv("TELEGRAM_INBOX_GROUP_ID", "").strip()
    if not group_id_raw:
        raise SystemExit("Set TELEGRAM_INBOX_GROUP_ID in .env (numeric chat/group id).")
    try:
        group_id = int(group_id_raw)
    except ValueError as e:
        raise SystemExit("TELEGRAM_INBOX_GROUP_ID must be integer.") from e

    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    if reload:
        effective_since = None
    elif since is not None:
        effective_since = since
    else:
        effective_since = _load_last_sync()

    async with _connect() as client:
        entity = await client.get_entity(group_id)

        # Fetch in chronological order
        kwargs = {"reverse": True}
        if effective_since is not None:
            kwargs["offset_date"] = effective_since

        blocks = []
        newest: Optional[datetime] = None
        async for m in client.iter_messages(entity, **kwargs):
            if not getattr(m, "date", None):
                continue
            if effective_since is not None and m.date <= effective_since:
                continue

            sender_name = "Unknown"
            try:
                if getattr(m, "sender", None):
                    s = m.sender
                    sender_name = (
                        getattr(s, "first_name", None)
                        or getattr(s, "title", None)
                        or getattr(s, "username", None)
                        or "Unknown"
                    )
            except Exception:
                pass

            text = (m.message or "").strip()
            if not text and getattr(m, "media", None):
                text = "🎤 [Voice/Media message]"
            blocks.append(_msg_block(m.date, sender_name, text))
            blocks.append("\n")
            newest = m.date

        if reload:
            header = f"# Telegram AI Inbox\n\n**Reloaded:** {iso(now_utc())}\n\n---\n\n"
            OUT_MD.write_text(header + "".join(blocks), encoding="utf-8")
        else:
            if not OUT_MD.exists():
                OUT_MD.write_text(f"# Telegram AI Inbox\n\n---\n\n", encoding="utf-8")
            if blocks:
                OUT_MD.write_text(OUT_MD.read_text(encoding="utf-8").rstrip() + "\n\n" + "".join(blocks), encoding="utf-8")

        if newest is not None:
            _save_last_sync(newest)
            print(f"Synced. Newest message: {iso(newest)}")
        else:
            print("No new messages.")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Sync Telegram AI Inbox group into Inbox/telegram ai inbox.md")
    p.add_argument("--reload", action="store_true", help="Reload all messages (overwrite file)")
    p.add_argument("--since", help="Reload from date/time (YYYY-MM-DD | ISO | 'YYYY-MM-DD HH:MM')")
    args = p.parse_args()

    since = parse_datetime(args.since) if args.since else None

    import asyncio

    asyncio.run(main_async(args.reload, since))


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from dotenv import load_dotenv

from telegram_common import get_telegram_credentials, get_session_path


def _connect():
    from telethon import TelegramClient

    api_id, api_hash, _session_name = get_telegram_credentials()
    session_path = str(get_session_path())
    return TelegramClient(session_path, api_id, api_hash)


def _entity_json(ent: Any) -> dict[str, Any]:
    username = getattr(ent, "username", None)
    return {
        "id": getattr(ent, "id", None),
        "type": ent.__class__.__name__,
        "username": ("@" + username) if username else None,
        "first_name": getattr(ent, "first_name", None),
        "last_name": getattr(ent, "last_name", None),
        "title": getattr(ent, "title", None),
        "phone": getattr(ent, "phone", None),
        "verified": getattr(ent, "verified", None),
        "bot": getattr(ent, "bot", None),
    }


async def main_async(handle: str | None, user_id: int | None, last_n: int) -> None:
    from telethon import types

    async with _connect() as client:
        target = None
        if user_id is not None:
            target = user_id
        elif handle:
            target = handle
        else:
            raise SystemExit("Provide --handle or --user-id")

        ent = await client.get_entity(target)
        out: dict[str, Any] = {"entity": _entity_json(ent), "last_messages": []}

        # Only users/chats have messages
        try:
            msgs = await client.get_messages(ent, limit=last_n)
            for m in reversed(msgs):
                text = (m.message or "").strip()
                out["last_messages"].append(
                    {
                        "id": m.id,
                        "date": m.date.isoformat() if m.date else None,
                        "out": bool(getattr(m, "out", False)),
                        "text": text[:500] if text else None,
                        "has_media": bool(getattr(m, "media", None)),
                    }
                )
        except Exception:
            pass

        print(json.dumps(out, ensure_ascii=False, indent=2))


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Preview a Telegram entity and recent messages")
    p.add_argument("--handle", help="@username or display name")
    p.add_argument("--user-id", type=int, help="Telegram numeric user_id")
    p.add_argument("--last", type=int, default=5, help="How many last messages to fetch")
    args = p.parse_args()

    import asyncio

    asyncio.run(main_async(args.handle, args.user_id, args.last))


if __name__ == "__main__":
    main()


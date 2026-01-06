#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from dotenv import load_dotenv

from telegram_common import SYNC_LIST_TELEGRAM, TAG_DO_SYNC, parse_datetime, read_sync_list
from telegram_sync import sync_one


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Reload Telegram history for all #DO_SYNC contacts")
    p.add_argument("--since", required=True, help="Reload from date/time (YYYY-MM-DD | ISO | 'YYYY-MM-DD HH:MM')")
    args = p.parse_args()

    since = parse_datetime(args.since)
    entries = [e for e in read_sync_list(SYNC_LIST_TELEGRAM) if e.tag == TAG_DO_SYNC]

    async def runner():
        results = []
        for e in entries:
            results.append(await sync_one(e, since))
        return results

    res = asyncio.run(runner())
    ok = sum(1 for r in res if r.ok)
    fail = len(res) - ok
    print(f"OK={ok} FAIL={fail} since={since.isoformat()}")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from telegram_common import (
    CONTACTS_DIR,
    SYNC_LIST_TELEGRAM,
    SYNC_STATUS_MD,
    TAG_DO_NOT_SYNC,
    TAG_DO_SYNC,
    TAG_NOT_CONNECTED,
    TAG_NOT_ON_TELEGRAM,
    read_sync_list,
    telegram_md_path,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate Telegram sync status report")
    p.add_argument("--out", default=str(SYNC_STATUS_MD), help="Output markdown path")
    args = p.parse_args()

    entries = read_sync_list(SYNC_LIST_TELEGRAM)

    counts = {
        TAG_DO_SYNC: 0,
        TAG_DO_NOT_SYNC: 0,
        TAG_NOT_ON_TELEGRAM: 0,
        TAG_NOT_CONNECTED: 0,
        "UNKNOWN": 0,
    }

    rows = []
    for e in entries:
        tag = e.tag or "UNKNOWN"
        counts[tag] = counts.get(tag, 0) + 1
        md = telegram_md_path(e.name)
        exists = md.exists()
        rows.append((e.name, e.handle or "", str(e.user_id or ""), tag, e.done.isoformat() if e.done else "", "✅" if exists else "❌"))

    out_lines = []
    out_lines.append("# Telegram Sync Status")
    out_lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    out_lines.append("")
    out_lines.append("## Counts")
    for k, v in counts.items():
        out_lines.append(f"- **{k}**: {v}")
    out_lines.append("")
    out_lines.append("## Per-contact status")
    out_lines.append("| Person | Handle | User ID | Tag | DONE | telegram.md |")
    out_lines.append("|---|---|---:|---|---|---|")
    for r in rows:
        out_lines.append(f"| {r[0]} | {r[1]} | {r[2]} | #{r[3]} | {r[4]} | {r[5]} |")
    out_lines.append("")
    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from telegram_common import (
    SYNC_LIST_TELEGRAM,
    TAG_DO_NOT_SYNC,
    TAG_DO_SYNC,
    TAG_NOT_CONNECTED,
    TAG_NOT_ON_TELEGRAM,
    SyncEntry,
    ensure_contact_folder,
    iso,
    now_utc,
    parse_datetime,
    read_sync_list,
    telegram_md_path,
    update_done_timestamp,
    get_telegram_credentials,
    get_session_path,
)


def _connect():
    from telethon import TelegramClient

    api_id, api_hash, _session_name = get_telegram_credentials()
    session_path = str(get_session_path())
    return TelegramClient(session_path, api_id, api_hash)


def _fmt_dir(outgoing: bool) -> str:
    return "➡️" if outgoing else "⬅️"


def _safe_text(text: str) -> str:
    # Keep markdown readable; avoid huge lines.
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not t:
        return ""
    return t


def _header(name: str, display: str, handle: Optional[str]) -> str:
    h = handle or display or "unknown"
    return f"# {name}\n\n## Telegram history with {display} (handle: {h})\n\n"


def _render_message_line(dt: datetime, outgoing: bool, text: str) -> str:
    return f"- {iso(dt)} {_fmt_dir(outgoing)}: {text}"


@dataclass
class SyncResult:
    person: str
    ok: bool
    message: str
    new_messages: int = 0


async def _resolve_entity(client, entry: SyncEntry):
    if entry.user_id is not None:
        return await client.get_entity(entry.user_id)
    if entry.handle:
        return await client.get_entity(entry.handle)
    raise RuntimeError("No handle/user_id to resolve entity.")


async def _iter_messages_chrono(client, entity, since: Optional[datetime] = None):
    # Telethon: reverse=True yields chronological order.
    # With offset_date+reverse=True: yields messages after offset_date (best-effort).
    kwargs = {"reverse": True}
    if since is not None:
        kwargs["offset_date"] = since
    async for msg in client.iter_messages(entity, **kwargs):
        yield msg


def _read_existing_prefix(path: Path, since: datetime) -> str:
    """
    Best-effort: keep everything before first message >= since.
    If parsing fails, keep full file (safer than deleting).
    """
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        out.append(line)
        if line.startswith("- "):
            try:
                ts = line.split(" ", 2)[1]
                dt = parse_datetime(ts)
                if dt >= since:
                    # remove this line and anything after
                    out.pop()
                    break
            except Exception:
                continue
    return "\n".join(out).rstrip() + ("\n" if out else "")


async def sync_one(entry: SyncEntry, since: Optional[datetime]) -> SyncResult:
    if entry.tag in (TAG_NOT_ON_TELEGRAM, TAG_NOT_CONNECTED):
        return SyncResult(entry.name, ok=False, message=f"Skipped due to tag #{entry.tag}")
    if not entry.handle and entry.user_id is None:
        return SyncResult(entry.name, ok=False, message="Missing handle and user_id")

    async with _connect() as client:
        entity = await _resolve_entity(client, entry)
        display = getattr(entity, "first_name", None) or getattr(entity, "title", None) or entry.handle or entry.name

        out_path = telegram_md_path(entry.name)
        ensure_contact_folder(entry.name)

        # Decide mode
        if since is not None:
            # Reload mode: preserve older content if file exists, then resync from since.
            prefix = _read_existing_prefix(out_path, since)
            marker = f"\n## Reloaded from {iso(since)} on {iso(now_utc())}\n\n"
            base = prefix if prefix else _header(entry.name, str(display), entry.handle)

            lines: list[str] = [base.rstrip(), marker.rstrip(), ""]
            count = 0
            async for m in _iter_messages_chrono(client, entity, since=since):
                if not getattr(m, "date", None):
                    continue
                text = _safe_text(getattr(m, "message", "") or "")
                if not text:
                    # media placeholder
                    if getattr(m, "media", None):
                        text = "[Media]"
                    else:
                        continue
                lines.append(_render_message_line(m.date, bool(getattr(m, "out", False)), text))
                lines.append("")
                count += 1
            out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            update_done_timestamp(entry.name, now_utc())
            return SyncResult(entry.name, ok=True, message="Reloaded", new_messages=count)

        if entry.done is None:
            # First sync: full history
            base = _header(entry.name, str(display), entry.handle)
            lines: list[str] = [base.rstrip(), ""]
            count = 0
            async for m in _iter_messages_chrono(client, entity, since=None):
                if not getattr(m, "date", None):
                    continue
                text = _safe_text(getattr(m, "message", "") or "")
                if not text:
                    if getattr(m, "media", None):
                        text = "[Media]"
                    else:
                        continue
                lines.append(_render_message_line(m.date, bool(getattr(m, "out", False)), text))
                lines.append("")
                count += 1
            out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            update_done_timestamp(entry.name, now_utc())
            return SyncResult(entry.name, ok=True, message="First sync complete", new_messages=count)

        # Incremental
        marker = (
            f"\n## Update from {iso(now_utc())}\n"
            f"### Messages after {iso(entry.done)}\n\n"
        )
        appended: list[str] = [marker]
        count = 0
        async for m in _iter_messages_chrono(client, entity, since=entry.done):
            if not getattr(m, "date", None):
                continue
            if m.date <= entry.done:
                continue
            text = _safe_text(getattr(m, "message", "") or "")
            if not text:
                if getattr(m, "media", None):
                    text = "[Media]"
                else:
                    continue
            appended.append(_render_message_line(m.date, bool(getattr(m, "out", False)), text))
            appended.append("")
            count += 1

        if count > 0:
            existing = out_path.read_text(encoding="utf-8") if out_path.exists() else _header(entry.name, str(display), entry.handle)
            out_path.write_text(existing.rstrip() + "\n" + "\n".join(appended).rstrip() + "\n", encoding="utf-8")

        update_done_timestamp(entry.name, now_utc())
        return SyncResult(entry.name, ok=True, message="Incremental sync complete", new_messages=count)


def _write_report(path: Path, results: list[SyncResult]) -> None:
    lines = []
    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok
    new_total = sum(r.new_messages for r in results)
    lines.append(f"OK: {ok}")
    lines.append(f"FAIL: {fail}")
    lines.append(f"NEW_MESSAGES: {new_total}")
    lines.append("")
    for r in results:
        lines.append(f"{r.person}\t{'OK' if r.ok else 'FAIL'}\t{r.new_messages}\t{r.message}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    load_dotenv()

    p = argparse.ArgumentParser(description="Sync Telegram messages into Contacts/<Name>/<Name> telegram.md")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--person", help="Person name (must match sync_list_telegram.txt)")
    g.add_argument("--all", action="store_true", help="Sync all contacts tagged #DO_SYNC")
    p.add_argument("--since", help="Reload from date/time (YYYY-MM-DD | ISO | 'YYYY-MM-DD HH:MM')")
    p.add_argument("--report", help="Write a TSV-ish report to file")
    args = p.parse_args()

    since: Optional[datetime] = parse_datetime(args.since) if args.since else None

    entries = read_sync_list(SYNC_LIST_TELEGRAM)
    targets: list[SyncEntry] = []
    if args.person:
        person = args.person.strip()
        found = [e for e in entries if e.name == person]
        if not found:
            raise SystemExit(f"Person not found in sync list: {person}")
        targets = found
    else:
        targets = [e for e in entries if e.tag == TAG_DO_SYNC]

    async def runner():
        results: list[SyncResult] = []
        for e in targets:
            try:
                results.append(await sync_one(e, since))
            except Exception as ex:
                results.append(SyncResult(e.name, ok=False, message=str(ex)))
        return results

    results = asyncio.run(runner())

    for r in results:
        status = "OK" if r.ok else "FAIL"
        print(f"{status}\t{r.person}\tnew={r.new_messages}\t{r.message}")

    if args.report:
        _write_report(Path(args.report), results)


if __name__ == "__main__":
    main()


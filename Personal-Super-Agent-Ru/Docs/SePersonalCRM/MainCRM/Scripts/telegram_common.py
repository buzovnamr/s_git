#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


MAINCRM_DIR = Path(__file__).resolve().parent.parent
CONTEXT_DIR = MAINCRM_DIR / "Context"
CONTACTS_DIR = MAINCRM_DIR / "Contacts"
INBOX_DIR = MAINCRM_DIR / "Inbox"

SYNC_LIST_TELEGRAM = CONTEXT_DIR / "sync_list_telegram.txt"
SYNC_STATUS_MD = CONTEXT_DIR / "Telegram_Sync_Status.md"


TAG_DO_SYNC = "DO_SYNC"
TAG_DO_NOT_SYNC = "DO_NOT_SYNC"
TAG_NOT_ON_TELEGRAM = "NOT_ON_TELEGRAM"
TAG_NOT_CONNECTED = "NOT_CONNECTED"


@dataclass(frozen=True)
class SyncEntry:
    name: str
    handle: Optional[str]
    user_id: Optional[int]
    tag: Optional[str]
    done: Optional[datetime]
    raw: str

    @property
    def should_sync_in_all(self) -> bool:
        return self.tag == TAG_DO_SYNC


def _parse_done_timestamp(raw: str) -> Optional[datetime]:
    m = re.search(r"\[DONE:(?P<ts>[^\]]+)\]", raw)
    if not m:
        return None
    ts = m.group("ts").strip()
    dt = parse_datetime(ts)
    return dt


def parse_datetime(value: str) -> datetime:
    """
    Accepts:
      - ISO: 2025-10-21T14:30:00 or 2025-10-21T14:30:00+00:00
      - Date only: 2025-10-21 (assumes 00:00:00)
      - Date time: 2025-10-21 14:30 or 2025-10-21 14:30:45
    Returns timezone-aware datetime (UTC if tz missing).
    """
    s = value.strip()

    # ISO-like
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    fmts = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(f"Unrecognized datetime format: {value!r}")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def get_telegram_credentials() -> tuple[int, str, str]:
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_SESSION", "sepersonalcrm").strip()

    if not api_id_raw or not api_hash:
        raise RuntimeError(
            "Missing Telegram credentials. Set TELEGRAM_API_ID and TELEGRAM_API_HASH "
            "(e.g. via .env)."
        )
    try:
        api_id = int(api_id_raw)
    except ValueError as e:
        raise RuntimeError("TELEGRAM_API_ID must be an integer.") from e

    return api_id, api_hash, session


def get_session_path() -> Path:
    # Keep session file local to Scripts/ for portability.
    session_name = os.getenv("TELEGRAM_SESSION", "sepersonalcrm").strip() or "sepersonalcrm"
    return Path(__file__).resolve().parent / session_name


def read_sync_list(path: Path = SYNC_LIST_TELEGRAM) -> list[SyncEntry]:
    if not path.exists():
        return []
    entries: list[SyncEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.rstrip("\n")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        name: str
        handle: Optional[str] = None
        user_id: Optional[int] = None
        tag: Optional[str] = None
        done: Optional[datetime] = _parse_done_timestamp(stripped)

        # Tag
        for candidate in (TAG_DO_SYNC, TAG_DO_NOT_SYNC, TAG_NOT_ON_TELEGRAM, TAG_NOT_CONNECTED):
            if f"#{candidate}" in stripped:
                tag = candidate
                break

        # user_id
        m_id = re.search(r"\[ID:(?P<id>\d+)\]", stripped)
        if m_id:
            try:
                user_id = int(m_id.group("id"))
            except ValueError:
                user_id = None

        # Name + handle
        if "->" in stripped:
            left, right = stripped.split("->", 1)
            name = left.strip()
            # Everything before first tag/metadata is "handle"
            right = right.strip()
            # Remove deprecated synonyms in brackets (best effort)
            right = re.sub(r"\[[^\]]+\]", lambda m: m.group(0) if m.group(0).startswith("[ID:") else "", right).strip()
            # Split by first metadata marker
            stop = len(right)
            for marker in (" #", " [ID:", " [DONE:"):
                idx = right.find(marker)
                if idx != -1:
                    stop = min(stop, idx)
            handle = right[:stop].strip() or None
        else:
            # No arrow format: "Name #TAG ..."
            parts = stripped.split("#", 1)
            name = parts[0].strip()

        entries.append(
            SyncEntry(name=name, handle=handle, user_id=user_id, tag=tag, done=done, raw=raw)
        )
    return entries


def find_entry(entries: Iterable[SyncEntry], person: str) -> Optional[SyncEntry]:
    target = person.strip()
    for e in entries:
        if e.name == target:
            return e
    return None


def ensure_contact_folder(name: str) -> Path:
    folder = CONTACTS_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def telegram_md_path(name: str) -> Path:
    return ensure_contact_folder(name) / f"{name} telegram.md"


def _render_line(
    name: str,
    handle: Optional[str],
    user_id: Optional[int],
    tag: str,
    done: Optional[datetime],
) -> str:
    parts: list[str] = [name]
    if handle:
        parts.append("->")
        parts.append(handle)
    if user_id is not None:
        parts.append(f"[ID:{user_id}]")
    parts.append(f"#{tag}")
    if done is not None:
        parts.append(f"[DONE:{iso(done)}]")
    return " ".join(parts)


def upsert_sync_entry(
    *,
    name: str,
    handle: Optional[str],
    user_id: Optional[int],
    tag: str,
    done: Optional[datetime] = None,
    path: Path = SYNC_LIST_TELEGRAM,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_line = _render_line(name=name, handle=handle, user_id=user_id, tag=tag, done=done)

    out: list[str] = []
    replaced = False
    for line in lines:
        if not replaced:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                if stripped.startswith(name + " ") or stripped == name or stripped.startswith(name + "->") or stripped.startswith(name + " ->"):
                    out.append(new_line)
                    replaced = True
                    continue
        out.append(line)
    if not replaced:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(new_line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def update_done_timestamp(person: str, done: datetime, path: Path = SYNC_LIST_TELEGRAM) -> None:
    entries = read_sync_list(path)
    entry = find_entry(entries, person)
    if not entry:
        raise RuntimeError(f"Person not found in sync list: {person}")
    tag = entry.tag or TAG_DO_SYNC
    upsert_sync_entry(
        name=entry.name,
        handle=entry.handle,
        user_id=entry.user_id,
        tag=tag,
        done=done,
        path=path,
    )


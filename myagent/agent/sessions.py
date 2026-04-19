"""
Shared session CRUD + trash logic.
Used by both tui.py and repl.py.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path.home() / ".myagent" / "sessions"
TRASH_DIR    = Path.home() / ".myagent" / "sessions_trash"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_topic(messages: list[dict]) -> str:
    for m in messages:
        if m.get("role") == "user":
            return m.get("text", "").replace("\n", " ").strip()[:120]
    return ""


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Active sessions
# ---------------------------------------------------------------------------

def sessions_save(sid: str, name: str, messages: list[dict]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _write(SESSIONS_DIR / f"{sid}.json", {
        "id":         sid,
        "name":       name,
        "updated_at": datetime.now().isoformat(),
        "topic":      extract_topic(messages),
        "messages":   messages,
    })


def sessions_list() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        d = _read(f)
        if d:
            out.append(d)
    return out


def session_rename(sid: str, new_name: str) -> bool:
    path = SESSIONS_DIR / f"{sid}.json"
    data = _read(path)
    if not data:
        return False
    data["name"] = new_name
    data["updated_at"] = datetime.now().isoformat()
    _write(path, data)
    return True


def resolve_session(arg: str, pool: list[dict]) -> dict | None:
    """Resolve a session by 1-based index number or ID prefix."""
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(pool):
            return pool[idx]
    else:
        for s in pool:
            if s.get("id", "").startswith(arg):
                return s
    return None


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

def trash_list() -> list[dict]:
    if not TRASH_DIR.exists():
        return []
    out = []
    for f in sorted(TRASH_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        d = _read(f)
        if d:
            out.append(d)
    return out


def session_delete(sid: str) -> bool:
    """Move a session to trash."""
    src = SESSIONS_DIR / f"{sid}.json"
    data = _read(src)
    if not data:
        return False
    data["trashed_at"] = datetime.now().isoformat()
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    _write(TRASH_DIR / f"{sid}.json", data)
    src.unlink(missing_ok=True)
    return True


def session_restore(sid: str) -> bool:
    """Restore a session from trash."""
    src = TRASH_DIR / f"{sid}.json"
    data = _read(src)
    if not data:
        return False
    data.pop("trashed_at", None)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _write(SESSIONS_DIR / f"{sid}.json", data)
    src.unlink(missing_ok=True)
    return True


def session_purge(sid: str) -> bool:
    """Permanently delete a session from trash."""
    path = TRASH_DIR / f"{sid}.json"
    if not path.exists():
        return False
    path.unlink()
    return True


def trash_purge_all() -> int:
    """Permanently delete all trashed sessions. Returns count."""
    if not TRASH_DIR.exists():
        return 0
    files = list(TRASH_DIR.glob("*.json"))
    for f in files:
        f.unlink(missing_ok=True)
    return len(files)

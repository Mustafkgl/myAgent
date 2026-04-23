"""
Auth mode detection, model selection, and runtime configuration management.
Handles persistence of API keys and modes to ~/.myagent/config.json.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

AuthMode = Literal["api", "cli", "claude"]

API: AuthMode = "api"
CLI: AuthMode = "cli"
CLAUDE_WORKER: AuthMode = "claude"

CONFIG_PATH: Path = Path.home() / ".myagent" / "config.json"

# Module-level runtime overrides
_overrides: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Key Management: Prioritize environment, then fallback to persisted config
# ---------------------------------------------------------------------------

def _load_keys_from_disk() -> tuple[str, str]:
    """Helper to get keys from config file if environment is missing."""
    c_key = ""
    g_key = ""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            c_key = (data.get("anthropic_api_key") or data.get("ANTHROPIC_API_KEY") or "")
            g_key = (data.get("gemini_api_key") or data.get("GEMINI_API_KEY") or 
                     data.get("google_api_key") or data.get("GOOGLE_API_KEY") or "")
        except Exception: pass
    return c_key.strip(), g_key.strip()

# Initialize from env OR disk
_disk_c, _disk_g = _load_keys_from_disk()
ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or _disk_c).strip()
GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or _disk_g).strip()


def apply_overrides(**kwargs: str | None) -> None:
    for key, val in kwargs.items():
        if val is not None: _overrides[key] = val


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try: return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}


def save_config(config: dict) -> None:
    """Merge *config* into disk. ENSURES keys are persisted if provided."""
    existing = load_config()
    existing.update(config)
    
    # If keys are being passed in directly (e.g. from AuthScreen), ensure they match our storage names
    if "anthropic_api_key" in config: existing["anthropic_api_key"] = config["anthropic_api_key"]
    if "gemini_api_key" in config: existing["gemini_api_key"] = config["gemini_api_key"]
    
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    
    # Refresh global key variables after saving
    global ANTHROPIC_API_KEY, GEMINI_API_KEY
    if "anthropic_api_key" in config: ANTHROPIC_API_KEY = config["anthropic_api_key"]
    if "gemini_api_key" in config: GEMINI_API_KEY = config["gemini_api_key"]


# ---------------------------------------------------------------------------
# Detection Helpers
# ---------------------------------------------------------------------------

def detect_claude() -> list[AuthMode]:
    """Return available auth modes for Claude."""
    modes: list[AuthMode] = []
    if ANTHROPIC_API_KEY: modes.append(API)
    if _claude_cli_ready(): modes.append(CLI)
    return modes


def detect_gemini() -> list[AuthMode]:
    """Return available worker backends."""
    modes: list[AuthMode] = []
    if GEMINI_API_KEY: modes.append(API)
    if _gemini_cli_ready(): modes.append(CLI)
    if _claude_cli_ready(): modes.append(CLAUDE_WORKER)
    return modes


def _claude_cli_ready() -> bool:
    if not shutil.which("claude"): return False
    if not (Path.home() / ".claude").exists(): return False
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception: return False


def _gemini_cli_ready() -> bool:
    if not shutil.which("gemini"): return False
    if not (Path.home() / ".gemini").exists(): return False
    try:
        r = subprocess.run(["gemini", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception: return False


# ---------------------------------------------------------------------------
# Getters (override > config > env/disk default)
# ---------------------------------------------------------------------------

def get_claude_mode() -> AuthMode:
    env = os.environ.get("MYAGENT_CLAUDE_MODE", "").strip()
    return (_overrides.get("claude_mode") or env or load_config().get("claude_mode", CLI)) or CLI # type: ignore


def get_gemini_mode() -> AuthMode:
    env = os.environ.get("MYAGENT_GEMINI_MODE", "").strip()
    return (_overrides.get("gemini_mode") or env or load_config().get("gemini_mode", CLI)) or CLI # type: ignore


def get_claude_model() -> str:
    from myagent.models import CLAUDE_DEFAULT, resolve_model
    raw = (_overrides.get("claude_model") or load_config().get("claude_model", CLAUDE_DEFAULT))
    return resolve_model(raw, "claude")


def get_gemini_model() -> str:
    from myagent.models import GEMINI_DEFAULT, resolve_model
    raw = (_overrides.get("gemini_model") or load_config().get("gemini_model", GEMINI_DEFAULT))
    return resolve_model(raw, "gemini")


def get_max_steps() -> int:
    from myagent.config.settings import MAX_STEPS
    raw = _overrides.get("max_steps") or load_config().get("max_steps")
    try: return int(raw) if raw is not None else MAX_STEPS
    except Exception: return MAX_STEPS

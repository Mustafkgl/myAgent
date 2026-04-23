"""
AuthScreen — Textual full-screen auth & mode configuration.
Guarantees API keys are persisted for Live Model Discovery.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioButton, RadioSet, Static

from myagent.config.auth import (
    API, CLI, CLAUDE_WORKER,
    detect_claude, detect_gemini,
    load_config, save_config,
)
from myagent.ui import C_CLAUDE, C_DIM, C_ERR, C_GEMINI, C_OK, C_WARN
from myagent.utils.logger import log

ENV_FILE = Path.home() / ".myagent" / ".env"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _radio_select(radio_set: RadioSet, index: int) -> None:
    buttons = list(radio_set.query(RadioButton))
    if 0 <= index < len(buttons):
        buttons[index].value = True


def _save_env(key: str, value: str) -> None:
    """Persist an env var to ~/.myagent/.env (upsert)."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def _load_env_file() -> None:
    """Load ~/.myagent/.env into os.environ (called on startup)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k and v and not os.environ.get(k):
            os.environ[k] = v


class AuthScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
        ("ctrl+s",  "save",          "Save"),
    ]

    CSS = """
    AuthScreen { background: $surface; }
    #auth-scroll { padding: 1 4; }
    .auth-title { text-style: bold; color: $primary; margin-top: 1; margin-bottom: 0; }
    .auth-subtitle { margin-bottom: 1; }
    .auth-nav-hint { color: $text-muted; margin-bottom: 1; }
    RadioSet { margin: 0 0 1 2; width: auto; max-width: 72; }
    .key-input { margin: 0 0 1 2; max-width: 60; }
    .cli-status  { margin: 0 0 0 2; }
    .cli-install-hint { margin: 0 0 1 2; }
    .login-btn { margin: 0 0 1 2; width: auto; }
    .save-btn { margin-top: 2; margin-bottom: 1; width: 30; align-horizontal: center; }
    .divider { margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="auth-scroll"):
            yield Static("Authentication & Connectivity Settings", classes="auth-title")
            yield Static("  ↑ ↓ Change option  ·  Tab Next  ·  Enter / Save Button to Apply\n", classes="auth-nav-hint")

            # ── Claude (Planner) ──
            yield Static("PLANNER  —  Claude  [dim]( ↑ ↓ select )[/dim]", classes="auth-title")
            yield Static("  Enter API Key for direct sync and pay-as-you-go usage.", classes="auth-subtitle")
            with RadioSet(id="claude-radio"):
                yield RadioButton("API Key Mode", id="claude-api-rb")
                yield RadioButton("Claude Code CLI Mode", id="claude-cli-rb")

            yield Input(password=True, placeholder="sk-ant-api03-...", id="claude-key-input", classes="key-input")
            yield Static("", id="claude-cli-status", classes="cli-status")
            yield Static("", id="claude-cli-hint",   classes="cli-install-hint")
            yield Button("claude login", id="claude-login-btn", classes="login-btn", variant="primary")

            yield Static("─" * 60, classes="divider")

            # ── Worker (Gemini / Claude) ──
            yield Static("WORKER  —  Gemini/Claude  [dim]( ↑ ↓ select )[/dim]", classes="auth-title")
            yield Static("  Enter Gemini API Key for high-speed execution.", classes="auth-subtitle")
            with RadioSet(id="worker-radio"):
                yield RadioButton("Gemini API", id="worker-api-rb")
                yield RadioButton("Claude Code (Worker)", id="worker-claude-rb")
                yield RadioButton("Gemini CLI", id="worker-cli-rb")

            yield Input(password=True, placeholder="AIzaSy...", id="gemini-key-input", classes="key-input")
            yield Static("", id="worker-cli-status", classes="cli-status")
            yield Static("", id="worker-cli-hint",   classes="cli-install-hint")
            yield Button("gemini login", id="gemini-login-btn", classes="login-btn", variant="primary")

            yield Button("  Save and Apply Settings  ", id="save-btn", classes="save-btn", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self._claude_cli = _claude_cli_state()
        self._gemini_cli = _gemini_cli_state()
        cfg = load_config()
        
        # Load from config file OR environment
        self._current_claude_mode = cfg.get("claude_mode", CLI)
        self._current_worker_mode = cfg.get("gemini_mode", API)
        
        ck = (cfg.get("anthropic_api_key") or cfg.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", ""))
        gk = (cfg.get("gemini_api_key") or cfg.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", ""))

        if ck: self.query_one("#claude-key-input", Input).value = ck
        if gk: self.query_one("#gemini-key-input", Input).value = gk

        self.call_after_refresh(self._init_selections)

    def _init_selections(self) -> None:
        claude_idx = 0 if self._current_claude_mode == API else 1
        _radio_select(self.query_one("#claude-radio", RadioSet), claude_idx)
        worker_idx = {API: 0, CLAUDE_WORKER: 1, CLI: 2}.get(self._current_worker_mode, 0)
        _radio_select(self.query_one("#worker-radio", RadioSet), worker_idx)
        self._refresh_claude_ui(self._current_claude_mode)
        self._refresh_worker_ui(self._current_worker_mode)
        self.query_one("#claude-radio", RadioSet).focus()

    @on(RadioSet.Changed, "#claude-radio")
    def claude_radio_changed(self, event: RadioSet.Changed) -> None:
        self._refresh_claude_ui(API if event.index == 0 else CLI)

    @on(RadioSet.Changed, "#worker-radio")
    def worker_radio_changed(self, event: RadioSet.Changed) -> None:
        self._refresh_worker_ui([API, CLAUDE_WORKER, CLI][event.index])

    def _refresh_claude_ui(self, mode: str) -> None:
        key_input = self.query_one("#claude-key-input", Input)
        cli_status = self.query_one("#claude-cli-status", Static)
        login_btn = self.query_one("#claude-login-btn", Button)
        key_input.display = True # Always show key input for sustainable discovery
        login_btn.display = (mode == CLI)
        if mode == CLI:
            cli_status.update("✓ CLI Mode active" if self._claude_cli == "ready" else "⚠ CLI not logged in")
            cli_status.display = True
        else: cli_status.display = False

    def _refresh_worker_ui(self, mode: str) -> None:
        key_input = self.query_one("#gemini-key-input", Input)
        cli_status = self.query_one("#worker-cli-status", Static)
        login_btn = self.query_one("#gemini-login-btn", Button)
        key_input.display = True # Always show
        login_btn.display = (mode == CLI)
        if mode == CLI:
            cli_status.update("✓ Gemini CLI active" if self._gemini_cli == "ready" else "⚠ CLI not ready")
            cli_status.display = True
        else: cli_status.display = False

    @on(Button.Pressed, "#save-btn")
    def action_save(self) -> None:
        claude_idx = self.query_one("#claude-radio", RadioSet).pressed_index or 0
        worker_idx = self.query_one("#worker-radio", RadioSet).pressed_index or 0
        claude_mode = API if claude_idx == 0 else CLI
        worker_mode = [API, CLAUDE_WORKER, CLI][worker_idx]

        ck = self.query_one("#claude-key-input", Input).value.strip()
        gk = self.query_one("#gemini-key-input", Input).value.strip()

        # PERSIST EVERYTHING
        config_payload = {
            "claude_mode": claude_mode,
            "gemini_mode": worker_mode,
            "anthropic_api_key": ck,
            "gemini_api_key": gk
        }
        
        save_config(config_payload)
        
        if ck: _save_env("ANTHROPIC_API_KEY", ck)
        if gk: _save_env("GEMINI_API_KEY", gk)

        log.info(f"Auth Settings Saved. Mode: C={claude_mode}, W={worker_mode}. Keys persisted.")
        self.app.notify("✓ Settings Applied & Persisted.", severity="information")
        self.app.pop_screen()


def _claude_cli_state() -> str:
    if not shutil.which("claude"): return "not_installed"
    try:
        r = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        return "ready" if r.returncode == 0 else "no_auth"
    except Exception: return "no_auth"

def _gemini_cli_state() -> str:
    if not shutil.which("gemini"): return "not_installed"
    try:
        r = subprocess.run(["gemini", "--version"], capture_output=True, timeout=5)
        return "ready" if r.returncode == 0 else "no_auth"
    except Exception: return "no_auth"

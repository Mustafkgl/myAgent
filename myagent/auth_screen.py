"""
AuthScreen — Textual full-screen auth & mode configuration.
Now includes a "Test Connection" button for live API verification.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on, work
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
from myagent.models import fetch_all_models

ENV_FILE = Path.home() / ".myagent" / ".env"

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
    .login-btn { margin: 0 0 1 2; width: auto; }
    #test-status { margin: 1 0 1 2; height: 1; color: $text-muted; }
    .action-row { margin-top: 2; height: 3; align-horizontal: center; }
    .save-btn { width: 30; margin-right: 2; }
    .test-btn { width: 25; }
    .divider { margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="auth-scroll"):
            yield Static("Authentication & Connectivity Settings", classes="auth-title")
            yield Static("  Enter your keys and test the connection before saving.\n", classes="auth-nav-hint")

            # ── Claude ──
            yield Static("PLANNER  —  Claude", classes="auth-title")
            with RadioSet(id="claude-radio"):
                yield RadioButton("API Key Mode", id="claude-api-rb")
                yield RadioButton("Claude Code CLI Mode", id="claude-cli-rb")
            yield Input(password=True, placeholder="sk-ant-api03-...", id="claude-key-input", classes="key-input")
            yield Button("claude login", id="claude-login-btn", classes="login-btn", variant="primary")

            yield Static("─" * 60, classes="divider")

            # ── Worker ──
            yield Static("WORKER  —  Gemini/Claude", classes="auth-title")
            with RadioSet(id="worker-radio"):
                yield RadioButton("Gemini API", id="worker-api-rb")
                yield RadioButton("Claude Code (Worker)", id="worker-claude-rb")
                yield RadioButton("Gemini CLI", id="worker-cli-rb")
            yield Input(password=True, placeholder="AIzaSy...", id="gemini-key-input", classes="key-input")
            yield Button("gemini login", id="gemini-login-btn", classes="login-btn", variant="primary")

            yield Static("", id="test-status")

            with Horizontal(classes="action-row"):
                yield Button("Test Connection", id="test-btn", classes="test-btn", variant="primary")
                yield Button("Save and Continue", id="save-btn", classes="save-btn", variant="success")
        yield Footer()

    def on_mount(self) -> None:
        self._claude_cli = _claude_cli_state()
        self._gemini_cli = _gemini_cli_state()
        cfg = load_config()
        self._current_claude_mode = cfg.get("claude_mode", CLI)
        self._current_worker_mode = cfg.get("gemini_mode", API)
        
        # Load keys from persisted config
        ck = (cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", ""))
        gk = (cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", ""))

        if ck: self.query_one("#claude-key-input", Input).value = ck
        if gk: self.query_one("#gemini-key-input", Input).value = gk
        self.call_after_refresh(self._init_selections)

    def _init_selections(self) -> None:
        c_idx = 0 if self._current_claude_mode == API else 1
        _radio_select(self.query_one("#claude-radio", RadioSet), c_idx)
        w_idx = {API: 0, CLAUDE_WORKER: 1, CLI: 2}.get(self._current_worker_mode, 0)
        _radio_select(self.query_one("#worker-radio", RadioSet), w_idx)
        self.query_one("#claude-radio", RadioSet).focus()

    @on(Button.Pressed, "#test-btn")
    def on_test_connection(self) -> None:
        """Trigger connection test in a background worker."""
        status = self.query_one("#test-status", Static)
        status.update(Text("⏳ Testing connection to APIs...", style="yellow"))
        
        ck = self.query_one("#claude-key-input", Input).value.strip()
        gk = self.query_one("#gemini-key-input", Input).value.strip()
        
        # Inject temporarily to runtime for testing
        if ck: os.environ["ANTHROPIC_API_KEY"] = ck
        if gk: os.environ["GEMINI_API_KEY"] = gk
        
        self._run_live_test()

    @work(thread=True)
    def _run_live_test(self) -> None:
        try:
            models = fetch_all_models()
            claude_count = len([m for m in models if m.provider == "claude" and "(Direct API)" in m.description])
            gemini_count = len([m for m in models if m.provider == "gemini" and "(Direct API)" in m.description])
            
            msg = f"✓ Success! Found {claude_count} Claude models and {gemini_count} Gemini models."
            self.app.call_from_thread(self._update_test_status, msg, "green")
        except Exception as e:
            self.app.call_from_thread(self._update_test_status, f"✗ Test Failed: {str(e)}", "red")

    def _update_test_status(self, msg: str, color: str) -> None:
        self.query_one("#test-status", Static).update(Text(msg, style=color))

    @on(Button.Pressed, "#save-btn")
    def action_save(self) -> None:
        c_idx = self.query_one("#claude-radio", RadioSet).pressed_index or 0
        w_idx = self.query_one("#worker-radio", RadioSet).pressed_index or 0
        ck = self.query_one("#claude-key-input", Input).value.strip()
        gk = self.query_one("#gemini-key-input", Input).value.strip()

        save_config({
            "claude_mode": API if c_idx == 0 else CLI,
            "gemini_mode": [API, CLAUDE_WORKER, CLI][w_idx],
            "anthropic_api_key": ck,
            "gemini_api_key": gk
        })
        self.app.notify("✓ Configuration Saved Permanently.")
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

def _radio_select(radio_set: RadioSet, index: int) -> None:
    buttons = list(radio_set.query(RadioButton))
    if 0 <= index < len(buttons): buttons[index].value = True

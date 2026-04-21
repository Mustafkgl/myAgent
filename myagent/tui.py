"""
myagent TUI — Level 2 Clean Architecture (English Edition)
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.markdown import Markdown
from rich.rule import Rule
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key
from textual.widgets import (
    Button,
    Checkbox,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Select,
    Static,
    TextArea,
)
from textual.screen import ModalScreen
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.widgets.option_list import Option
from textual.binding import Binding

from myagent.agent.chat import Chat
from myagent.agent.doctor import run_diagnostics
from myagent.agent.sessions import (
    SESSIONS_DIR as _SESSIONS_DIR,
    extract_topic as _extract_topic,
    resolve_session as _resolve_session,
    session_delete, session_rename, session_restore, session_purge, trash_purge_all,
    sessions_list as _sessions_list_new,
    sessions_save as _sessions_save_new,
    trash_list,
)
from myagent.ui import AgentUI, C_CLAUDE, C_DIM, C_GEMINI, C_OK, C_WARN, C_ERR

if TYPE_CHECKING:
    from myagent.cli import SessionState


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class PromptInput(Input):
    """Custom Input that doesn't clutter the footer and respects app-level shortcuts."""
    can_focus = True
    BINDINGS = [
        Binding("ctrl+e", "app.toggle_sidebar", "Process"),
        Binding("ctrl+k", "app.copy_mode", "Selection"),
        Binding("left", "cursor_left", "Left", show=False),
        Binding("right", "cursor_right", "Right", show=False),
        Binding("home", "home", "Home", show=False),
        Binding("end", "end", "End", show=False),
        Binding("delete", "delete_forward", "Delete", show=False),
        Binding("backspace", "delete_left", "Backspace", show=False),
        Binding("ctrl+a", "home", "Home", show=False),
    ]

class SettingsModal(ModalScreen):
    """A modal for updating agent configuration on the fly."""
    CSS = """
    SettingsModal { align: center middle; }
    #settings-container {
        width: 60; height: 35;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    .setting-row { height: 3; margin-bottom: 1; }
    .setting-row Label { width: 20; padding-top: 1; }
    #modal-title { text-align: center; text-style: bold; width: 100%; margin-bottom: 1; color: $primary; }
    #button-row { align: center middle; margin-top: 2; height: 3; }
    Button { margin: 0 1; }
    """
    def compose(self) -> ComposeResult:
        from myagent.config.auth import get_claude_model, get_gemini_model
        from myagent.models import CLAUDE_CURATED, GEMINI_CURATED
        
        yield Grid(
            Label("🔧 SETTINGS", id="modal-title"),
            Horizontal(Label("Claude Model:"), Select([(m.id, m.id) for m in CLAUDE_CURATED], value=get_claude_model(), id="claude-model"), classes="setting-row"),
            Horizontal(Label("Gemini Model:"), Select([(m.id, m.id) for m in GEMINI_CURATED], value=get_gemini_model(), id="gemini-model"), classes="setting-row"),
            Horizontal(Label("Auto-Approve:"), Checkbox(value=True, id="auto-approve"), classes="setting-row"),
            Horizontal(Label("Dry Run Mode:"), Checkbox(value=False, id="dry-run"), classes="setting-row"),
            Horizontal(Button("Save", variant="success", id="save-settings"), Button("Cancel", variant="error", id="cancel-settings"), id="button-row"),
            id="settings-container"
        )
    @on(Button.Pressed, "#save-settings")
    def save(self) -> None: self.dismiss(True)
    @on(Button.Pressed, "#cancel-settings")
    def cancel(self) -> None: self.dismiss(False)

class CopyModal(ModalScreen):
    """A modal for text selection."""
    def __init__(self, content: str):
        super().__init__()
        self.content = content
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="copy-container"):
            yield Label("📄 SELECTION MODE (Esc: Exit / Mouse to select & copy)", id="copy-title")
            yield TextArea(self.content, read_only=True, id="copy-area")
            yield Footer()
    CSS = """
    CopyModal { align: center middle; }
    #copy-container { width: 90%; height: 90%; border: thick $primary; background: $surface; padding: 1; }
    #copy-title { text-align: center; text-style: bold; background: $primary; color: white; margin-bottom: 1; width: 100%; }
    #copy-area { height: 1fr; border: none; }
    """
    def on_mount(self) -> None: self.query_one("#copy-area").focus()
    BINDINGS = [("escape", "dismiss", "Back")]

# ---------------------------------------------------------------------------
# Slash commands registry
# ---------------------------------------------------------------------------

_COMMANDS: list[tuple[str, str]] = [
    ("/about",    "Version and model info"),
    ("/auth",     "Authentication screen"),
    ("/clear",    "Clear screen"),
    ("/compact",  "Compress history"),
    ("/config",   "Show configuration"),
    ("/doctor",   "System diagnostics"),
    ("/exit",     "Exit application"),
    ("/export",   "Export to Markdown"),
    ("/help",     "Show help"),
    ("/load",     "Load session <id>"),
    ("/model",    "Model selection"),
    ("/new",      "New session"),
    ("/sessions", "List sessions"),
    ("/status",   "Session stats"),
    ("/theme",    "Toggle dark/light"),
]

# ---------------------------------------------------------------------------
# TUI Bridge
# ---------------------------------------------------------------------------

class TuiAgentUI(AgentUI):
    def __init__(self, app: "MyAgentApp"):
        super().__init__(verbose=app.verbose)
        self.app = app
    def _log(self, renderable: Any) -> None: self.app.call_from_thread(self.app.log_message, renderable)
    def _update_sidebar(self, widget_id: str, content: Any) -> None:
        def update():
            try: self.app.query_one(f"#{widget_id}", Static).update(content)
            except Exception: pass
        self.app.call_from_thread(update)
    def header(self, task: str, cm: str, gm: str) -> None:
        self._log(Rule(f"[{C_CLAUDE}]{task}[/]", style=C_DIM))
        self._update_sidebar("pipeline-status", Text(f"🚀 Task Started\n{task[:30]}...", style="bold green"))
    def plan_done(self, steps: list[str]) -> None:
        sidebar_t = Text("📋 Planned Steps:\n", style="bold #c084fc")
        for i, s in enumerate(steps, 1): sidebar_t.append(f"  {i}. {s[:35]}...\n", style="white")
        self._update_sidebar("pipeline-steps", sidebar_t)
    def exec_results(self, steps: list[str], results: list[Any]) -> None:
        t = Text("\n  Execution Results:\n", style=C_GEMINI)
        for i, (step, r) in enumerate(zip(steps, results), 1):
            t.append(f"    {i}. {'✓' if r.ok else '✗'} {r.message}\n", style=C_OK if r.ok else C_ERR)
        self._log(t)
    def chat_answer(self, text: str) -> None: self.app._last_answer = text
    def summary(self, success: bool, review: bool, n: int, files: list[str]) -> None:
        status = "✓ Completed" if success else "✗ Failed"
        self._update_sidebar("pipeline-status", Text(status, style=f"bold {C_OK if success else C_ERR}"))
    def ask_approval(self) -> bool:
        self.app._approval_event = asyncio.Event()
        self.app._approval_result = False
        def prep():
            inp = self.app.query_one("#user-input", PromptInput)
            inp.placeholder = "Proceed? (y/n)"; inp.focus()
        self.app.call_from_thread(prep)
        loop = self.app.call_from_thread(asyncio.get_running_loop)
        asyncio.run_coroutine_threadsafe(self.app._approval_event.wait(), loop).result()
        return self.app._approval_result
    @contextmanager
    def streaming(self, label: str, color: str = C_DIM):
        self._update_sidebar("pipeline-status", Text(f"⏳ {label}", style=f"bold {color}"))
        yield lambda x: None
    @contextmanager
    def spinner(self, label: str, color: str = C_DIM):
        self._update_sidebar("pipeline-status", Text(f"⚙️ {label}", style=f"bold {color}"))
        yield

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

_BANNER = """\
                              █████████
                             ███░░░░░███
 █████████████   █████ ████ ░███    ░███   ███████  ██████  ████████   █████
░░███░░███░░███ ░░███ ░███  ░███████████  ███░░███ ███░░███░░███░░███ ░░███
 ░███ ░███ ░███  ░███ ░███  ░███░░░░░███ ░███ ░███░███████  ░███ ░███ ███████
 ░███ ░███ ░███  ░███ ░███  ░███    ░███ ░███ ░███░███░░░   ░███ ░███░░░███░
 █████░███ █████ ░░███████  █████   █████░░███████░░██████  ████ ████  ░███
░░░░░ ░░░ ░░░░░   ░░░░░███ ░░░░░   ░░░░░  ░░░░░███ ░░░░░░  ░░░░ ░░░░░  ░███ ███
                  ███ ░███                ███ ░███                     ░░█████
                 ░░██████                ░░██████                       ░░░░░
                  ░░░░░░                  ░░░░░░"""

class MyAgentApp(App):
    TITLE = "myAgent"
    CSS = """
    Screen { background: $surface; }
    #main-container { height: 1fr; }
    #file-tree { width: 20%; min-width: 25; background: $panel; border-right: solid $primary; }
    #chat-log { width: 1fr; min-width: 40; padding: 0 2; }
    #pipeline-sidebar { width: 25%; min-width: 30; background: $panel; border-left: solid $primary; padding: 1 2; }
    #sidebar-title { text-align: center; text-style: bold; width: 100%; background: $primary; color: white; margin-bottom: 1; }
    #pipeline-status { margin-bottom: 1; }
    #autocomplete { display: none; max-height: 10; border: solid $primary; background: $panel; }
    #input-container { height: 3; dock: bottom; border-top: solid $primary; padding: 0 1; }
    Input { border: none; background: $surface; width: 1fr; }
    .input-prompt { color: $primary; text-style: bold; width: 4; }
    Footer { background: $surface; }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Exit"), ("ctrl+b", "toggle_tree", "Files"),
        ("ctrl+e", "toggle_sidebar", "Process"), ("ctrl+k", "copy_mode", "Selection"),
        ("ctrl+s", "open_settings", "Settings"), ("ctrl+l", "clear_log", "Clear"),
        ("ctrl+y", "copy_last", "Copy"), ("f1", "help", "Help"),
    ]

    def __init__(self, session_state: "SessionState", verbose: bool = False):
        super().__init__()
        self.session = session_state
        self.verbose = verbose
        self._msgs: list[dict] = []
        if not self.session.chat: self.session.chat = Chat()
        self.ui_bridge = TuiAgentUI(self)
        self._approval_event: asyncio.Event | None = None
        self._approval_result: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            yield DirectoryTree("./", id="file-tree")
            yield VerticalScroll(id="chat-log")
            with VerticalScroll(id="pipeline-sidebar"):
                yield Label("PROCESS TRACKING", id="sidebar-title")
                yield Static("", id="pipeline-status")
                yield Static("", id="pipeline-steps")
                yield Static("", id="pipeline-logs")
        yield OptionList(id="autocomplete")
        with Horizontal(id="input-container"):
            yield Label(" ❯ ", classes="input-prompt")
            yield PromptInput(placeholder="What can I build for you today?", id="user-input")
        yield Footer()

    def action_toggle_tree(self) -> None: self.query_one("#file-tree").display = not self.query_one("#file-tree").display
    def action_toggle_sidebar(self) -> None: self.query_one("#pipeline-sidebar").display = not self.query_one("#pipeline-sidebar").display
    def action_open_settings(self) -> None: self.push_screen(SettingsModal(), self._on_settings_closed)
    def action_copy_mode(self) -> None:
        txt = "".join([f"=== {m['role'].upper()} ===\n{m['text']}\n\n" for m in self._msgs])
        if txt: self.push_screen(CopyModal(txt))
    def _on_settings_closed(self, saved: bool) -> None:
        if saved: self.log_message(Text("  ✅ Settings updated.", style="green"))

    def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", VerticalScroll)
        from myagent.config.auth import get_claude_model, get_gemini_model
        self.log_message(Text(_BANNER, style="bold #c084fc"))
        self.log_message(Text.assemble(("  v2.0.0  ·  ", "dim"), ("◆ ", "bold #D97706"), ("Claude", "bold #D97706"), (" plans  ·  ", "dim"), ("✦ ", "bold #4285F4"), ("Gemini", "bold #E8EAED"), (" executes\n", "dim")))
        self.log_message(Text.assemble(("  ◆ ", "#D97706"), (get_claude_model(), "#D97706"), ("  ✦ ", "#4285F4"), (get_gemini_model(), "#E8EAED"), ("\n", "")))
        self.query_one("#user-input", PromptInput).focus()

    def log_message(self, renderable: Any) -> None:
        self.chat_log.mount(Static(renderable))
        self.chat_log.scroll_end(animate=False)

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text: return
        
        inp = self.query_one("#user-input", PromptInput)
        
        if self._approval_event and not self._approval_event.is_set():
            inp.value = ""
            self._approval_result = text.lower() in ("y", "yes", "ok", "")
            self._approval_event.set(); return
            
        inp.value = ""
        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            await self._cmd(parts[0].lower(), parts[1] if len(parts) > 1 else "")
        else:
            self._show_user(text)
            self.process_chat(text)

    def _show_user(self, text: str) -> None:
        self.log_message(Text.assemble(("\n  ", ""), ("You  ", f"bold {C_GEMINI}"), (text, "bold white"), ("\n", "")))

    async def _run_pipeline(self, task: str) -> None:
        from myagent.agent.pipeline import run
        t0 = time.time()
        try:
            fn = functools.partial(run, task, verbose=self.verbose, ui=self.ui_bridge)
            result = await asyncio.get_event_loop().run_in_executor(None, fn)
            elapsed = time.time() - t0
            icon = "✓" if result.success else "✗"
            color = C_OK if result.success else C_ERR
            self.log_message(Text.assemble(("\n  " + icon + " ", f"bold {color}"), (f"{elapsed:.1f}s  files: ", "dim"), (", ".join(result.created_files[:4]) or "—" + "\n", "white")))
        except Exception as e:
            self.log_message(Text(f"\n  ✗ Error: {e}\n", style=f"bold {C_ERR}"))

    @work(exclusive=True, group="ai")
    async def process_chat(self, text: str) -> None:
        self.log_message(Text("  ⊛ thinking…\n", style=f"dim {C_CLAUDE}"))
        route = await asyncio.get_event_loop().run_in_executor(None, self.session.chat.route, text)
        if route.action == "answer":
            self._last_answer = route.answer
            self.log_message(Text.assemble(("  Claude\n", f"bold {C_CLAUDE}")))
            self.log_message(Markdown(route.answer))
            self.log_message(Text(""))
            self._msgs.append({"role": "user", "text": text})
            self._msgs.append({"role": "assistant", "text": route.answer})
        else: await self._run_pipeline(route.task or text)

    async def _cmd(self, cmd: str, arg: str) -> None:
        if cmd in ("exit", "quit"): self.exit()
        elif cmd == "clear": self.chat_log.remove_children()
        elif cmd == "status": self._cmd_status()
        elif cmd == "theme":
            self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
            self.log_message(Text(f"  ✓ Theme: {self.theme}\n", style=C_OK))
        else: self._show_user(f"/{cmd} {arg}"); self._run_pipeline(f"{cmd} {arg}".strip())

    def _cmd_status(self) -> None:
        self.log_message(Text.assemble(("\n  Session Status\n", f"bold {C_CLAUDE}"), ("  Theme:      ", "dim"), (f"{self.theme}\n", "white")))

def start_tui(session: "SessionState", verbose: bool = False) -> None:
    app = MyAgentApp(session, verbose=verbose)
    app.run(mouse=True)

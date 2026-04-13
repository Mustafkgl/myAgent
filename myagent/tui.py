"""
myagent TUI — Textual-based responsive terminal interface.
"""

from __future__ import annotations

import asyncio
import functools
import json
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
from textual.containers import Horizontal
from textual.events import Key
from textual.widgets import Footer, Header, Input, Label, RichLog

from myagent.agent.chat import Chat
from myagent.ui import AgentUI, C_CLAUDE, C_DIM, C_GEMINI, C_OK, C_WARN, C_ERR

if TYPE_CHECKING:
    from myagent.cli import SessionState


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

_SESSIONS_DIR = Path.home() / ".myagent" / "sessions"


def _sessions_save(sid: str, name: str, messages: list[dict]) -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = {"id": sid, "name": name, "updated_at": datetime.now().isoformat(), "messages": messages}
    (_SESSIONS_DIR / f"{sid}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _sessions_list() -> list[dict]:
    if not _SESSIONS_DIR.exists():
        return []
    out = []
    for f in sorted(_SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# TUI-specific UI Bridge
# ---------------------------------------------------------------------------

class TuiAgentUI(AgentUI):
    def __init__(self, app: "MyAgentApp"):
        super().__init__(verbose=app.verbose)
        self.app = app

    def _log(self, renderable: Any) -> None:
        self.app.call_from_thread(self.app.log_message, renderable)

    def header(self, task: str, claude_model: str, gemini_model: str) -> None:
        self._log(Rule(f"[{C_CLAUDE}]{task}[/]", style=C_DIM))

    def plan_done(self, steps: list[str]) -> None:
        t = Text(f"\n  Plan ({len(steps)} adım):\n", style=C_CLAUDE)
        for i, s in enumerate(steps, 1):
            t.append(f"    {i}. ", style=C_DIM)
            t.append(f"{s}\n")
        self._log(t)

    def exec_results(self, steps: list[str], results: list[Any]) -> None:
        t = Text(f"\n  Yürütme:\n", style=C_GEMINI)
        for i, (step, r) in enumerate(zip(steps, results), 1):
            icon = "✓" if r.ok else "✗"
            color = C_OK if r.ok else C_ERR
            t.append(f"    {i}. ", style=C_DIM)
            t.append(f"{icon} ", style=color)
            t.append(f"{r.message}\n")
        self._log(t)

    def chat_answer(self, text: str) -> None:
        self.app._last_answer = text

    def session_context_notice(self, notice: str) -> None:
        self._log(Text(f"  ℹ {notice}", style=C_DIM))

    def summary(self, success: bool, review_approved: bool,
                n_review_rounds: int, created_files: list[str]) -> None:
        status = "✓ Tamamlandı" if success else "✗ Hatalarla tamamlandı"
        color = C_OK if success else C_WARN
        self._log(Text(f"\n  {status}\n", style=f"bold {color}"))

    @contextmanager
    def streaming(self, label: str, color: str = C_DIM):
        yield lambda x: None

    @contextmanager
    def spinner(self, label: str, color: str = C_DIM):
        yield


# ---------------------------------------------------------------------------
# Textual App
# ---------------------------------------------------------------------------

_BANNER = """\
  ╔╦╗╦ ╦╔═╗╔═╗╔═╗╔╗╔╔╦╗
  ║║║╚╦╝╠═╣║ ╦║╣ ║║║ ║
  ╩ ╩ ╩ ╩ ╩╚═╝╚═╝╝╚╝ ╩"""


class MyAgentApp(App):
    CSS = """
    Screen { background: $surface; }

    #chat-log {
        height: 1fr;
        padding: 0 2;
        scrollbar-size: 0 0;
    }

    #input-container {
        height: 3;
        dock: bottom;
        border-top: solid $primary;
        padding: 0 1;
    }

    Input { border: none; background: $surface; }
    """

    BINDINGS = [
        ("ctrl+c",  "quit",       "Çıkış"),
        ("ctrl+l",  "clear_log",  "Temizle"),
        ("ctrl+y",  "copy_last",  "Kopyala"),
        ("f1",      "help",       "Yardım"),
    ]

    def __init__(self, session_state: "SessionState", verbose: bool = False):
        super().__init__()
        self.session = session_state
        self.verbose = verbose
        self._last_answer: str = ""
        # Input history (↑↓ navigation)
        self._input_history: list[str] = []
        self._hist_pos: int = -1
        self._hist_draft: str = ""
        # Session
        self._sid   = str(uuid.uuid4())
        self._sname = datetime.now().strftime("%d %b %Y %H:%M")
        self._msgs: list[dict] = []
        if not self.session.chat:
            self.session.chat = Chat()
        self.ui_bridge = TuiAgentUI(self)

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        self.chat_log = RichLog(id="chat-log", highlight=True, markup=True)
        yield self.chat_log
        with Horizontal(id="input-container"):
            yield Label(" ❯ ", variant="bold")
            yield Input(placeholder="Ne yapmamı istersin?", id="user-input")
        yield Footer()

    def on_mount(self) -> None:
        from myagent.config.auth import get_claude_model, get_gemini_model
        self.log_message(Text(_BANNER, style=f"bold {C_CLAUDE}"))
        self.log_message(Text.assemble(
            ("  v1.0.0  ·  ", "dim"),
            ("Claude", f"bold {C_CLAUDE}"),
            (" planlar  ·  ", "dim"),
            ("Gemini", f"bold {C_GEMINI}"),
            (" yürütür\n", "dim"),
        ))
        self.log_message(Text.assemble(
            ("  ", ""),
            (get_claude_model(), C_CLAUDE),
            ("  /  ", "dim"),
            (get_gemini_model(), C_GEMINI),
            ("\n", ""),
        ))
        self.log_message(Text(
            "  ↑↓ geçmiş · Ctrl+Y kopyala · Ctrl+L temizle · F1 yardım\n",
            style="dim",
        ))
        self.query_one("#user-input").focus()

    def log_message(self, renderable: Any) -> None:
        self.chat_log.write(renderable)

    # ── ↑↓ input history ─────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        inp = self.query_one("#user-input", Input)
        if self.focused is not inp:
            return

        if event.key == "up":
            event.prevent_default()
            event.stop()
            if not self._input_history:
                return
            if self._hist_pos == -1:
                self._hist_draft = inp.value
                self._hist_pos = len(self._input_history) - 1
            elif self._hist_pos > 0:
                self._hist_pos -= 1
            inp.value = self._input_history[self._hist_pos]
            inp.cursor_position = len(inp.value)

        elif event.key == "down":
            event.prevent_default()
            event.stop()
            if self._hist_pos == -1:
                return
            if self._hist_pos < len(self._input_history) - 1:
                self._hist_pos += 1
                inp.value = self._input_history[self._hist_pos]
            else:
                self._hist_pos = -1
                inp.value = self._hist_draft
            inp.cursor_position = len(inp.value)

    # ── Input handler ─────────────────────────────────────────────────────────

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self._hist_pos = -1
        self._hist_draft = ""
        if not self._input_history or self._input_history[-1] != text:
            self._input_history.append(text)

        if text.startswith("/"):
            parts = text[1:].split(maxsplit=1)
            await self._cmd(parts[0].lower(), parts[1] if len(parts) > 1 else "")
        else:
            self._show_user(text)
            self.process_chat(text)

    def _show_user(self, text: str) -> None:
        self.log_message(Text.assemble(
            ("\n  ", ""),
            ("Sen  ", f"bold {C_GEMINI}"),
            (text, "bold white"),
            ("\n", ""),
        ))

    # ── Commands ──────────────────────────────────────────────────────────────

    async def _cmd(self, cmd: str, arg: str) -> None:
        if cmd in ("exit", "quit", "çıkış", "cikis"):
            self._autosave(); self.exit()

        elif cmd in ("help", "yardım", "yardim", "h"):
            self.action_help()

        elif cmd in ("clear", "cls", "temizle"):
            self.action_clear_log()

        elif cmd in ("sessions", "oturumlar", "gecmis", "geçmiş"):
            self._show_sessions()

        elif cmd in ("rename", "isimlendir", "adlandir"):
            if arg:
                self._sname = arg
                self._autosave()
                self.log_message(Text(f"  ✓ Oturum adı: {arg}\n", style=C_OK))
            else:
                self.log_message(Text("  Kullanım: /rename <yeni ad>\n", style=C_DIM))

        elif cmd in ("load", "yukle", "yükle", "aç", "ac"):
            await self._load_session(arg)

        elif cmd in ("new", "yeni"):
            self._autosave(); self._new_session()

        else:
            self._show_user(f"/{cmd}" + (f" {arg}" if arg else ""))
            self.process_task(f"{cmd} {arg}".strip())

    def _show_sessions(self) -> None:
        sessions = _sessions_list()
        if not sessions:
            self.log_message(Text("  Kayıtlı oturum yok.\n", style=C_DIM))
            return
        t = Text(f"\n  Oturumlar ({len(sessions)}):\n", style=f"bold {C_CLAUDE}")
        for i, s in enumerate(sessions[:20], 1):
            sid   = s.get("id", "")[:8]
            name  = s.get("name", "isimsiz")[:40]
            ts    = s.get("updated_at", "")[:16].replace("T", " ")
            n_msg = len(s.get("messages", []))
            t.append(f"  [{i:2}]  ", style=C_DIM)
            t.append(f"{name:<42}", style="white")
            t.append(f"  {ts}  ", style=C_DIM)
            t.append(f"{n_msg:3} mesaj  ", style=C_DIM)
            t.append(f"id:{sid}\n", style="dim")
        t.append("\n  /load <numara veya id>  ile yükle\n", style=C_DIM)
        self.log_message(t)

    async def _load_session(self, arg: str) -> None:
        if not arg:
            self.log_message(Text("  Kullanım: /load <numara veya id>\n", style=C_DIM))
            return
        sessions = _sessions_list()
        data = None
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(sessions):
                data = sessions[idx]
        else:
            for s in sessions:
                if s.get("id", "").startswith(arg):
                    data = s; break
        if not data:
            self.log_message(Text(f"  Oturum bulunamadı: {arg}\n", style=C_ERR))
            return

        self._autosave()
        self.action_clear_log()
        self._sid   = data["id"]
        self._sname = data.get("name", "yüklendi")
        self._msgs  = data.get("messages", [])

        # Replay visually
        for msg in self._msgs:
            if msg["role"] == "user":
                self.log_message(Text.assemble(
                    ("\n  ", ""), ("Sen  ", f"bold {C_GEMINI}"),
                    (msg["text"], "bold white"), ("\n", ""),
                ))
            else:
                ts = msg.get("ts", "")[:16].replace("T", " ")
                self.log_message(Text(f"  Claude  {ts}\n", style=f"bold {C_CLAUDE}"))
                self.log_message(Markdown(msg["text"]))
                self.log_message(Text(""))

        self.log_message(Text(f"\n  ✓ Yüklendi: {self._sname}\n", style=C_OK))

    def _new_session(self) -> None:
        self._sid   = str(uuid.uuid4())
        self._sname = datetime.now().strftime("%d %b %Y %H:%M")
        self._msgs  = []
        self.session.chat = Chat()
        self.action_clear_log()
        self.on_mount()

    def _autosave(self) -> None:
        if self._msgs:
            _sessions_save(self._sid, self._sname, self._msgs)

    # ── Workers ───────────────────────────────────────────────────────────────

    @work(exclusive=True, group="ai")
    async def process_chat(self, text: str) -> None:
        self.log_message(Text("  ⊛ düşünüyor…\n", style=f"dim {C_CLAUDE}"))
        t0 = time.time()
        loop = asyncio.get_event_loop()
        route = await loop.run_in_executor(None, self.session.chat.route, text)
        elapsed = time.time() - t0

        if route.action == "answer":
            answer = route.answer
            self._last_answer = answer
            self.log_message(Text.assemble(
                ("  Claude  ", f"bold {C_CLAUDE}"),
                (f"{elapsed:.1f}s\n", "dim"),
            ))
            self.log_message(Markdown(answer))
            self.log_message(Text(""))
            now = datetime.now().isoformat()
            self._msgs.append({"role": "user",      "text": text,   "ts": now})
            self._msgs.append({"role": "assistant",  "text": answer, "ts": now})
            self._autosave()
        else:
            await self._run_pipeline(route.task or text)

    @work(exclusive=True, group="ai")
    async def process_task(self, task: str) -> None:
        await self._run_pipeline(task)

    async def _run_pipeline(self, task: str) -> None:
        from myagent.agent.pipeline import run
        t0 = time.time()
        loop = asyncio.get_event_loop()
        try:
            fn = functools.partial(
                run, task,
                verbose=self.verbose, dry_run=False, batch=True, clarify=False,
                review=True, max_review_rounds=2, auto_deps=False,
                verify_completion=True, max_completion_rounds=2,
                session_context="", ui=self.ui_bridge,
            )
            result = await loop.run_in_executor(None, fn)
            elapsed = time.time() - t0
            self.session.update(result)
            if self.session.chat:
                self.session.chat.add_task_result(result.task_original, result.summary_en)
            files = ", ".join(result.created_files[:4]) or "—"
            self.log_message(Text.assemble(
                ("\n  ✓ ", f"bold {C_OK}"),
                (f"{elapsed:.1f}s  dosyalar: ", "dim"),
                (files + "\n", "white"),
            ))
            self._autosave()
        except Exception as e:
            self.log_message(Text(f"\n  ✗ Hata: {e}\n", style=f"bold {C_ERR}"))

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_clear_log(self) -> None:
        self.chat_log.clear()

    def action_copy_last(self) -> None:
        if not self._last_answer:
            self.notify("Kopyalanacak cevap yok.", severity="warning"); return
        self.copy_to_clipboard(self._last_answer)
        self.notify("Panoya kopyalandı.")

    def action_help(self) -> None:
        self.log_message(Markdown(
            "### Komutlar\n"
            "| Komut | Açıklama |\n"
            "|---|---|\n"
            "| `/help` | Bu yardım |\n"
            "| `/sessions` | Kayıtlı oturumları listele |\n"
            "| `/load <n>` | Oturum yükle (numara veya id) |\n"
            "| `/rename <ad>` | Mevcut oturumu yeniden adlandır |\n"
            "| `/new` | Yeni oturum başlat |\n"
            "| `/clear` | Ekranı temizle |\n"
            "| `/exit` | Çıkış |\n"
            "\n"
            "**Kısayollar:**  "
            "`↑` `↓` komut geçmişi  ·  "
            "`Ctrl+Y` son cevabı kopyala  ·  "
            "`Ctrl+L` temizle  ·  "
            "`F1` yardım\n"
        ))


def start_tui(session: "SessionState", verbose: bool = False) -> None:
    app = MyAgentApp(session, verbose=verbose)
    app.run(mouse=False)

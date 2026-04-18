"""
myagent TUI — Textual-based responsive terminal interface.
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
from textual.widgets import Footer, Header, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

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
# Slash commands registry
# ---------------------------------------------------------------------------

_COMMANDS: list[tuple[str, str]] = [
    ("/about",    "Versiyon bilgileri ve model bilgisi"),
    ("/auth",     "API anahtarları ve kimlik doğrulama ekranı"),
    ("/clear",    "Ekranı temizle"),
    ("/compact",  "Konuşma geçmişini özetle ve sıkıştır"),
    ("/config",   "Mevcut yapılandırmayı göster"),
    ("/editor",   "Çok satırlı giriş için harici editör aç"),
    ("/exit",     "Uygulamadan çık"),
    ("/export",   "Oturumu markdown dosyasına aktar"),
    ("/help",     "Tüm komutları ve kısayolları göster"),
    ("/load",     "Oturum yükle  →  /load <numara veya id>"),
    ("/model",    "Model seçim ekranı — Claude ve Gemini modelleri"),
    ("/new",      "Yeni oturum başlat"),
    ("/rename",   "Oturumu yeniden adlandır  →  /rename <yeni ad>"),
    ("/sessions", "Kayıtlı oturumları listele"),
    ("/status",   "Oturum istatistiklerini göster"),
    ("/theme",    "Temayı değiştir  →  /theme dark|light"),
    ("/think",    "Ayrıntılı çıktı modunu aç / kapat"),
]


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
        t = Text("\n  Yürütme:\n", style=C_GEMINI)
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

    #chat-log {
        height: 1fr;
        padding: 0 2;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }

    #chat-log > Static { width: 100%; }

    #autocomplete {
        display: none;
        max-height: 10;
        border-top: solid $primary;
        border-bottom: solid $primary;
        background: $panel;
        scrollbar-size-vertical: 0;
    }

    #input-container {
        height: 3;
        dock: bottom;
        border-top: solid $primary;
        padding: 0 1;
    }

    Input { border: none; background: $surface; }
    .input-prompt { color: $primary; text-style: bold; width: 4; }
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
        self._input_history: list[str] = []
        self._hist_pos: int = -1
        self._hist_draft: str = ""
        self._quit_confirm: bool = False
        self._sid   = str(uuid.uuid4())
        self._sname = datetime.now().strftime("%d %b %Y %H:%M")
        self._msgs: list[dict] = []
        if not self.session.chat:
            self.session.chat = Chat()
        self.ui_bridge = TuiAgentUI(self)

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="chat-log")
        yield OptionList(id="autocomplete")
        with Horizontal(id="input-container"):
            yield Label(" ❯ ", classes="input-prompt")
            yield Input(placeholder="Ne yapmamı istersin?", id="user-input")
        yield Footer()

    def on_mount(self) -> None:
        self.chat_log = self.query_one("#chat-log", VerticalScroll)
        from myagent.config.auth import get_claude_model, get_gemini_model
        self.log_message(Text(_BANNER, style="bold #c084fc"))
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
            "  ↑↓ geçmiş · Tab otomatik tamamla · Ctrl+Y kopyala · Ctrl+L temizle · F1 yardım\n",
            style="dim",
        ))
        self.query_one("#user-input").focus()

    def log_message(self, renderable: Any) -> None:
        self.chat_log.mount(Static(renderable))
        self.chat_log.scroll_end(animate=False)

    # ── Autocomplete ──────────────────────────────────────────────────────────

    @on(Input.Changed, "#user-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        ac = self.query_one("#autocomplete", OptionList)

        if not text.startswith("/"):
            ac.display = False
            return

        query = text.lower()
        if query == "/":
            matches = _COMMANDS
        else:
            matches = [(cmd, desc) for cmd, desc in _COMMANDS if cmd.startswith(query)]

        if not matches:
            ac.display = False
            return

        ac.clear_options()
        for cmd, desc in matches:
            ac.add_option(Option(f"{cmd}  [dim]{desc}[/dim]", id=cmd))
        ac.display = True
        ac.highlighted = 0

    @on(OptionList.OptionSelected, "#autocomplete")
    def on_autocomplete_selected(self, event: OptionList.OptionSelected) -> None:
        self._complete_autocomplete(event.option.id)

    def _complete_autocomplete(self, cmd: str) -> None:
        inp = self.query_one("#user-input", Input)
        ac  = self.query_one("#autocomplete", OptionList)
        inp.value = cmd + " "
        inp.cursor_position = len(inp.value)
        ac.display = False
        inp.focus()

    # ── Key handling ──────────────────────────────────────────────────────────

    def on_key(self, event: Key) -> None:
        try:
            inp = self.query_one("#user-input", Input)
            ac  = self.query_one("#autocomplete", OptionList)
        except Exception:
            return  # AuthScreen veya başka bir ekran aktif, müdahale etme

        # Autocomplete navigation (takes priority when visible)
        if ac.display and ac.option_count > 0:
            if event.key == "up":
                event.prevent_default(); event.stop()
                ac.highlighted = max(0, (ac.highlighted or 0) - 1)
                return
            elif event.key == "down":
                event.prevent_default(); event.stop()
                ac.highlighted = min(ac.option_count - 1, (ac.highlighted or 0) + 1)
                return
            elif event.key in ("tab", "enter"):
                if ac.highlighted is not None:
                    event.prevent_default(); event.stop()
                    opt = ac.get_option_at_index(ac.highlighted)
                    self._complete_autocomplete(opt.id)
                    return
            elif event.key == "escape":
                event.prevent_default(); event.stop()
                ac.display = False
                return

        # Input history (only when autocomplete hidden and input focused)
        if self.focused is not inp:
            return

        if event.key == "up":
            event.prevent_default(); event.stop()
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
            event.prevent_default(); event.stop()
            if self._hist_pos == -1:
                return
            if self._hist_pos < len(self._input_history) - 1:
                self._hist_pos += 1
                inp.value = self._input_history[self._hist_pos]
            else:
                self._hist_pos = -1
                inp.value = self._hist_draft
            inp.cursor_position = len(inp.value)

    # ── Input submit ──────────────────────────────────────────────────────────

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
        self.query_one("#autocomplete", OptionList).display = False

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

        elif cmd in ("about", "hakkında", "hakkinda"):
            self._cmd_about()

        elif cmd in ("status", "durum", "istatistik"):
            self._cmd_status()

        elif cmd in ("config", "yapılandırma", "yapilandirma"):
            self._cmd_config()

        elif cmd in ("auth", "kimlik", "api"):
            from myagent.auth_screen import AuthScreen
            self.app.push_screen(AuthScreen())

        elif cmd in ("model", "models"):
            from myagent.model_screen import ModelScreen
            self.app.push_screen(ModelScreen())

        elif cmd in ("think", "verbose", "ayrıntı", "ayrintimod"):
            self._cmd_think()

        elif cmd in ("theme", "tema"):
            self._cmd_theme(arg)

        elif cmd in ("export", "dışa", "disa"):
            self._cmd_export()

        elif cmd in ("compact", "sıkıştır", "sikistir", "özetle", "ozetle"):
            await self._cmd_compact()

        elif cmd in ("editor", "editör", "cok_satir"):
            await self._cmd_editor()

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

    # ── Command implementations ───────────────────────────────────────────────

    def _cmd_about(self) -> None:
        from myagent.config.auth import get_claude_model, get_gemini_model
        self.log_message(Text.assemble(
            ("\n  MyAgent  ", f"bold {C_CLAUDE}"),
            ("v1.0.0\n\n", "dim"),
            ("  Claude:  ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
            ("  Gemini:  ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
            (f"  Tarih:   {datetime.now().strftime('%Y-%m-%d')}\n", "dim"),
            (f"  Python:  {os.sys.version.split()[0]}\n\n", "dim"),
        ))

    def _cmd_status(self) -> None:
        n_user = sum(1 for m in self._msgs if m["role"] == "user")
        n_asst = sum(1 for m in self._msgs if m["role"] == "assistant")
        self.log_message(Text.assemble(
            ("\n  Oturum Durumu\n", f"bold {C_CLAUDE}"),
            ("  Ad:         ", "dim"), (self._sname, "white"), ("\n", ""),
            ("  ID:         ", "dim"), (self._sid[:8], "dim"), ("\n", ""),
            ("  Mesajlar:   ", "dim"), (f"{n_user} soru / {n_asst} cevap\n", "white"),
            ("  Verbose:    ", "dim"), ("açık\n" if self.verbose else "kapalı\n", "white"),
            ("  Tema:       ", "dim"), ("dark\n\n" if self.dark else "light\n\n", "white"),
        ))

    def _cmd_config(self) -> None:
        from myagent.config.auth import get_claude_model, get_gemini_model
        mask = lambda k: f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("eksik" if not k else "***")
        claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        self.log_message(Text.assemble(
            ("\n  Yapılandırma\n", f"bold {C_CLAUDE}"),
            ("  Claude model:    ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
            ("  Gemini model:    ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
            ("  Claude API key:  ", "dim"), (mask(claude_key), "white"), ("\n", ""),
            ("  Gemini API key:  ", "dim"), (mask(gemini_key), "white"), ("\n\n", ""),
        ))

    def _cmd_auth(self) -> None:
        mask = lambda k: f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("eksik" if not k else "***")
        claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        self.log_message(Text.assemble(
            ("\n  API Kimlik Doğrulama\n", f"bold {C_CLAUDE}"),
            ("  ANTHROPIC_API_KEY:  ", "dim"), (mask(claude_key), "white"), ("\n", ""),
            ("  GEMINI_API_KEY:     ", "dim"), (mask(gemini_key), "white"), ("\n", ""),
            ("\n  Değiştirmek için ~/.myagent/.env dosyasını düzenleyin.\n\n", "dim"),
        ))

    async def _cmd_model(self, arg: str) -> None:
        from myagent.config.auth import get_claude_model, get_gemini_model
        if not arg:
            self.log_message(Text.assemble(
                ("\n  Mevcut Modeller\n", f"bold {C_CLAUDE}"),
                ("  Claude:  ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
                ("  Gemini:  ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
                ("\n  Kullanım: /model claude <model-adı>\n", "dim"),
                ("           /model gemini <model-adı>\n\n", "dim"),
            ))
            return
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            self.log_message(Text("  Kullanım: /model claude|gemini <model-adı>\n", style=C_DIM))
            return
        target, model_name = parts[0].lower(), parts[1]
        if target == "claude":
            os.environ["CLAUDE_MODEL"] = model_name
            self.log_message(Text(f"  ✓ Claude modeli: {model_name}\n", style=C_OK))
        elif target == "gemini":
            os.environ["GEMINI_MODEL"] = model_name
            self.log_message(Text(f"  ✓ Gemini modeli: {model_name}\n", style=C_OK))
        else:
            self.log_message(Text("  Geçersiz hedef. 'claude' veya 'gemini' olmalı.\n", style=C_ERR))

    def _cmd_think(self) -> None:
        self.verbose = not self.verbose
        self.ui_bridge.verbose = self.verbose
        self.log_message(Text(
            f"  ✓ Verbose mod: {'açık' if self.verbose else 'kapalı'}\n", style=C_OK
        ))

    def _cmd_theme(self, arg: str) -> None:
        if arg == "light":
            self.dark = False
        elif arg == "dark":
            self.dark = True
        else:
            self.dark = not self.dark
        self.log_message(Text(
            f"  ✓ Tema: {'dark' if self.dark else 'light'}\n", style=C_OK
        ))

    def _cmd_export(self) -> None:
        if not self._msgs:
            self.log_message(Text("  Dışa aktarılacak mesaj yok.\n", style=C_DIM))
            return
        path = Path.home() / f"myagent_export_{self._sid[:8]}.md"
        lines = [f"# {self._sname}\n\n"]
        for msg in self._msgs:
            role = "**Sen**" if msg["role"] == "user" else "**Claude**"
            ts = msg.get("ts", "")[:16].replace("T", " ")
            lines.append(f"### {role}  `{ts}`\n\n{msg['text']}\n\n---\n\n")
        path.write_text("".join(lines), encoding="utf-8")
        self.log_message(Text(f"  ✓ Dışa aktarıldı: {path}\n", style=C_OK))

    async def _cmd_compact(self) -> None:
        if not self._msgs:
            self.log_message(Text("  Sıkıştırılacak mesaj yok.\n", style=C_DIM))
            return
        self.log_message(Text("  ⊛ Geçmiş özetleniyor…\n", style=f"dim {C_CLAUDE}"))
        history = "\n".join(
            f"{'Kullanıcı' if m['role']=='user' else 'Asistan'}: {m['text'][:500]}"
            for m in self._msgs
        )
        prompt = f"Aşağıdaki konuşmayı 3-5 cümleyle Türkçe özetle:\n\n{history}"
        loop = asyncio.get_event_loop()
        route = await loop.run_in_executor(None, self.session.chat.route, prompt)
        if route.answer:
            summary_text = f"[Önceki konuşma özeti]: {route.answer}"
            self._msgs = [{"role": "assistant", "text": summary_text, "ts": datetime.now().isoformat()}]
            self.session.chat = Chat()
            self.log_message(Text("  ✓ Geçmiş sıkıştırıldı.\n", style=C_OK))
            self._autosave()

    async def _cmd_editor(self) -> None:
        editor = os.environ.get("EDITOR", "nano")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("")
            tmp = f.name
        try:
            with self.suspend():
                subprocess.run([editor, tmp], check=False)
            text = Path(tmp).read_text(encoding="utf-8").strip()
        finally:
            Path(tmp).unlink(missing_ok=True)
        if text:
            inp = self.query_one("#user-input", Input)
            inp.value = text
            inp.cursor_position = len(text)

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

    def action_quit(self) -> None:
        if self._quit_confirm:
            self._autosave()
            self.exit()
        else:
            self._quit_confirm = True
            self.notify(
                "Çıkmak için tekrar Ctrl+C yapın.",
                severity="warning",
                timeout=3,
            )
            self.set_timer(3, self._reset_quit_confirm)

    def _reset_quit_confirm(self) -> None:
        self._quit_confirm = False

    def action_clear_log(self) -> None:
        self.chat_log.remove_children()

    def action_copy_last(self) -> None:
        if not self._last_answer:
            self.notify("Kopyalanacak cevap yok.", severity="warning"); return
        self.copy_to_clipboard(self._last_answer)
        self.notify("Panoya kopyalandı.")

    def action_help(self) -> None:
        rows = "\n".join(f"| `{cmd}` | {desc} |" for cmd, desc in _COMMANDS)
        self.log_message(Markdown(
            "### Komutlar\n"
            "| Komut | Açıklama |\n"
            "|---|---|\n"
            + rows + "\n\n"
            "**Kısayollar:**  "
            "`↑` `↓` geçmiş  ·  "
            "`Tab` otomatik tamamla  ·  "
            "`Ctrl+Y` kopyala  ·  "
            "`Ctrl+L` temizle  ·  "
            "`F1` yardım\n"
        ))


def start_tui(session: "SessionState", verbose: bool = False) -> None:
    app = MyAgentApp(session, verbose=verbose)
    app.run(mouse=False)

"""
prompt_toolkit + rich REPL — Textual TUI'nin yerine geçer.

Terminal inline modda çalışır (alternate screen yok):
  - Terminal scrollback çalışır
  - Mouse ile metin seçimi çalışır
  - prompt_toolkit: input history, slash autocomplete, renkli prompt
  - rich: renkli çıktı, markdown, streaming
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from myagent.agent.chat import Chat
from myagent.agent.doctor import run_diagnostics
from myagent.ui import C_CLAUDE, C_DIM, C_ERR, C_GEMINI, C_OK, C_WARN, make_ui

if TYPE_CHECKING:
    from myagent.cli import SessionState

# ---------------------------------------------------------------------------
# Shared console
# ---------------------------------------------------------------------------

_console = Console(highlight=False)

# ---------------------------------------------------------------------------
# Slash commands registry
# ---------------------------------------------------------------------------

_COMMANDS: list[tuple[str, str]] = [
    ("/about",    "Versiyon bilgileri ve model bilgisi"),
    ("/auth",     "API anahtarları ve yapılandırma"),
    ("/clear",    "Ekranı temizle"),
    ("/compact",  "Konuşma geçmişini özetle ve sıkıştır"),
    ("/config",   "Mevcut yapılandırmayı göster"),
    ("/doctor",   "Sistem sağlık kontrolü"),
    ("/editor",   "Harici editörle çok satırlı giriş"),
    ("/exit",     "Çıkış"),
    ("/export",   "Oturumu markdown dosyasına aktar"),
    ("/help",     "Tüm komutları göster"),
    ("/load",     "Oturum yükle  →  /load <numara veya id>"),
    ("/model",    "Model değiştir  →  /model claude|gemini <model>"),
    ("/new",      "Yeni oturum başlat"),
    ("/rename",   "Oturumu yeniden adlandır  →  /rename <ad>"),
    ("/sessions", "Kayıtlı oturumları listele"),
    ("/status",   "Oturum istatistiklerini göster"),
    ("/think",    "Verbose modunu aç / kapat"),
]

# ---------------------------------------------------------------------------
# Autocompleter
# ---------------------------------------------------------------------------

class _SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        word = text[1:]
        for cmd, desc in _COMMANDS:
            name = cmd[1:]
            if name.startswith(word):
                yield Completion(
                    name,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc,
                )

# ---------------------------------------------------------------------------
# Session persistence (mirrors tui.py logic)
# ---------------------------------------------------------------------------

_SESSIONS_DIR = Path.home() / ".myagent" / "sessions"


def _extract_topic(messages: list[dict]) -> str:
    """First user message, stripped to one line, max 120 chars."""
    for m in messages:
        if m.get("role") == "user":
            text = m.get("text", "").replace("\n", " ").strip()
            return text[:120]
    return ""


def _sessions_save(sid: str, name: str, messages: list[dict]) -> None:
    import json
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "id": sid,
        "name": name,
        "updated_at": datetime.now().isoformat(),
        "topic": _extract_topic(messages),
        "messages": messages,
    }
    (_SESSIONS_DIR / f"{sid}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _sessions_list() -> list[dict]:
    import json
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
# Banner
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


# ---------------------------------------------------------------------------
# REPL state
# ---------------------------------------------------------------------------

class ReplState:
    def __init__(self, session: "SessionState", verbose: bool = False):
        self.session = session
        self.verbose = verbose
        self.sid = str(uuid.uuid4())
        self.sname = datetime.now().strftime("%d %b %Y %H:%M")
        self.msgs: list[dict] = []
        self.last_answer: str = ""
        if not self.session.chat:
            self.session.chat = Chat()

    def autosave(self) -> None:
        if self.msgs:
            _sessions_save(self.sid, self.sname, self.msgs)

    def new_session(self) -> None:
        from myagent.agent.tokens import tracker
        self.autosave()
        self.sid = str(uuid.uuid4())
        self.sname = datetime.now().strftime("%d %b %Y %H:%M")
        self.msgs = []
        self.last_answer = ""
        self.session.chat = Chat()
        tracker.reset()
        _console.clear()
        _print_banner(self)


# ---------------------------------------------------------------------------
# Banner printer
# ---------------------------------------------------------------------------

def _print_banner(state: ReplState | None = None) -> None:
    from myagent.config.auth import get_claude_model, get_gemini_model
    # Disable line wrap: banner lines stay 1 row each on resize → cursor tracking intact
    sys.stdout.write("\033[?7l")
    sys.stdout.flush()
    _console.print(Text(_BANNER, style="bold #c084fc"))
    _console.print(Text.assemble(
        ("  v1.0.0  ·  ", "dim"),
        ("◆ ", "bold #D97706"), ("Claude", "bold #D97706"), (" planlar  ·  ", "dim"),
        ("✦ ", "bold #4285F4"), ("Gemini", "bold #E8EAED"), (" yürütür\n", "dim"),
    ))
    _console.print(Text.assemble(
        ("  ◆ ", "#D97706"), (get_claude_model(), "#D97706"),
        ("  ✦ ", "#4285F4"), (get_gemini_model(), "#E8EAED"), ("\n", ""),
    ))
    _console.print(Text(
        "     ↑↓ geçmiş · Tab tamamla · Ctrl+O editör · Ctrl+Y kopyala · ? kısayollar\n",
        style="dim",
    ))
    sys.stdout.write("\033[?7h")
    sys.stdout.flush()
    _console.rule(style="dim")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_help() -> None:
    t = Text("\n  Slash Komutları\n\n", style=f"bold {C_CLAUDE}")
    for cmd, desc in _COMMANDS:
        t.append(f"  {cmd:<16}", style="bold white")
        t.append(f"  {desc}\n", style="dim")
    t.append("\n  Kısayollar için  ?  yazın.\n\n", style="dim")
    _console.print(t)


def _cmd_about() -> None:
    from myagent.config.auth import get_claude_model, get_gemini_model
    _console.print(Text.assemble(
        ("\n  MyAgent  ", f"bold {C_CLAUDE}"),
        ("v1.0.0\n\n", "dim"),
        ("  Claude:  ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
        ("  Gemini:  ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
        (f"  Tarih:   {datetime.now().strftime('%Y-%m-%d')}\n", "dim"),
        (f"  Python:  {sys.version.split()[0]}\n\n", "dim"),
    ))


def _cmd_status(state: ReplState) -> None:
    from myagent.agent.tokens import tracker

    n_user = sum(1 for m in state.msgs if m["role"] == "user")
    n_asst = sum(1 for m in state.msgs if m["role"] == "assistant")

    _console.print(Text.assemble(
        ("\n  Oturum Durumu\n", f"bold {C_CLAUDE}"),
        ("  Ad:         ", "dim"), (state.sname, "white"), ("\n", ""),
        ("  ID:         ", "dim"), (state.sid[:8], "dim"), ("\n", ""),
        ("  Mesajlar:   ", "dim"), (f"{n_user} soru / {n_asst} cevap\n", "white"),
        ("  Verbose:    ", "dim"), ("açık\n" if state.verbose else "kapalı\n", "white"),
    ))

    if not tracker.has_data():
        _console.print(Text("  (henüz token verisi yok)\n\n", style="dim"))
        return

    est_c = "~" if tracker.claude.has_estimates else ""
    est_g = "~" if tracker.gemini.has_estimates else ""
    c_cost = tracker.claude_cost()
    g_cost = tracker.gemini_cost()
    sav = tracker.savings()
    sav_pct = tracker.savings_pct()
    hyp = tracker.hypothetical_cost()
    fp_rate = tracker.first_pass_rate()
    n_tasks = tracker.tasks_total

    def fmt_tok(n: int) -> str:
        return f"{n:,}" if n < 1_000_000 else f"{n/1_000_000:.2f}M"

    def fmt_cost(v: float) -> str:
        if v < 0.0001:
            return f"${v * 100_000:.2f} (0.00001¢)"
        if v < 0.01:
            return f"${v:.5f}"
        return f"${v:.4f}"

    _console.print(Text.assemble(
        ("\n  Token Kullanımı\n", f"bold {C_CLAUDE}"),
        ("  ◆ Claude:  ", f"bold {C_CLAUDE}"),
        (f"{est_c}{fmt_tok(tracker.claude.input_tokens)} giriş  +  "
         f"{est_c}{fmt_tok(tracker.claude.output_tokens)} çıkış", "white"),
        (f"  =  {est_c}{fmt_cost(c_cost)}\n", "dim"),
        ("  ✦ Gemini:  ", f"bold {C_GEMINI}"),
        (f"{est_g}{fmt_tok(tracker.gemini.input_tokens)} giriş  +  "
         f"{est_g}{fmt_tok(tracker.gemini.output_tokens)} çıkış", "white"),
        (f"  =  {est_g}{fmt_cost(g_cost)}\n", "dim"),
    ))

    _console.print(Text.assemble(
        ("\n  Maliyet Tasarrufu\n", f"bold {C_CLAUDE}"),
        ("  Tümü Claude olsaydı:   ", "dim"), (f"{est_c}{fmt_cost(hyp)}\n", "white"),
        ("  Gerçek maliyet:        ", "dim"), (f"{fmt_cost(c_cost + g_cost)}\n", "white"),
        ("  Tasarruf:              ", "dim"),
        (f"{fmt_cost(sav)}  (%{sav_pct:.1f})\n", "bold green" if sav > 0 else "white"),
    ))

    if n_tasks > 0:
        _console.print(Text.assemble(
            ("\n  Verimlilik\n", f"bold {C_CLAUDE}"),
            ("  Toplam görev:   ", "dim"), (f"{n_tasks}\n", "white"),
            ("  İlk seferde:    ", "dim"),
            (f"{tracker.tasks_first_pass}  (%{fp_rate:.0f})\n\n", "white"),
        ))
    else:
        _console.print()


def _cmd_config() -> None:
    from myagent.config.auth import get_claude_model, get_gemini_model
    from myagent.config.settings import WORK_DIR
    mask = lambda k: f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("eksik" if not k else "***")
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
    _console.print(Text.assemble(
        ("\n  Yapılandırma\n", f"bold {C_CLAUDE}"),
        ("  Claude model:    ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
        ("  Gemini model:    ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
        ("  Claude API key:  ", "dim"), (mask(claude_key), "white"), ("\n", ""),
        ("  Gemini API key:  ", "dim"), (mask(gemini_key), "white"), ("\n", ""),
        ("  Çalışma dizini:  ", "dim"), (str(WORK_DIR), "white"), ("\n\n", ""),
    ))


def _cmd_auth() -> None:
    mask = lambda k: f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("eksik" if not k else "***")
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
    _console.print(Text.assemble(
        ("\n  API Kimlik Doğrulama\n", f"bold {C_CLAUDE}"),
        ("  ANTHROPIC_API_KEY:  ", "dim"), (mask(claude_key), "white"), ("\n", ""),
        ("  GEMINI_API_KEY:     ", "dim"), (mask(gemini_key), "white"), ("\n", ""),
        ("\n  Değiştirmek için ~/.myagent/.env dosyasını düzenleyin.\n\n", "dim"),
    ))


def _cmd_doctor() -> None:
    _console.print(Text.assemble(
        ("\n  Sistem Sağlık Kontrolü  ", f"bold {C_CLAUDE}"),
        ("çalışıyor…\n", "dim"),
    ))
    results = run_diagnostics()
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", width=12)
    table.add_column(width=3)
    table.add_column()
    for cat, status, msg in results:
        color = C_OK if status == "✓" else (C_ERR if status == "✗" else C_WARN)
        table.add_row(cat, Text(status, style=f"bold {color}"), Text(msg, style="white"))
    _console.print(table)
    _console.print(Text("\n  ✓ Kontrol tamamlandı.\n", style=C_DIM))


def _cmd_model(arg: str) -> None:
    from myagent.config.auth import get_claude_model, get_gemini_model
    if not arg:
        _console.print(Text.assemble(
            ("\n  Mevcut Modeller\n", f"bold {C_CLAUDE}"),
            ("  Claude:  ", "dim"), (get_claude_model(), C_CLAUDE), ("\n", ""),
            ("  Gemini:  ", "dim"), (get_gemini_model(), C_GEMINI), ("\n", ""),
            ("\n  Kullanım: /model claude <model>  veya  /model gemini <model>\n\n", "dim"),
        ))
        return
    parts = arg.split(maxsplit=1)
    if len(parts) < 2:
        _console.print(Text("  Kullanım: /model claude|gemini <model-adı>\n", style=C_DIM))
        return
    target, model_name = parts[0].lower(), parts[1]
    if target == "claude":
        os.environ["CLAUDE_MODEL"] = model_name
        _console.print(Text(f"  ✓ Claude modeli: {model_name}\n", style=C_OK))
    elif target == "gemini":
        os.environ["GEMINI_MODEL"] = model_name
        _console.print(Text(f"  ✓ Gemini modeli: {model_name}\n", style=C_OK))
    else:
        _console.print(Text("  Geçersiz hedef. 'claude' veya 'gemini' olmalı.\n", style=C_ERR))


def _cmd_think(state: ReplState) -> None:
    state.verbose = not state.verbose
    _console.print(Text(
        f"  ✓ Verbose mod: {'açık' if state.verbose else 'kapalı'}\n", style=C_OK
    ))


def _cmd_export(state: ReplState) -> None:
    if not state.msgs:
        _console.print(Text("  Dışa aktarılacak mesaj yok.\n", style=C_DIM))
        return
    path = Path.home() / f"myagent_export_{state.sid[:8]}.md"
    lines = [f"# {state.sname}\n\n"]
    for msg in state.msgs:
        role = "**Sen**" if msg["role"] == "user" else "**Claude**"
        ts = msg.get("ts", "")[:16].replace("T", " ")
        lines.append(f"### {role}  `{ts}`\n\n{msg['text']}\n\n---\n\n")
    path.write_text("".join(lines), encoding="utf-8")
    _console.print(Text(f"  ✓ Dışa aktarıldı: {path}\n", style=C_OK))


def _cmd_compact(state: ReplState) -> None:
    if not state.msgs:
        _console.print(Text("  Sıkıştırılacak mesaj yok.\n", style=C_DIM))
        return
    _console.print(Text("  ⊛ Geçmiş özetleniyor…\n", style=f"dim {C_CLAUDE}"))
    history = "\n".join(
        f"{'Kullanıcı' if m['role']=='user' else 'Asistan'}: {m['text'][:500]}"
        for m in state.msgs
    )
    prompt = f"Aşağıdaki konuşmayı 3-5 cümleyle Türkçe özetle:\n\n{history}"
    route = state.session.chat.route(prompt)
    if route.answer:
        summary_text = f"[Önceki konuşma özeti]: {route.answer}"
        state.msgs = [{"role": "assistant", "text": summary_text, "ts": datetime.now().isoformat()}]
        state.session.chat = Chat()
        _console.print(Text("  ✓ Geçmiş sıkıştırıldı.\n", style=C_OK))
        state.autosave()


def _cmd_editor(state: ReplState) -> None:
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("")
        tmp = f.name
    try:
        subprocess.run([editor, tmp], check=False)
        text = Path(tmp).read_text(encoding="utf-8").strip()
    finally:
        Path(tmp).unlink(missing_ok=True)
    if text:
        return text
    return None


def _cmd_sessions() -> None:
    sessions = _sessions_list()
    if not sessions:
        _console.print(Text("  Kayıtlı oturum yok.\n", style=C_DIM))
        return
    t = Text(f"\n  Oturumlar ({len(sessions)}):\n\n", style=f"bold {C_CLAUDE}")
    for i, s in enumerate(sessions[:20], 1):
        sid   = s.get("id", "")[:8]
        ts    = s.get("updated_at", "")[:16].replace("T", " ")
        n_msg = len(s.get("messages", []))
        topic = s.get("topic") or _extract_topic(s.get("messages", []))

        t.append(f"  [{i:2}]  ", style=C_DIM)
        t.append(f"{ts}  ", style="white")
        t.append(f"{n_msg:3} mesaj  ", style=C_DIM)
        t.append(f"id:{sid}\n", style="dim")
        if topic:
            preview = topic[:88] + ("…" if len(topic) > 88 else "")
            t.append(f"        {preview}\n", style="italic")
        t.append("\n", style="")
    t.append("  /load <numara veya id>  ile yükle\n\n", style=C_DIM)
    _console.print(t)


def _cmd_load(state: ReplState, arg: str) -> None:
    if not arg:
        _console.print(Text("  Kullanım: /load <numara veya id>\n", style=C_DIM))
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
        _console.print(Text(f"  Oturum bulunamadı: {arg}\n", style=C_ERR))
        return

    state.autosave()
    state.sid   = data["id"]
    state.sname = data.get("name", "yüklendi")
    state.msgs  = data.get("messages", [])
    state.last_answer = ""

    _console.clear()
    _print_banner(state)
    for msg in state.msgs:
        if msg["role"] == "user":
            _console.print(Text.assemble(
                ("\n  ", ""), ("Sen  ", f"bold {C_GEMINI}"),
                (msg["text"], "bold white"), ("\n", ""),
            ))
        else:
            ts = msg.get("ts", "")[:16].replace("T", " ")
            _console.print(Text(f"  Claude  {ts}\n", style=f"bold {C_CLAUDE}"))
            _console.print(Markdown(msg["text"]))
            _console.print()
    _console.print(Text(f"\n  ✓ Yüklendi: {state.sname}\n", style=C_OK))


def _cmd_rename(state: ReplState, arg: str) -> None:
    if not arg:
        _console.print(Text("  Kullanım: /rename <yeni ad>\n", style=C_DIM))
        return
    state.sname = arg
    state.autosave()
    _console.print(Text(f"  ✓ Oturum adı: {arg}\n", style=C_OK))


# ---------------------------------------------------------------------------
# Chat / pipeline handlers
# ---------------------------------------------------------------------------

def _handle_chat(state: ReplState, text: str) -> None:
    _console.print(Text.assemble(
        ("\n  ", ""), ("Sen  ", f"bold {C_GEMINI}"),
        (text, "bold white"), ("\n", ""),
    ))
    _console.print(Text("  ⊛ düşünüyor…\n", style=f"dim {C_CLAUDE}"), end="")
    t0 = time.time()
    route = state.session.chat.route(text)
    elapsed = time.time() - t0

    if route.action == "answer":
        answer = route.answer
        state.last_answer = answer
        _console.print(Text.assemble(
            ("  Claude  ", f"bold {C_CLAUDE}"),
            (f"{elapsed:.1f}s\n", "dim"),
        ))
        _console.print(Markdown(answer))
        _console.print()
        now = datetime.now().isoformat()
        state.msgs.append({"role": "user",      "text": text,   "ts": now})
        state.msgs.append({"role": "assistant",  "text": answer, "ts": now})
        state.autosave()
    else:
        _handle_pipeline(state, route.task or text)


def _handle_pipeline(state: ReplState, task: str) -> None:
    from myagent.agent.pipeline import run
    from myagent.cli import _handle_run

    _console.print(Text.assemble(
        ("\n  ", ""), ("Sen  ", f"bold {C_GEMINI}"),
        (task, "bold white"), ("\n", ""),
    ))

    ui = make_ui(verbose=state.verbose)
    t0 = time.time()
    try:
        result = run(
            task,
            verbose=state.verbose,
            dry_run=False, batch=True, clarify=False,
            review=True, max_review_rounds=4,
            auto_deps=False, verify_completion=True, max_completion_rounds=2,
            session_context="", ui=ui,
        )
        elapsed = time.time() - t0
        state.session.update(result)
        if state.session.chat:
            state.session.chat.add_task_result(result.task_original, result.summary_en)
        files = ", ".join(result.created_files[:4]) or "—"
        _console.print(Text.assemble(
            ("\n  ✓ ", f"bold {C_OK}"),
            (f"{elapsed:.1f}s  dosyalar: ", "dim"),
            (files + "\n", "white"),
        ))
        state.autosave()
    except Exception as exc:
        _console.print(Text(f"\n  ✗ Hata: {exc}\n", style=f"bold {C_ERR}"))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _dispatch(state: ReplState, raw: str) -> bool:
    """Returns False to exit, True to continue."""
    raw = raw.strip()
    if not raw:
        return True

    if raw.startswith("/"):
        raw = raw[1:]

    parts = raw.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("exit", "quit", "çıkış", "cikis"):
        state.autosave()
        return False

    elif cmd in ("help", "yardım", "yardim", "h"):
        _cmd_help()

    elif cmd in ("clear", "cls", "temizle"):
        _console.clear()

    elif cmd in ("about", "hakkında", "hakkinda"):
        _cmd_about()

    elif cmd in ("status", "durum", "istatistik"):
        _cmd_status(state)

    elif cmd in ("config", "yapılandırma", "yapilandirma"):
        _cmd_config()

    elif cmd in ("auth", "kimlik", "api"):
        _cmd_auth()

    elif cmd in ("doctor", "check", "kontrol", "doktor"):
        _cmd_doctor()

    elif cmd in ("model", "models"):
        _cmd_model(arg)

    elif cmd in ("think", "verbose", "ayrıntı", "ayrintimod"):
        _cmd_think(state)

    elif cmd in ("export", "dışa", "disa"):
        _cmd_export(state)

    elif cmd in ("compact", "sıkıştır", "sikistir", "özetle", "ozetle"):
        _cmd_compact(state)

    elif cmd in ("editor", "editör", "cok_satir"):
        text = _cmd_editor(state)
        if text:
            _handle_chat(state, text)

    elif cmd in ("sessions", "oturumlar", "gecmis", "geçmiş"):
        _cmd_sessions()

    elif cmd in ("rename", "isimlendir", "adlandir"):
        _cmd_rename(state, arg)

    elif cmd in ("load", "yukle", "yükle", "aç", "ac"):
        _cmd_load(state, arg)

    elif cmd in ("new", "yeni"):
        state.new_session()

    else:
        # Not a recognized slash command — treat whole thing as a task/chat
        _handle_chat(state, raw if raw.startswith("/") else f"/{cmd}" + (f" {arg}" if arg else ""))

    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _copy_to_clipboard(text: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
            return True
        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            try:
                subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
                return True
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
    except Exception:
        pass
    return False


def _show_shortcuts() -> None:
    rows = [
        ("Ctrl+C",      "İptal / Çıkış onayı"),
        ("Ctrl+D",      "Çıkış"),
        ("Ctrl+L",      "Ekranı temizle"),
        ("Ctrl+R",      "Geçmişte ara (reverse search)"),
        ("Ctrl+O",      "Editörde çok satırlı giriş ($EDITOR)"),
        ("Ctrl+Y",      "Son cevabı panoya kopyala"),
        ("Ctrl+N",      "Yeni oturum başlat"),
        ("Ctrl+A",      "Satır başına git"),
        ("Ctrl+E",      "Satır sonuna git"),
        ("Ctrl+K",      "Satır sonunu sil"),
        ("Ctrl+U",      "Satır başını sil"),
        ("Ctrl+W",      "Önceki kelimeyi sil"),
        ("↑ / ↓",       "Geçmiş - sonraki / önceki"),
        ("Tab",         "Slash komut otomatik tamamlama"),
        ("?",           "Bu yardımı göster"),
        ("! <komut>",   "Shell komutu çalıştır  (! ls, ! git status ...)"),
    ]
    t = Text("\n  Kısayollar\n\n", style="bold #c084fc")
    for key, desc in rows:
        t.append(f"  {key:<22}", style="bold white")
        t.append(f"  {desc}\n", style="dim")
    t.append("\n  Slash komutları için  /help  yazın.\n\n", style="dim")
    _console.print(t)


def _run_shell(cmd: str) -> None:
    _console.print(Text(f"\n  $ {cmd}\n", style="dim"))
    try:
        result = subprocess.run(
            cmd, shell=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=30,
        )
        if result.stdout:
            _console.print(result.stdout.rstrip())
    except subprocess.TimeoutExpired:
        _console.print(Text("  (zaman aşımı)\n", style=C_WARN))
    except Exception as exc:
        _console.print(Text(f"  Hata: {exc}\n", style=C_ERR))
    _console.print()


def _build_key_bindings(state: "ReplState") -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-l")
    def _(event):
        event.app.renderer.clear()
        _console.clear()
        _print_banner(state)

    @kb.add("c-y")
    def _(event):
        if state.last_answer:
            ok = _copy_to_clipboard(state.last_answer)
            msg = "  ✓ Panoya kopyalandı\n" if ok else "  ✗ Pano aracı bulunamadı (xclip/wl-copy)\n"
            _console.print(Text(msg, style=C_OK if ok else C_WARN))
        else:
            _console.print(Text("  (henüz cevap yok)\n", style=C_DIM))

    @kb.add("c-n")
    def _(event):
        state.new_session()

    @kb.add("c-o")
    def _(event):
        buf = event.app.current_buffer
        current = buf.text
        editor = os.environ.get("EDITOR", "nano")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(current)
            tmp = f.name
        try:
            with event.app.input.detach():
                subprocess.run([editor, tmp], check=False)
            text = Path(tmp).read_text(encoding="utf-8").strip()
            buf.set_document(Document(text, len(text)))
        except Exception as exc:
            _console.print(Text(f"  Editör hatası: {exc}\n", style=C_ERR))
        finally:
            Path(tmp).unlink(missing_ok=True)

    @kb.add("enter")
    def _(event):
        buf = event.app.current_buffer
        if buf.text.strip():
            buf.validate_and_handle()
        # empty → do nothing; cursor stays on same line

    @kb.add("/")
    def _(event):
        event.app.current_buffer.insert_text("/")
        event.app.current_buffer.start_completion(select_first=False)

    return kb


def start_repl(session: "SessionState", verbose: bool = False) -> None:
    state = ReplState(session, verbose=verbose)

    history_path = Path.home() / ".myagent" / "repl_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    kb = _build_key_bindings(state)

    def _bottom_toolbar():
        from prompt_toolkit.application import get_app
        from myagent.config.auth import get_claude_model
        try:
            width = get_app().output.get_size().columns
        except Exception:
            try:
                width = os.get_terminal_size().columns
            except OSError:
                width = 80
        model = get_claude_model()
        info = f" ◆ {model}  ? kısayollar  /help komutlar "
        dashes = max(0, width - len(info))
        left = dashes // 2
        right = dashes - left
        rule = "─" * left + info + "─" * right
        return HTML(f"<ansibrightblack>{rule}</ansibrightblack>")

    prompt_session: PromptSession = PromptSession(
        history=FileHistory(str(history_path)),
        completer=_SlashCompleter(),
        complete_while_typing=True,
        key_bindings=kb,
        enable_history_search=True,
        multiline=False,
        bottom_toolbar=_bottom_toolbar,
    )

    _print_banner(state)

    quit_confirm = False

    while True:
        try:
            raw = prompt_session.prompt(
                HTML("<ansipurple><b>❯</b></ansipurple> ")
            ).strip()
            quit_confirm = False
        except KeyboardInterrupt:
            if quit_confirm:
                state.autosave()
                _console.print(Text("\nGoodbye.\n", style="dim"))
                break
            quit_confirm = True
            _console.print(Text("  Çıkmak için tekrar Ctrl+C yapın.\n", style="dim yellow"))
            continue
        except EOFError:
            state.autosave()
            _console.print(Text("\nGoodbye.\n", style="dim"))
            break

        if not raw:
            continue

        # ? alone → shortcuts
        if raw == "?":
            _show_shortcuts()
            continue

        # ! prefix → shell command
        if raw.startswith("!"):
            _run_shell(raw[1:].strip())
            continue

        if not _dispatch(state, raw):
            _console.print(Text("\nGoodbye.\n", style="dim"))
            break

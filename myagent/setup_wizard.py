"""
First-run setup wizard — clean step-by-step Rich UI.
"""

from __future__ import annotations

import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from myagent.config.auth import (
    API, CLI, CLAUDE_WORKER, AuthMode,
    detect_claude, detect_gemini,
    save_config,
)
from myagent.models import (
    CLAUDE_CURATED, CLAUDE_DEFAULT,
    GEMINI_CURATED, GEMINI_DEFAULT,
    ModelInfo,
    fetch_claude_models, fetch_gemini_models,
)

_console = Console()

# ---------------------------------------------------------------------------
# Human-friendly labels
# ---------------------------------------------------------------------------

_PLANNER_OPTS = [
    # (mode, short_name, detail, env_hint)
    (API, "API Anahtarı",   "~3s/plan",  "ANTHROPIC_API_KEY"),
    (CLI, "Claude Code",    "~5s/plan",  "OAuth — ayrıca kurulum gerekmez"),
]

_WORKER_OPTS = [
    (API,           "Gemini API",   "~2s/adım",  "Hızlı — GEMINI_API_KEY gerekli"),
    (CLAUDE_WORKER, "Claude Code",  "~5s/adım",  "Giriş yapılmış hesabı kullanır"),
    (CLI,           "Gemini CLI",   "~40s/adım", "Yavaş — Node.js her adımda başlar"),
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    _console.print()
    _console.print(Panel(
        Text.assemble(
            ("myagent", "bold medium_purple1"),
            ("  Kurulum Sihirbazı", "bold white"),
        ),
        border_style="medium_purple1",
        padding=(0, 2),
        expand=False,
        subtitle="[dim]3 adımda yapılandırma[/]",
    ))
    _console.print()

    with _console.status("[dim]Sistem taranıyor…[/]", spinner="dots"):
        claude_modes = detect_claude()
        gemini_modes = detect_gemini()

    if not claude_modes:
        _fatal(
            "Claude bağlantısı kurulamadı.\n\n"
            "  Şunlardan birini yapın:\n"
            "  [dim]• export ANTHROPIC_API_KEY=sk-ant-…[/]\n"
            "  [dim]• claude login[/]"
        )
    if not gemini_modes:
        _fatal(
            "Worker backend bulunamadı.\n\n"
            "  Şunlardan birini yapın:\n"
            "  [dim]• export GEMINI_API_KEY=AIza…[/]\n"
            "  [dim]• claude login[/]"
        )

    # ── Adım 1: Planner (Claude) auth ──────────────────────────────────────
    _step_header(1, 3, "Planner", "Claude nasıl bağlanacak?")
    claude_mode = _pick_planner(claude_modes)

    # ── Adım 2: Worker backend ──────────────────────────────────────────────
    _step_header(2, 3, "Worker", "Görevleri kim yürütecek?")
    gemini_mode = _pick_worker(gemini_modes)

    # ── Adım 3: Model ────────────────────────────────────────────────────────
    _step_header(3, 3, "Model", "Hangi Claude modeli kullanılsın?")
    claude_model = _pick_claude_model(claude_mode)

    # Worker model — derived, no extra step
    _console.print()
    if gemini_mode == API:
        gemini_model = _pick_gemini_model_inline()
    elif gemini_mode == CLAUDE_WORKER:
        gemini_model = claude_model
        _console.print(
            f"  [dim]Worker modeli → Planner ile aynı:[/]  "
            f"[medium_purple1]{claude_model}[/]"
        )
    else:
        gemini_model = GEMINI_DEFAULT
        _console.print(
            f"  [dim]Gemini CLI varsayılan modeli:[/]  "
            f"[dodger_blue1]{gemini_model}[/]"
        )

    save_config({
        "claude_mode":  claude_mode,
        "claude_model": claude_model,
        "gemini_mode":  gemini_mode,
        "gemini_model": gemini_model,
    })

    _summary(claude_mode, claude_model, gemini_mode, gemini_model)


# ---------------------------------------------------------------------------
# Step header
# ---------------------------------------------------------------------------

def _step_header(step: int, total: int, title: str, subtitle: str) -> None:
    _console.print()
    _console.print(Rule(
        f"[bold white] Adım {step}/{total} [/]  [dim]{title}[/]",
        style="dim",
    ))
    if subtitle:
        _console.print(f"  [dim]{subtitle}[/]")
    _console.print()


# ---------------------------------------------------------------------------
# Step 1 — Planner picker
# ---------------------------------------------------------------------------

def _pick_planner(available: list[AuthMode]) -> AuthMode:
    opts = [(m, name, detail, hint)
            for m, name, detail, hint in _PLANNER_OPTS
            if m in available]
    unavail = [(m, name, detail, hint)
               for m, name, detail, hint in _PLANNER_OPTS
               if m not in available]

    if len(opts) == 1:
        m, name, detail, hint = opts[0]
        _console.print(f"  [green3]✓[/] [bold white]{name}[/]  [dim]{detail}[/]")
        if unavail:
            um, uname, _, uhint = unavail[0]
            _console.print(f"  [dim]✗ {uname}  ({uhint} tanımlı değil)[/]")
        _console.print(f"\n  [dim]→ Otomatik seçildi[/]")
        return m

    return _menu(
        opts,
        color="medium_purple1",
        recommended=opts[0][0],
    )


# ---------------------------------------------------------------------------
# Step 2 — Worker picker
# ---------------------------------------------------------------------------

def _pick_worker(available: list[AuthMode]) -> AuthMode:
    avail = [(m, name, detail, hint)
             for m, name, detail, hint in _WORKER_OPTS
             if m in available]
    unavail = [(m, name, detail, hint)
               for m, name, detail, hint in _WORKER_OPTS
               if m not in available]

    if len(avail) == 1:
        m, name, detail, hint = avail[0]
        _console.print(f"  [green3]✓[/] [bold white]{name}[/]  [dim]{detail}[/]")
        _console.print(f"\n  [dim]→ Otomatik seçildi[/]")
        return m

    # Show available options + unavailable ones dimmed at the bottom
    all_rows = []
    for m, name, detail, hint in avail:
        all_rows.append((m, name, detail, hint, True))
    for m, name, detail, hint in unavail:
        all_rows.append((m, name, detail, hint, False))

    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", justify="right", width=4)
    t.add_column(min_width=16)
    t.add_column(style="dim", min_width=10)
    t.add_column(style="dim")

    selectable = [row for row in all_rows if row[4]]
    rec_mode = selectable[0][0]
    idx = 1
    num_map: dict[int, AuthMode] = {}

    for m, name, detail, hint, is_avail in all_rows:
        if is_avail:
            star = "  [green3]★[/]" if m == rec_mode else ""
            t.add_row(f"{idx})", f"[bold white]{name}[/]{star}", detail, hint)
            num_map[idx] = m
            idx += 1
        else:
            t.add_row("", f"[dim]✗ {name}[/]", f"[dim]{detail}[/]", f"[dim]{hint}[/]")

    _console.print(Panel(t, border_style="dim", padding=(0, 1), expand=False))

    while True:
        prompt = f"  [dim]Seçim [1-{len(selectable)}, Enter={1}]:[/] [dodger_blue1]"
        raw = _console.input(prompt).strip()
        _console.print("[/]", end="")
        if not raw:
            _console.print(f"  [dodger_blue1]✓[/] [bold white]{selectable[0][1]}[/]")
            return selectable[0][0]
        if raw.isdigit() and 1 <= int(raw) <= len(selectable):
            chosen = num_map[int(raw)]
            chosen_name = next(n for m, n, *_ in avail if m == chosen)
            _console.print(f"  [dodger_blue1]✓[/] [bold white]{chosen_name}[/]")
            return chosen
        _console.print(f"  [red1]Geçersiz.[/] [dim]1-{len(selectable)} arası veya Enter[/]")


# ---------------------------------------------------------------------------
# Step 3 — Claude model picker
# ---------------------------------------------------------------------------

def _pick_claude_model(mode: AuthMode) -> str:
    models = _load_claude_models(mode)
    default = CLAUDE_DEFAULT

    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", justify="right", width=4)
    t.add_column(min_width=30)
    t.add_column(style="dim")

    for i, m in enumerate(models, 1):
        star = "  [green3]★[/]" if m.is_recommended else ""
        aliases = f"  ({', '.join(m.aliases)})" if m.aliases else ""
        t.add_row(f"{i})", f"[bold white]{m.id}[/]{star}", f"{m.description}{aliases}")

    extra_start = len(models) + 1
    t.add_row(f"{extra_start})", "[dim]Manuel giriş[/]", "")
    t.add_row(f"{extra_start + 1})", "[dim]Varsayılanı kullan[/]", f"[dim]{default}[/]")

    _console.print(Panel(t, border_style="dim", padding=(0, 1), expand=False))

    # Find recommended index
    rec_idx = next(
        (i for i, m in enumerate(models, 1) if m.is_recommended),
        extra_start + 1,
    )

    while True:
        prompt = f"  [dim]Seçim [1-{extra_start + 1}, Enter={rec_idx}]:[/] [medium_purple1]"
        raw = _console.input(prompt).strip()
        _console.print("[/]", end="")

        if not raw:
            raw = str(rec_idx)

        if not raw.isdigit() or not (1 <= int(raw) <= extra_start + 1):
            _console.print(f"  [red1]Geçersiz.[/] [dim]1-{extra_start + 1} arası veya Enter[/]")
            continue

        choice = int(raw)
        if choice == extra_start + 1:
            _console.print(f"  [medium_purple1]✓[/] Varsayılan: [bold]{default}[/]")
            return default
        if choice == extra_start:
            val = _console.input("  [dim]Model ID:[/] [medium_purple1]").strip()
            _console.print("[/]", end="")
            result = val or default
            _console.print(f"  [medium_purple1]✓[/] [bold]{result}[/]")
            return result
        selected = models[choice - 1]
        _console.print(f"  [medium_purple1]✓[/] [bold]{selected.id}[/]")
        return selected.id


# ---------------------------------------------------------------------------
# Gemini model inline (only shown when worker=API)
# ---------------------------------------------------------------------------

def _pick_gemini_model_inline() -> str:
    import os
    api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if api_key:
        with _console.status("[dim]Gemini modelleri getiriliyor…[/]", spinner="dots"):
            models = fetch_gemini_models(api_key)
    else:
        models = GEMINI_CURATED

    default = GEMINI_DEFAULT
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", justify="right", width=4)
    t.add_column(min_width=30)
    t.add_column(style="dim")

    for i, m in enumerate(models, 1):
        star = "  [green3]★[/]" if m.is_recommended else ""
        t.add_row(f"{i})", f"[bold white]{m.id}[/]{star}", m.description)

    extra_start = len(models) + 1
    t.add_row(f"{extra_start})", "[dim]Varsayılanı kullan[/]", f"[dim]{default}[/]")

    _console.print()
    _console.print(Rule("[dim] Gemini modeli [/]", style="dim"))
    _console.print()
    _console.print(Panel(t, border_style="dim", padding=(0, 1), expand=False))

    rec_idx = next(
        (i for i, m in enumerate(models, 1) if m.is_recommended),
        extra_start,
    )

    while True:
        prompt = f"  [dim]Seçim [1-{extra_start}, Enter={rec_idx}]:[/] [dodger_blue1]"
        raw = _console.input(prompt).strip()
        _console.print("[/]", end="")
        if not raw:
            raw = str(rec_idx)
        if raw.isdigit() and 1 <= int(raw) <= extra_start:
            choice = int(raw)
            if choice == extra_start:
                _console.print(f"  [dodger_blue1]✓[/] Varsayılan: [bold]{default}[/]")
                return default
            selected = models[choice - 1]
            _console.print(f"  [dodger_blue1]✓[/] [bold]{selected.id}[/]")
            return selected.id
        _console.print(f"  [red1]Geçersiz.[/] [dim]1-{extra_start} arası veya Enter[/]")


# ---------------------------------------------------------------------------
# Generic menu helper (used by planner when multiple options exist)
# ---------------------------------------------------------------------------

def _menu(
    opts: list[tuple[AuthMode, str, str, str]],
    color: str,
    recommended: AuthMode,
) -> AuthMode:
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", justify="right", width=4)
    t.add_column(min_width=18)
    t.add_column(style="dim", min_width=10)
    t.add_column(style="dim")

    for i, (m, name, detail, hint) in enumerate(opts, 1):
        star = "  [green3]★[/]" if m == recommended else ""
        t.add_row(f"{i})", f"[bold white]{name}[/]{star}", detail, hint)

    _console.print(Panel(t, border_style=color, padding=(0, 1), expand=False))

    rec_idx = next(i for i, (m, *_) in enumerate(opts, 1) if m == recommended)

    while True:
        prompt = f"  [dim]Seçim [1-{len(opts)}, Enter={rec_idx}]:[/] [{color}]"
        raw = _console.input(prompt).strip()
        _console.print("[/]", end="")
        if not raw:
            raw = str(rec_idx)
        if raw.isdigit() and 1 <= int(raw) <= len(opts):
            chosen = opts[int(raw) - 1]
            _console.print(f"  [{color}]✓[/] [bold white]{chosen[1]}[/]")
            return chosen[0]
        _console.print(f"  [red1]Geçersiz.[/] [dim]1-{len(opts)} arası veya Enter[/]")


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

def _load_claude_models(mode: AuthMode) -> list[ModelInfo]:
    if mode == API:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            with _console.status("[dim]Claude modelleri getiriliyor…[/]", spinner="dots"):
                return fetch_claude_models(api_key)
    return CLAUDE_CURATED


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _summary(
    claude_mode: str, claude_model: str,
    gemini_mode: str, gemini_model: str,
) -> None:
    _console.print()

    worker_name = {
        API: "Gemini API",
        CLAUDE_WORKER: "Claude Code",
        CLI: "Gemini CLI",
    }.get(gemini_mode, gemini_mode)

    planner_name = {
        API: "API Anahtarı",
        CLI: "Claude Code",
    }.get(claude_mode, claude_mode)

    t = Table.grid(padding=(0, 3))
    t.add_column(style="dim", min_width=14)
    t.add_column(style="bold white")

    t.add_row("Planner",  f"[medium_purple1]{planner_name}[/]  [dim]{claude_model}[/]")
    t.add_row("Worker",   f"[dodger_blue1]{worker_name}[/]  [dim]{gemini_model}[/]")
    t.add_row("",         "")
    t.add_row("Kayıt",    "[dim]~/.myagent/config.json[/]")

    _console.print(Panel(
        t,
        title="[bold green3]✓ Kurulum tamamlandı[/]",
        border_style="green3",
        padding=(0, 2),
        expand=False,
    ))
    _console.print()
    _console.print("  [dim]Değiştirmek için:[/]  [bold]/setup[/]")
    _console.print()


# ---------------------------------------------------------------------------
# Fatal error
# ---------------------------------------------------------------------------

def _fatal(message: str) -> None:
    _console.print()
    _console.print(Panel(
        Text.from_markup(message),
        border_style="red1",
        title="[red1]Kurulum başarısız[/]",
        padding=(0, 2),
        expand=False,
    ))
    sys.exit(1)

"""
Planner — uses Claude to produce a deterministic step-by-step plan.

Auth modes:
  api  — Anthropic Python SDK (ANTHROPIC_API_KEY)
  cli  — `claude -p` subprocess (Claude Code OAuth session)

Model selection: runtime override > ~/.myagent/config.json > default (claude-opus-4-6)
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

from myagent.config.settings import ANTHROPIC_API_KEY, MAX_STEPS, PROMPTS_DIR, WORK_DIR


def _system_prompt() -> str:
    return (PROMPTS_DIR / "planner.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Codebase context (Phase 1: tree + README, Phase 2: AST symbols)
# ---------------------------------------------------------------------------

def _build_context() -> str:
    """Build a compact codebase context for the planner (workspace + history)."""
    parts: list[str] = []

    # Phase 1: directory tree (max depth 3, skip hidden/venv/cache dirs)
    tree = _dir_tree(WORK_DIR, max_depth=3)
    if tree:
        parts.append(f"Current workspace:\n{tree}")

    # Phase 1: README if present
    readme = WORK_DIR / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8", errors="ignore")[:800]
        parts.append(f"README:\n{content}")

    # Phase 2: AST symbol map for existing Python files
    symbols = _symbol_map(WORK_DIR)
    if symbols:
        parts.append(f"Existing symbols:\n{symbols}")

    # Phase 3: persistent task/file history (agentic memory)
    try:
        from myagent.memory.history import context_for_planner
        hist = context_for_planner(max_runs=5)
        if hist:
            parts.append(hist)
    except Exception:
        pass

    # Phase 4: Cognitive Knowledge Hub (lessons learned)
    try:
        from myagent.agent.memory import KnowledgeHub
        kh = KnowledgeHub()
        lessons = kh.get_context_for_planner()
        if lessons:
            parts.append(lessons)
    except Exception:
        pass

    return "\n\n".join(parts)


def _dir_tree(root: Path, max_depth: int = 3) -> str:
    SKIP = {".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
    lines: list[str] = []

    def _walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in SKIP or entry.name.startswith("."):
                continue
            connector = "└── " if entry == entries[-1] else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if entry == entries[-1] else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(root, "", 1)
    return "\n".join(lines) if lines else ""


def _symbol_map(root: Path) -> str:
    """Extract function/class signatures from .py files directly in WORK_DIR (depth 1 only)."""
    lines: list[str] = []
    for py_file in sorted(root.glob("*.py")):
        symbols = _extract_symbols(py_file)
        if symbols:
            lines.append(f"{py_file.name}:")
            lines.extend(f"  {s}" for s in symbols)
    return "\n".join(lines)


def _extract_symbols(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return []
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ast.unparse(node.args)
            ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            symbols.append(f"{prefix}def {node.name}({args}){ret}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(f"class {node.name}")
    return symbols


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plan(
    task: str,
    verbose: bool = False,
    stream_callback=None,
    session_context: str = "",
) -> list[str]:
    """Return an ordered list of step strings for *task*.

    session_context: optional extra context injected by the REPL (e.g. info
    about the previous task in this session) — not the same as workspace context
    which is auto-built from disk.
    """
    from myagent.config.auth import CLI, get_claude_mode
    mode = get_claude_mode()
    if verbose:
        from myagent.config.auth import get_claude_model
        print(f"  [planner] mode={mode}  model={get_claude_model()}", flush=True)

    context = _build_context()
    parts = [task]
    if context:
        parts.append(context)
    if session_context:
        parts.append(f"Session context:\n{session_context}")
    full_task = "\n\n".join(parts)
    usage = None

    if mode == CLI:
        raw, usage = _plan_via_cli(full_task, stream_callback=stream_callback)
    else:
        raw, usage = _plan_via_api(full_task, stream_callback=stream_callback)
    if verbose:
        print(f"  [planner raw output]\n{raw}\n", flush=True)
    return _parse_steps(raw)[:MAX_STEPS], usage


# ---------------------------------------------------------------------------
# API mode
# ---------------------------------------------------------------------------

def _plan_via_api(task: str, stream_callback=None) -> tuple[str, dict | None]:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Claude API modu seçili fakat ANTHROPIC_API_KEY tanımlı değil.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...  ya da  myagent> setup"
        )
    import anthropic
    from myagent.config.auth import get_claude_model

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if stream_callback:
        with client.messages.stream(
            model=get_claude_model(),
            max_tokens=1024,
            system=_system_prompt(),
            messages=[{"role": "user", "content": task}],
        ) as stream:
            for text in stream.text_stream:
                stream_callback(text)
            msg = stream.get_final_message()
            usage = {
                "input": msg.usage.input_tokens,
                "output": msg.usage.output_tokens,
            }
            return msg.content[0].text, usage

    response = client.messages.create(
        model=get_claude_model(),
        max_tokens=1024,
        system=_system_prompt(),
        messages=[{"role": "user", "content": task}],
    )
    usage = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    return response.content[0].text, usage


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def _plan_via_cli(task: str, stream_callback=None) -> tuple[str, dict | None]:
    from myagent.config.auth import get_claude_model
    model = get_claude_model()
    full_prompt = f"{_system_prompt()}\n\nTask: {task}"
    cmd = ["claude", "-p", full_prompt, "--model", model]

    if stream_callback:
        import time
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
            )
        except FileNotFoundError:
            raise RuntimeError("`claude` komutu bulunamadı. Claude Code kurulu mu?")
        from myagent import interrupt
        deadline = time.time() + 120
        output = interrupt.readline_interruptible(proc, stream_callback, deadline)
        stderr = proc.stderr.read() if proc.stderr else ""
        if proc.returncode not in (0, None):
            raise RuntimeError(f"Claude CLI hata (kod {proc.returncode}):\n{stderr.strip()}")
        return output, None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise RuntimeError("`claude` komutu bulunamadı. Claude Code kurulu mu?")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI zaman aşımına uğradı (120 s).")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Claude CLI hata (kod {result.returncode}):\n{detail}")
    return result.stdout, None


# ---------------------------------------------------------------------------
# Parser (shared)
# ---------------------------------------------------------------------------

def _parse_steps(text: str) -> list[str]:
    """Parse STEP N: lines; keep only the first occurrence of each step number."""
    seen: set[int] = set()
    steps: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^STEP\s+(\d+)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if match:
            num = int(match.group(1))
            if num not in seen:
                seen.add(num)
                steps.append(match.group(2).strip())
    return steps

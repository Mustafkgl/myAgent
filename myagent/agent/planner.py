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
from pathlib import Path

from myagent.config.settings import ANTHROPIC_API_KEY, PROMPTS_DIR, WORK_DIR


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


import subprocess

def _ripgrep(pattern: str, include_pattern: str = None) -> str:
    """Fast search using ripgrep (rg)."""
    cmd = ["rg", "--max-count", "20", "--line-number", "--column", "--color", "never", pattern]
    if include_pattern:
        cmd.extend(["-g", include_pattern])
    
    try:
        result = subprocess.run(cmd, cwd=WORK_DIR, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout
        return f"No results found for: {pattern}"
    except FileNotFoundError:
        return "Error: 'rg' (ripgrep) is not installed on the system."
    except Exception as e:
        return f"Search error: {str(e)}"

def _read_file_content(path_str: str) -> str:
    """Read full content of a file for Claude's deep understanding."""
    try:
        path = WORK_DIR / path_str
        if path.exists() and path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Limit to 8KB to save tokens but provide depth
            if len(content) > 8192:
                return content[:8192] + "\n... (truncated)"
            return content
        return f"Error: File not found: {path_str}"
    except Exception as e:
        return f"Read error: {str(e)}"

# ---------------------------------------------------------------------------
# Research Phase Loop (The "Thinking" before "Planning")
# ---------------------------------------------------------------------------

def _run_research(task: str, stream_callback=None) -> str:
    """Initial research phase where Claude can ask for file content or searches."""
    # This phase allows Claude to be proactive. 
    # For now, we enhance the context by automatically searching for key terms in the task.
    keywords = re.findall(r"\b\w{4,}\b", task) # Get significant words
    research_results = []
    
    if stream_callback:
        stream_callback("\n[research] Scanning project...\n")

    # Limit research to top 3 keywords to keep it fast
    for kw in keywords[:3]:
        if kw.lower() in ("create", "make", "build", "change", "update", "delete", "with", "from", "import"):
            continue
        res = _ripgrep(kw)
        if "No results found" not in res:
            # Only take the first 5 matches to save tokens
            lines = res.splitlines()[:5]
            research_results.append(f"Search (top 5) for '{kw}':\n" + "\n".join(lines))
            
    return "\n\n".join(research_results)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def plan(
    task: str,
    verbose: bool = False,
    stream_callback=None,
    session_context: str = "",
) -> tuple[list[str], str]:
    """Return (steps, interface_contract) for *task*.

    steps: ordered list of step strings
    interface_contract: INTERFACE: block describing file contracts between steps,
        or "" if the plan involves only a single file.

    session_context: optional extra context injected by the REPL.
    """
    from myagent.config.auth import CLI, get_claude_mode
    mode = get_claude_mode()
    if verbose:
        from myagent.config.auth import get_claude_model
        print(f"  [planner] mode={mode}  model={get_claude_model()}", flush=True)

    context = _build_context()
    research = _run_research(task, stream_callback=stream_callback)
    
    parts = [task]
    if research:
        parts.append(f"Research Findings (Deep Scan):\n{research}")
    if context:
        parts.append(context)
    if session_context:
        parts.append(f"Session context:\n{session_context}")
    full_task = "\n\n".join(parts)

    if mode == CLI:
        raw = _plan_via_cli(full_task, stream_callback=stream_callback)
    else:
        raw = _plan_via_api(full_task, stream_callback=stream_callback)
    if verbose:
        print(f"  [planner raw output]\n{raw}\n", flush=True)

    from myagent.config.auth import get_max_steps
    steps = _parse_steps(raw)[:get_max_steps()]
    interface = _extract_interface(raw)

    # Only generate an interface contract when multiple files are involved
    if not interface and _needs_interface(steps):
        interface = _build_interface(task, steps, mode)

    return steps, interface


# ---------------------------------------------------------------------------
# Interface contract helpers
# ---------------------------------------------------------------------------

_INTERFACE_RE = re.compile(
    r"INTERFACE:\s*\n((?:\s*-[^\n]+\n?)+)", re.IGNORECASE
)
_FILE_EXT_RE = re.compile(
    r"\b[\w./\\-]+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|toml|md|html|css|sh)\b"
)


def _extract_interface(raw: str) -> str:
    """Pull an INTERFACE: block from the raw planner output if present."""
    m = _INTERFACE_RE.search(raw)
    return m.group(0).strip() if m else ""


def _needs_interface(steps: list[str]) -> bool:
    """Return True if the plan creates multiple distinct files."""
    files: set[str] = set()
    for step in steps:
        for fname in _FILE_EXT_RE.findall(step):
            files.add(fname.lower())
    return len(files) >= 2


def _build_interface(task: str, steps: list[str], mode: str) -> str:
    """Ask Claude to produce a compact INTERFACE: block for the plan."""
    prompt = (
        f"Task: {task}\n\n"
        f"Plan:\n" + "\n".join(f"STEP {i}: {s}" for i, s in enumerate(steps, 1)) +
        "\n\nList the data contracts between these files in this EXACT format "
        "(nothing else, max 6 lines):\n"
        "INTERFACE:\n- file_a.py → function/class exported and what it returns\n"
        "- file_b.py → what it imports from file_a.py\n\n"
        "Only include files that depend on each other. "
        "If all steps touch the same file, respond with: INTERFACE: (single file)"
    )
    try:
        from myagent.config.auth import CLI as _CLI, get_claude_model
        from myagent.config.settings import ANTHROPIC_API_KEY

        model = get_claude_model()
        if mode == _CLI:
            from myagent.agent.claude_runner import is_error, run_claude_cli
            cmd = ["claude", "-p", prompt, "--model", model]
            raw = run_claude_cli(cmd, prompt, model, timeout=30)
            if is_error(raw):
                raw = ""
        else:
            if not ANTHROPIC_API_KEY:
                return ""
            import anthropic
            from myagent.agent.tokens import tracker
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=model, max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            tracker.add_claude(resp.usage.input_tokens, resp.usage.output_tokens, model)
            raw = resp.content[0].text.strip()

        # Extract just the INTERFACE: block
        m = _INTERFACE_RE.search(raw)
        if m:
            return m.group(0).strip()
        if "single file" in raw.lower():
            return ""
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# API mode
# ---------------------------------------------------------------------------

def _plan_via_api(task: str, stream_callback=None) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Claude API mode selected but ANTHROPIC_API_KEY is not defined.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...  ya da  myagent> setup"
        )
    import anthropic
    from myagent.agent.tokens import tracker
    from myagent.config.auth import get_claude_model

    model = get_claude_model()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if stream_callback:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=_system_prompt(),
            messages=[{"role": "user", "content": task}],
        ) as stream:
            for text in stream.text_stream:
                stream_callback(text)
            msg = stream.get_final_message()
            tracker.add_claude(msg.usage.input_tokens, msg.usage.output_tokens, model)
            return msg.content[0].text

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_system_prompt(),
        messages=[{"role": "user", "content": task}],
    )
    tracker.add_claude(response.usage.input_tokens, response.usage.output_tokens, model)
    return response.content[0].text


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def _plan_via_cli(task: str, stream_callback=None) -> str:
    from myagent.agent.claude_runner import _FALLBACK_SENTINEL, is_error, run_claude_cli
    from myagent.config.auth import get_claude_model

    model = get_claude_model()
    full_prompt = f"{_system_prompt()}\n\nTask: {task}"
    cmd = ["claude", "-p", full_prompt, "--model", model]

    output = run_claude_cli(cmd, full_prompt, model, timeout=120, stream_callback=stream_callback)
    if is_error(output):
        raise RuntimeError("Claude CLI planning failed. Token limit or connection error.")
    return output


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

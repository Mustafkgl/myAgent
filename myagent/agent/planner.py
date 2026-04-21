"""
Planner — uses Claude to produce a deterministic step-by-step plan.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from myagent.utils.logger import log

from myagent.config.auth import ANTHROPIC_API_KEY, GEMINI_API_KEY, CLI, API, get_claude_mode
from myagent.config.settings import PROMPTS_DIR, WORK_DIR


def _system_prompt() -> str:
    return (PROMPTS_DIR / "planner.txt").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Codebase context
# ---------------------------------------------------------------------------

def _build_context() -> str:
    """Build a compact codebase context for the planner."""
    log.debug("Building codebase context...")
    parts: list[str] = []
    tree = _dir_tree(WORK_DIR, max_depth=3)
    if tree:
        parts.append(f"Current workspace:\n{tree}")
    readme = WORK_DIR / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8", errors="ignore")[:800]
        parts.append(f"README:\n{content}")
    symbols = _symbol_map(WORK_DIR)
    if symbols:
        parts.append(f"Existing symbols:\n{symbols}")
    return "\n\n".join(parts)


def _dir_tree(path: Path, max_depth: int, current_depth: int = 0) -> str:
    if current_depth >= max_depth: return ""
    lines = []
    try:
        for p in sorted(path.iterdir()):
            if p.name.startswith((".", "__", "node_modules", "venv", ".venv")): continue
            lines.append("  " * current_depth + ("📁 " if p.is_dir() else "📄 ") + p.name)
            if p.is_dir():
                lines.append(_dir_tree(p, max_depth, current_depth + 1))
    except Exception: pass
    return "\n".join(filter(None, lines))


def _symbol_map(root: Path) -> str:
    symbols = []
    for p in root.glob("*.py"):
        try:
            content = p.read_text(encoding="utf-8")
            tree = ast.parse(content)
            file_syms = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
            if file_syms:
                symbols.append(f"{p.name}: {', '.join(file_syms)}")
        except Exception: pass
    return "\n".join(symbols)


# ---------------------------------------------------------------------------
# Research Tools
# ---------------------------------------------------------------------------

def _ripgrep(pattern: str, include_pattern: str = None) -> str:
    import subprocess
    log.debug(f"Searching for pattern: {pattern}")
    cmd = ["rg", "--max-count", "20", "--line-number", "--color", "never", pattern]
    if include_pattern: cmd.extend(["-g", include_pattern])
    try:
        result = subprocess.run(cmd, cwd=WORK_DIR, capture_output=True, text=True, timeout=5)
        return result.stdout if result.returncode == 0 else f"No results found for: {pattern}"
    except Exception as e:
        log.error(f"ripgrep failed: {str(e)}")
        return f"Search error: {str(e)}"

def _run_research(task: str, stream_callback=None) -> str:
    keywords = re.findall(r"\b\w{4,}\b", task)
    results = []
    if stream_callback: stream_callback("\n[research] Scanning project...\n")
    for kw in keywords[:3]:
        if kw.lower() in ("create", "make", "build", "change", "update", "delete", "with", "from", "import"): continue
        res = _ripgrep(kw)
        if "No results found" not in res:
            lines = res.splitlines()[:5]
            results.append(f"Search (top 5) for '{kw}':\n" + "\n".join(lines))
    return "\n\n".join(results)


# ---------------------------------------------------------------------------
# Main Plan Logic
# ---------------------------------------------------------------------------

def plan(
    task: str,
    verbose: bool = False,
    stream_callback=None,
    session_context: str = "",
) -> tuple[list[str], str]:
    log.info(f"Starting planning phase for task: {task[:50]}...")
    mode = get_claude_mode()
    
    # ── Complexity Detection & Roadmap
    massive_keywords = ("RDBMS", "REDIS", "OPERATING SYSTEM", "DATABASE ENGINE", "ENTERPRISE", "DISTRIBUTED", "OS", "KERNEL", "NMAP")
    is_massive = any(k in task.upper() for k in massive_keywords) or len(task) > 300

    if is_massive:
        roadmap_prompt = f"Task: {task}\n\nOutput ONLY a ROADMAP line: ROADMAP: Comp 1 | Comp 2 | ..."
        raw_roadmap = None
        
        if ANTHROPIC_API_KEY:
            if stream_callback: stream_callback("\n[planner] Massive project: Generating Roadmap via Claude API...\n")
            try: raw_roadmap = _plan_via_api(roadmap_prompt)
            except Exception as e:
                log.warning(f"Claude API roadmap failed: {str(e)}")

        if not raw_roadmap and GEMINI_API_KEY:
            if stream_callback: stream_callback("\n[planner] Roadmap via Gemini API...\n")
            try:
                from myagent.agent.worker import _gemini_api_batch
                raw_roadmap = _gemini_api_batch(roadmap_prompt)
            except Exception as e:
                log.warning(f"Gemini API roadmap failed: {str(e)}")

        if not raw_roadmap:
            if stream_callback: stream_callback("\n[planner] Roadmap via Claude CLI...\n")
            try: raw_roadmap = _plan_via_cli(roadmap_prompt, roadmap=True)
            except Exception as e:
                log.error(f"Claude CLI roadmap failed: {str(e)}")

        if raw_roadmap:
            m = re.search(r"ROADMAP:\s*(.+)", raw_roadmap, re.IGNORECASE)
            if m:
                components = [c.strip() for c in m.group(1).split("|")]
                log.info(f"Recursive Roadmap detected: {components}")
                all_steps = []
                for comp in components:
                    if stream_callback:
                        stream_callback(f"\n[planner] Planning component: {comp}...\n")
                    s, _ = plan(f"Plan for component: {comp} (Part of task: {task})", stream_callback=stream_callback)
                    all_steps.extend(s)
                return all_steps[:20], ""

    # Normal Planning
    context = _build_context()
    research = _run_research(task, stream_callback=stream_callback)
    full_prompt = f"{task}\n\nResearch:\n{research}\n\nContext:\n{context}\n\nSession:\n{session_context}"

    try:
        if mode == CLI:
            raw = _plan_via_cli(full_prompt, stream_callback=stream_callback)
        else:
            raw = _plan_via_api(full_prompt, stream_callback=stream_callback)
    except RuntimeError as e:
        # Extract the real error message from the prefix if it exists
        err_msg = str(e)
        if "__CLAUDE_ERROR__:" in err_msg:
            real_cause = err_msg.split("__CLAUDE_ERROR__:", 1)[1]
            log.error(f"Detailed Planning Failure: {real_cause}")
            raise RuntimeError(f"Claude planning failed. Reason: {real_cause}")
        raise

    from myagent.config.auth import get_max_steps
    steps = _parse_steps(raw)[:get_max_steps()]
    log.info(f"Planning complete. Generated {len(steps)} steps.")
    return steps, _extract_interface(raw)


def _plan_via_api(task: str, stream_callback=None) -> str:
    if not ANTHROPIC_API_KEY: 
        log.error("API mode selected but ANTHROPIC_API_KEY is missing.")
        raise RuntimeError("ANTHROPIC_API_KEY missing.")
    import anthropic
    from myagent.agent.tokens import tracker
    from myagent.config.auth import get_claude_model
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    model = get_claude_model()
    
    if stream_callback:
        with client.messages.stream(model=model, max_tokens=1024, system=_system_prompt(), messages=[{"role": "user", "content": task}]) as s:
            for t in s.text_stream: stream_callback(t)
            msg = s.get_final_message()
            tracker.add_claude(msg.usage.input_tokens, msg.usage.output_tokens, model)
            return msg.content[0].text
    
    resp = client.messages.create(model=model, max_tokens=1024, system=_system_prompt(), messages=[{"role": "user", "content": task}])
    tracker.add_claude(resp.usage.input_tokens, resp.usage.output_tokens, model)
    return resp.content[0].text


def _plan_via_cli(task: str, stream_callback=None, roadmap: bool = False) -> str:
    from myagent.agent.claude_runner import is_error, run_claude_cli
    from myagent.config.auth import get_claude_model
    model = get_claude_model()
    cmd = ["claude", "-p", task, "--model", model]
    if roadmap: cmd.extend(["--max-steps", "1"])
    out = run_claude_cli(cmd, task, model, timeout=120, stream_callback=stream_callback)
    if is_error(out):
        raise RuntimeError(out) # Will be caught and parsed in plan()
    return out


def _parse_steps(raw: str) -> list[str]:
    steps = []
    seen = set()
    for line in raw.splitlines():
        m = re.search(r"STEP\s*(\d+)\s*:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            num = int(m.group(1))
            if num not in seen:
                seen.add(num)
                steps.append(m.group(2).strip())
    return steps


def _extract_interface(raw: str) -> str:
    m = re.search(r"INTERFACE:.*?(?=\n\n|\Z)", raw, re.DOTALL | re.IGNORECASE)
    return m.group(0).strip() if m else ""

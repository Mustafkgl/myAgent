"""
Executor — executes structured JSON actions from the LLM.
Actions supported: write, bash, observation.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from myagent.config.settings import WORK_DIR


@dataclass
class ExecutionResult:
    ok: bool
    kind: str  # "file" | "bash" | "observation" | "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def parse_batch_and_execute(json_raw: str, expected: int = 0) -> list[ExecutionResult]:
    """Parse a JSON list of actions and execute them in order."""
    results: list[ExecutionResult] = []
    
    # Try to clean up markdown if LLM ignored the rules
    json_clean = json_raw.strip()
    if json_clean.startswith("```json"):
        json_clean = json_clean[7:]
    if json_clean.endswith("```"):
        json_clean = json_clean[:-3]
    json_clean = json_clean.strip()

    try:
        actions = json.loads(json_clean)
        if not isinstance(actions, list):
            return [ExecutionResult(ok=False, kind="error", message="LLM output is not a JSON list.")]
            
        for act in actions:
            results.append(_dispatch_action(act))
            
    except json.JSONDecodeError as e:
        return [ExecutionResult(ok=False, kind="error", message=f"JSON Parse Error: {str(e)}", details={"raw": json_raw})]

    return results


def _dispatch_action(action: dict[str, Any]) -> ExecutionResult:
    """Execute a single action object."""
    kind = action.get("action", "").lower()
    
    if kind == "write":
        return _write_file(action.get("filename", ""), action.get("content", ""))
    
    if kind == "bash":
        return _execute_bash(action.get("command", ""))
        
    if kind == "observation":
        msg = action.get("message", "")
        return ExecutionResult(ok=True, kind="observation", message=msg, details={"observation": msg})

    return ExecutionResult(ok=False, kind="error", message=f"Unknown action type: {kind}")


def _write_file(filename: str, content: str) -> ExecutionResult:
    """Safely write content to a file inside WORK_DIR."""
    if not filename:
        return ExecutionResult(ok=False, kind="error", message="Filename is missing.")

    # Security: resolve and confirm target stays inside WORK_DIR
    target = (WORK_DIR / filename).resolve()
    work_resolved = WORK_DIR.resolve()

    try:
        target.relative_to(work_resolved)
    except ValueError:
        return ExecutionResult(ok=False, kind="error", message=f"Security: path traversal denied for '{filename}'.")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except Exception as e:
        return ExecutionResult(ok=False, kind="error", message=f"File I/O error for '{filename}': {str(e)}", details={"error": str(e)})

    return ExecutionResult(
        ok=True,
        kind="file",
        message=f"Created/Updated file: {filename}",
        details={"path": str(target), "filename": filename, "size": len(content)}
    )


def _execute_bash(command: str) -> ExecutionResult:
    """Execute a shell command with security restrictions."""
    if not command:
        return ExecutionResult(ok=False, kind="error", message="BASH command is empty.")

    # Level 2 Security: Guardrail logic could be added here
    try:
        # We run with a timeout to prevent hanging
        result = subprocess.run(
            shlex.split(command),
            cwd=WORK_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        ok = (result.returncode == 0)
        msg = result.stdout if ok else result.stderr
        return ExecutionResult(
            ok=ok,
            kind="bash",
            message=msg.strip() or ("Success" if ok else "Error"),
            details={"exit_code": result.returncode, "command": command}
        )
    except Exception as e:
        return ExecutionResult(ok=False, kind="error", message=f"BASH error: {str(e)}")

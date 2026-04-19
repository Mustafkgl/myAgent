"""
Shared Claude CLI/API runner with token-limit detection and retry.

All Claude subprocess calls in reviewer.py, completer.py, and planner.py
route through run_claude_cli() / run_claude_api() so that:

  - Token-limit messages are detected and surfaced to the user (#11)
  - Non-limit failures emit a visible warning instead of silent APPROVED (#12)
  - Retry logic lives in one place (max 3 attempts after limit clears)
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Callable

# Matches Claude CLI's "You've hit your limit · resets 8pm (Europe/Istanbul)"
_LIMIT_RE = re.compile(
    r"hit your limit.*?resets\s+(\S+)\s+\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_MAX_RETRIES = 3
_FALLBACK_SENTINEL = "__CLAUDE_ERROR__"


def _detect_limit(text: str) -> tuple[bool, str]:
    """Return (is_limit, human_readable_reset_info)."""
    m = _LIMIT_RE.search(text)
    if m:
        return True, f"{m.group(1)} ({m.group(2)})"
    if "hit your limit" in text.lower():
        return True, "bilinmiyor"
    return False, ""


def _wait_for_user(reset_info: str, attempt: int) -> None:
    """Block until the user presses Enter after a token limit hit."""
    print(
        f"\n⏸  Claude token limiti doldu · {reset_info} yenileniyor\n"
        f"   Token yenilenince Enter'a bas... (deneme {attempt}/{_MAX_RETRIES})",
        flush=True,
    )
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def run_claude_cli(
    cmd: list[str],
    full_prompt: str,
    model: str,
    timeout: int = 120,
    stream_callback: Callable[[str], None] | None = None,
) -> str:
    """Run a Claude CLI command with token-limit detection and retry.

    Returns the stripped stdout on success.
    Returns _FALLBACK_SENTINEL on non-limit errors (caller should warn + fallback).
    Blocks (with user prompt) on token-limit errors and retries up to _MAX_RETRIES times.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            if stream_callback:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                from myagent import interrupt
                deadline = time.time() + timeout
                output = interrupt.readline_interruptible(proc, stream_callback, deadline)
                stderr = proc.stderr.read() if proc.stderr else ""
                combined = output + stderr

                if proc.returncode not in (0, None):
                    is_limit, reset_info = _detect_limit(combined)
                    if is_limit:
                        _wait_for_user(reset_info, attempt)
                        continue
                    return _FALLBACK_SENTINEL

                from myagent.agent.tokens import tracker
                tracker.add_claude(len(full_prompt) // 4, len(output) // 4, model, estimated=True)
                return output.strip()

            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                combined = result.stdout + result.stderr

                if result.returncode != 0:
                    is_limit, reset_info = _detect_limit(combined)
                    if is_limit:
                        _wait_for_user(reset_info, attempt)
                        continue
                    return _FALLBACK_SENTINEL

                from myagent.agent.tokens import tracker
                tracker.add_claude(len(full_prompt) // 4, len(result.stdout) // 4, model, estimated=True)
                return result.stdout.strip()

        except subprocess.TimeoutExpired:
            return _FALLBACK_SENTINEL
        except Exception:
            return _FALLBACK_SENTINEL

    # All retries exhausted after token limit waits
    return _FALLBACK_SENTINEL


def is_error(output: str) -> bool:
    return output == _FALLBACK_SENTINEL


def warn_skipped(context: str, error_code: int | None = None) -> None:
    """Print a visible warning when a Claude call is silently skipped."""
    code_str = f" (error code: {error_code})" if error_code is not None else ""
    print(f"\n⚠  Claude {context} failed{code_str} — skipping step\n", flush=True)

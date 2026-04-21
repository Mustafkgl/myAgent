"""
Shared Claude CLI/API runner with token-limit detection and retry.
"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Callable
from myagent.utils.logger import log

# Matches Claude CLI's "You've hit your limit · resets 8pm (Europe/Istanbul)"
_LIMIT_RE = re.compile(
    r"hit your limit.*?resets\s+(\S+)\s+\(([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)
_MAX_RETRIES = 3
_FALLBACK_PREFIX = "__CLAUDE_ERROR__"


def _detect_limit(text: str) -> tuple[bool, str]:
    """Return (is_limit, human_readable_reset_info)."""
    m = _LIMIT_RE.search(text)
    if m:
        return True, f"{m.group(1)} ({m.group(2)})"
    if "hit your limit" in text.lower():
        return True, "unknown"
    return False, ""


def _wait_for_user(reset_info: str, attempt: int) -> None:
    """Block until the user presses Enter after a token limit hit."""
    log.warning(f"Token limit hit. Waiting for reset at {reset_info}. Attempt {attempt}/{_MAX_RETRIES}")
    print(
        f"\n⏸  Claude token limit hit · resets {reset_info}\n"
        f"   Press Enter when reset... (attempt {attempt}/{_MAX_RETRIES})",
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
    """Run a Claude CLI command with detailed logging and error bubbling."""
    log.debug(f"Executing Claude CLI command: {' '.join(cmd)}")
    
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
                    log.error(f"Claude CLI error (attempt {attempt}): {stderr.strip()}")
                    is_limit, reset_info = _detect_limit(combined)
                    if is_limit:
                        _wait_for_user(reset_info, attempt)
                        continue
                    # Return actual stderr prefixed with sentinel
                    return f"{_FALLBACK_PREFIX}:{stderr.strip()}"

                from myagent.agent.tokens import tracker
                tracker.add_claude(len(full_prompt) // 4, len(output) // 4, model, estimated=True)
                log.info(f"Claude CLI success (attempt {attempt})")
                return output.strip()

            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                combined = result.stdout + result.stderr

                if result.returncode != 0:
                    log.error(f"Claude CLI error (attempt {attempt}): {result.stderr.strip()}")
                    is_limit, reset_info = _detect_limit(combined)
                    if is_limit:
                        _wait_for_user(reset_info, attempt)
                        continue
                    return f"{_FALLBACK_PREFIX}:{result.stderr.strip()}"

                from myagent.agent.tokens import tracker
                tracker.add_claude(len(full_prompt) // 4, len(result.stdout) // 4, model, estimated=True)
                log.info(f"Claude CLI success (attempt {attempt})")
                return result.stdout.strip()

        except subprocess.TimeoutExpired:
            log.error(f"Claude CLI timeout after {timeout}s")
            return f"{_FALLBACK_PREFIX}:TimeoutExpired after {timeout}s"
        except Exception as e:
            log.exception(f"Unexpected error running Claude CLI")
            return f"{_FALLBACK_PREFIX}:{str(e)}"

    return f"{_FALLBACK_PREFIX}:Max retries exhausted after token limit"


def is_error(output: str) -> bool:
    """Check if the response is a marked error."""
    return output.startswith(_FALLBACK_PREFIX)


def warn_skipped(context: str, error_code: int | None = None) -> None:
    """Print a visible warning when a Claude call is silently skipped."""
    log.warning(f"Claude {context} call failed and was skipped.")
    code_str = f" (error code: {error_code})" if error_code is not None else ""
    print(f"\n⚠  Claude {context} failed{code_str} — step skipped\n", flush=True)

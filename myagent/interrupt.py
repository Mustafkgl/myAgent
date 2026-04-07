"""
Interrupt handling — ESC key + Ctrl+C during model calls.

Usage:
  with interrupt.context():        # wraps a model call
      result = run_something()
  if interrupt.was_raised():
      # user pressed ESC or Ctrl+C
      ...

Internal:
  - ESC watcher: background thread reads /dev/tty raw, detects standalone ESC
  - readline_interruptible(): drop-in replacement for proc.stdout readline loops
"""

from __future__ import annotations

import subprocess
import threading
import time
from contextlib import contextmanager


class Interrupted(BaseException):
    """Raised when the user presses ESC or Ctrl+C during a model call."""


_event = threading.Event()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_set() -> bool:
    return _event.is_set()


def clear() -> None:
    _event.clear()


@contextmanager
def context():
    """Start ESC watcher for the duration of a command.

    Clears the event on entry.  On exit the watcher stops but the event is
    intentionally NOT cleared — so an ESC pressed between two streaming calls
    (both inside the same outer context) is still seen by the next call.
    Call clear() explicitly after catching Interrupted if you want to reset.
    """
    clear()
    watcher = _EscWatcher()
    watcher.start()
    try:
        yield
    finally:
        watcher.stop()


def readline_interruptible(
    proc: subprocess.Popen,
    callback=None,
    deadline: float | None = None,
) -> str:
    """Read proc.stdout line-by-line, raising Interrupted on ESC / Ctrl+C.

    Replaces the standard `for line in iter(proc.stdout.readline, "")` pattern.
    Kills the subprocess and raises Interrupted when the user interrupts.
    """
    parts: list[str] = []
    try:
        assert proc.stdout is not None
        for line in iter(proc.stdout.readline, ""):
            if _event.is_set():
                proc.kill()
                raise Interrupted()
            if deadline and time.time() > deadline:
                proc.kill()
                break
            parts.append(line)
            if callback:
                callback(line)
    except KeyboardInterrupt:
        proc.kill()
        _event.set()
        raise Interrupted()
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass
    return "".join(parts)


# ---------------------------------------------------------------------------
# ESC watcher thread
# ---------------------------------------------------------------------------

class _EscWatcher(threading.Thread):
    """Daemon thread that monitors /dev/tty for a standalone ESC keypress."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import select
            import termios
            import tty

            tty_f = open("/dev/tty", "rb", buffering=0)
            fd = tty_f.fileno()
            old = termios.tcgetattr(fd)
            tty.setraw(fd)
            try:
                while not self._stop_event.is_set() and not _event.is_set():
                    r, _, _ = select.select([tty_f], [], [], 0.05)
                    if not r:
                        continue
                    ch = tty_f.read(1)
                    if ch != b"\x1b":
                        continue
                    # Distinguish standalone ESC from escape sequences (arrow keys etc.)
                    r2, _, _ = select.select([tty_f], [], [], 0.05)
                    if r2:
                        # More bytes follow → escape sequence, ignore
                        tty_f.read(1)
                        r3, _, _ = select.select([tty_f], [], [], 0.02)
                        if r3:
                            tty_f.read(1)
                    else:
                        # Standalone ESC → interrupt
                        _event.set()
                        break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                tty_f.close()
        except Exception:
            pass

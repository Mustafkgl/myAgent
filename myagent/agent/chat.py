"""
Chat — conversational front-end for myagent.

Routes user input to one of two modes:
  TASK   → return task description for the pipeline to execute
  ANSWER → stream Claude's response directly to the user

History is maintained in-memory for the session (last MAX_HISTORY turns).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Literal

from myagent.config.settings import ANTHROPIC_API_KEY, WORK_DIR

_SYSTEM = """\
You are myagent — a terminal AI assistant for a developer. You can both answer questions \
and execute coding tasks by delegating to a code-generation engine.

When the user's message is a TASK (create, build, write, fix, add, modify, test, refactor, \
generate, run, deploy something — any request to produce or change files/code):

Respond EXACTLY with this format (nothing else):
ACTION: TASK
TASK: <one precise sentence in English, enough for a code generator to work from>

When the user's message is a QUESTION, EXPLANATION REQUEST, or CONVERSATION \
(explain, describe, what is, how does, why, show me, list, tell me, general chat):

Respond EXACTLY with this format:
ACTION: ANSWER
<your full response in the SAME language the user used — Turkish if they wrote Turkish, \
English if they wrote English>

IMPORTANT:
- Never start a task silently. If you're not 100% sure it's a task, choose ANSWER.
- For ambiguous requests, choose ANSWER and ask a clarifying question.
- Workspace files listed below are for your context; mention them when relevant.
- Keep ANSWER responses concise but complete. Use markdown for code blocks.
"""

MAX_HISTORY = 10  # keep last N turns per side


@dataclass
class RouteResult:
    action: Literal["task", "answer"]
    task: str = ""    # if action == "task"
    answer: str = ""  # if action == "answer"


@dataclass
class Chat:
    """Maintains conversation history and routes user input."""
    history: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        user_input: str,
        stream_callback=None,
    ) -> RouteResult:
        """Decide whether input is a TASK or an ANSWER, streaming if callback given."""
        workspace = _workspace_summary()
        system = _SYSTEM
        if workspace:
            system = f"{_SYSTEM}\n\nWorkspace files:\n{workspace}"

        self._add("user", user_input)

        raw = _ask_claude(
            system=system,
            history=self.history,
            stream_callback=stream_callback,
        )

        result = _parse(raw)

        # Store assistant turn in history
        if result.action == "answer":
            self._add("assistant", result.answer)
        else:
            # Record what task was routed so context is maintained
            self._add("assistant", f"[Executing task: {result.task}]")

        return result

    def add_task_result(self, task: str, summary: str) -> None:
        """Inject a completed task's summary into history for context."""
        self._add("assistant", f"[Task completed: {task}]\n{summary[:400]}")
        self._trim()

    def load_history(self, messages: list[dict]) -> None:
        """Restore chat history from a persisted session."""
        self.history = [
            {"role": m["role"], "content": m.get("text") or m.get("content", "")}
            for m in messages
            if m.get("role") in ("user", "assistant")
            and (m.get("text") or m.get("content"))
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > MAX_HISTORY * 2:
            self.history = self.history[-(MAX_HISTORY * 2):]


# ---------------------------------------------------------------------------
# Workspace context
# ---------------------------------------------------------------------------

def _workspace_summary() -> str:
    """One-line list of files in WORK_DIR (no dirs, no hidden)."""
    try:
        files = [
            p.name for p in sorted(WORK_DIR.iterdir())
            if p.is_file() and not p.name.startswith(".")
        ]
        return ", ".join(files) if files else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Claude caller — supports both API and CLI modes
# ---------------------------------------------------------------------------

def _ask_claude(
    system: str,
    history: list[dict],
    stream_callback=None,
) -> str:
    from myagent.config.auth import CLI, get_claude_mode, get_claude_model
    mode = get_claude_mode()

    if mode == CLI:
        return _ask_via_cli(system, history, stream_callback)
    else:
        return _ask_via_api(system, history, stream_callback)


def _ask_via_api(system: str, history: list[dict], stream_callback=None) -> str:
    if not ANTHROPIC_API_KEY:
        return "ACTION: ANSWER\nHata: ANTHROPIC_API_KEY tanımlı değil."
    try:
        import anthropic
        from myagent.agent.tokens import tracker
        from myagent.config.auth import get_claude_model
        model = get_claude_model()
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if stream_callback:
            with client.messages.stream(
                model=model,
                max_tokens=1024,
                system=system,
                messages=history,
            ) as stream:
                parts: list[str] = []
                for text in stream.text_stream:
                    parts.append(text)
                    stream_callback(text)
                msg = stream.get_final_message()
                tracker.add_claude(msg.usage.input_tokens, msg.usage.output_tokens, model)
                return "".join(parts).strip()

        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=history,
        )
        tracker.add_claude(response.usage.input_tokens, response.usage.output_tokens, model)
        return response.content[0].text.strip()
    except Exception as exc:
        return f"ACTION: ANSWER\nHata: {exc}"


def _ask_via_cli(system: str, history: list[dict], stream_callback=None) -> str:
    from myagent.agent.tokens import tracker
    from myagent.config.auth import get_claude_model

    model = get_claude_model()
    # Build a single prompt: system + conversation history
    turns: list[str] = [system, ""]
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        turns.append(f"{role}: {msg['content']}")
    full_prompt = "\n".join(turns)

    cmd = ["claude", "-p", full_prompt, "--model", model]

    if stream_callback:
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
            from myagent import interrupt
            deadline = time.time() + 60
            output = interrupt.readline_interruptible(proc, stream_callback, deadline)
            if output.strip():
                tracker.add_claude(len(full_prompt) // 4, len(output) // 4, model, estimated=True)
            return output.strip() or "ACTION: ANSWER\nZaman aşımı."
        except Exception as exc:
            return f"ACTION: ANSWER\nHata: {exc}"
    else:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return f"ACTION: ANSWER\nClaude CLI hata: {result.stderr.strip()[:200]}"
            tracker.add_claude(len(full_prompt) // 4, len(result.stdout) // 4, model, estimated=True)
            return result.stdout.strip()
        except Exception as exc:
            return f"ACTION: ANSWER\nHata: {exc}"


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse(raw: str) -> RouteResult:
    """Parse Claude's structured ACTION: TASK / ACTION: ANSWER response."""
    text = raw.strip()
    if not text:
        return RouteResult(action="answer", answer="(boş yanıt)")

    lines = text.splitlines()
    first = lines[0].strip().upper()

    if first == "ACTION: TASK":
        # Find TASK: line
        for line in lines[1:]:
            if line.strip().upper().startswith("TASK:"):
                task = line.split(":", 1)[1].strip()
                return RouteResult(action="task", task=task)
        # No TASK: line found — treat whole thing as answer
        return RouteResult(action="answer", answer=text)

    if first == "ACTION: ANSWER":
        answer = "\n".join(lines[1:]).strip()
        return RouteResult(action="answer", answer=answer or "(boş yanıt)")

    # Claude didn't follow the format — treat as plain answer
    return RouteResult(action="answer", answer=text)

"""
Pipeline state persistence — checkpoint each phase for --resume support.

State files: ~/.myagent/pipeline_sessions/{session_id}/state.json

Phases (in order): started → planned → executed → review → complete
"""

from __future__ import annotations

import json
import time
import uuid as _uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

_STATE_DIR = Path.home() / ".myagent" / "pipeline_sessions"

# Ordered phases — used to determine which phases are already done
_PHASE_ORDER = ["started", "planned", "executed", "review", "complete"]


@dataclass
class PipelineState:
    session_id: str
    task: str
    work_dir: str
    phase: str
    steps: list[str] = field(default_factory=list)
    interface_contract: str = ""
    created_files: list[str] = field(default_factory=list)
    review_round: int = 0
    fix_steps: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def new_session_id() -> str:
    return _uuid.uuid4().hex[:12]


def _phase_rank(phase: str) -> int:
    """Return the numeric rank of a phase string (review_N counts as 'review')."""
    if phase.startswith("review"):
        phase = "review"
    try:
        return _PHASE_ORDER.index(phase)
    except ValueError:
        return 0


def phase_done(saved_phase: str, checkpoint: str) -> bool:
    """Return True if *checkpoint* was already reached in *saved_phase*."""
    return _phase_rank(saved_phase) >= _phase_rank(checkpoint)


def save_state(state: PipelineState) -> None:
    state.updated_at = time.time()
    session_dir = _STATE_DIR / state.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "state.json").write_text(
        json.dumps(asdict(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_session(session_id: str) -> PipelineState | None:
    path = _STATE_DIR / session_id / "state.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineState(**data)
    except Exception:
        return None


def load_latest_incomplete() -> PipelineState | None:
    sessions = list_sessions()
    for s in sessions:
        if s.phase != "complete":
            return s
    return None


def list_sessions() -> list[PipelineState]:
    if not _STATE_DIR.exists():
        return []
    out: list[PipelineState] = []
    for p in sorted(
        _STATE_DIR.glob("*/state.json"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    ):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(PipelineState(**data))
        except Exception:
            pass
    return out

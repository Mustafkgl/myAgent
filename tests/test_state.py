"""Tests for myagent.agent.state — pipeline state persistence."""

import json
import time
from pathlib import Path

import pytest

from myagent.agent.state import (
    PipelineState,
    _phase_rank,
    list_sessions,
    load_latest_incomplete,
    load_session,
    new_session_id,
    phase_done,
    save_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_state_dir(tmp_path, monkeypatch):
    """Redirect _STATE_DIR to a temp directory for all tests."""
    import myagent.agent.state as state_mod
    monkeypatch.setattr(state_mod, "_STATE_DIR", tmp_path)
    return tmp_path


def _make_state(**kwargs) -> PipelineState:
    defaults = dict(
        session_id=new_session_id(),
        task="test task",
        work_dir="/tmp/work",
        phase="started",
        started_at=time.time(),
        updated_at=time.time(),
    )
    defaults.update(kwargs)
    return PipelineState(**defaults)


# ---------------------------------------------------------------------------
# new_session_id
# ---------------------------------------------------------------------------

def test_new_session_id_length():
    sid = new_session_id()
    assert len(sid) == 12
    assert sid.isalnum()


def test_new_session_id_unique():
    assert new_session_id() != new_session_id()


# ---------------------------------------------------------------------------
# _phase_rank / phase_done
# ---------------------------------------------------------------------------

def test_phase_rank_order():
    assert _phase_rank("started") < _phase_rank("planned")
    assert _phase_rank("planned") < _phase_rank("executed")
    assert _phase_rank("executed") < _phase_rank("review")
    assert _phase_rank("review") < _phase_rank("complete")


def test_phase_rank_review_variants():
    assert _phase_rank("review_1") == _phase_rank("review")
    assert _phase_rank("review_4") == _phase_rank("review")


def test_phase_done_true():
    assert phase_done("complete", "planned") is True
    assert phase_done("executed", "planned") is True
    assert phase_done("executed", "executed") is True
    assert phase_done("review_2", "executed") is True


def test_phase_done_false():
    assert phase_done("planned", "executed") is False
    assert phase_done("started", "planned") is False
    assert phase_done("executed", "complete") is False


# ---------------------------------------------------------------------------
# save_state / load_session
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(tmp_state_dir):
    s = _make_state(phase="planned", steps=["step1", "step2"])
    save_state(s)

    loaded = load_session(s.session_id)
    assert loaded is not None
    assert loaded.session_id == s.session_id
    assert loaded.phase == "planned"
    assert loaded.steps == ["step1", "step2"]


def test_save_updates_updated_at(tmp_state_dir):
    before = time.time()
    s = _make_state()
    save_state(s)
    assert s.updated_at >= before


def test_save_creates_file(tmp_state_dir):
    s = _make_state()
    save_state(s)
    assert (tmp_state_dir / s.session_id / "state.json").exists()


def test_load_nonexistent_returns_none(tmp_state_dir):
    assert load_session("doesnotexist") is None


def test_load_corrupt_returns_none(tmp_state_dir):
    sid = new_session_id()
    d = tmp_state_dir / sid
    d.mkdir()
    (d / "state.json").write_text("not json")
    assert load_session(sid) is None


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

def test_list_sessions_empty(tmp_state_dir):
    assert list_sessions() == []


def test_list_sessions_returns_all(tmp_state_dir):
    for phase in ["planned", "executed", "complete"]:
        save_state(_make_state(phase=phase))
    sessions = list_sessions()
    assert len(sessions) == 3


def test_list_sessions_sorted_newest_first(tmp_state_dir):
    s1 = _make_state(phase="planned")
    save_state(s1)
    time.sleep(0.01)
    s2 = _make_state(phase="complete")
    save_state(s2)

    sessions = list_sessions()
    assert sessions[0].session_id == s2.session_id  # newer first


# ---------------------------------------------------------------------------
# load_latest_incomplete
# ---------------------------------------------------------------------------

def test_load_latest_incomplete_none_when_empty(tmp_state_dir):
    assert load_latest_incomplete() is None


def test_load_latest_incomplete_skips_complete(tmp_state_dir):
    save_state(_make_state(phase="complete"))
    assert load_latest_incomplete() is None


def test_load_latest_incomplete_returns_incomplete(tmp_state_dir):
    s = _make_state(phase="executed")
    save_state(s)
    result = load_latest_incomplete()
    assert result is not None
    assert result.session_id == s.session_id


def test_load_latest_incomplete_returns_newest(tmp_state_dir):
    s1 = _make_state(phase="planned")
    save_state(s1)
    time.sleep(0.01)
    s2 = _make_state(phase="executed")
    save_state(s2)

    result = load_latest_incomplete()
    assert result is not None
    assert result.session_id == s2.session_id


def test_load_latest_incomplete_ignores_complete(tmp_state_dir):
    save_state(_make_state(phase="complete"))
    s = _make_state(phase="review_2")
    save_state(s)

    result = load_latest_incomplete()
    assert result is not None
    assert result.session_id == s.session_id

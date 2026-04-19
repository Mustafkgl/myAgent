"""Tests for session topic extraction and display."""
import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

# Make sure we import from the project
sys.path.insert(0, str(Path(__file__).parent.parent))

from myagent.repl import _extract_topic, _sessions_save, _sessions_list, _SESSIONS_DIR


class TestExtractTopic(unittest.TestCase):

    def test_extracts_first_user_message(self):
        msgs = [
            {"role": "user", "text": "FastAPI ile REST API nasıl yazılır?", "ts": "2026-04-19"},
            {"role": "assistant", "text": "FastAPI...", "ts": "2026-04-19"},
        ]
        assert _extract_topic(msgs) == "FastAPI ile REST API nasıl yazılır?"

    def test_skips_assistant_messages(self):
        msgs = [
            {"role": "assistant", "text": "Merhaba!", "ts": "2026-04-19"},
            {"role": "user", "text": "Nasıl öğrenebilirim?", "ts": "2026-04-19"},
        ]
        assert _extract_topic(msgs) == "Nasıl öğrenebilirim?"

    def test_empty_messages(self):
        assert _extract_topic([]) == ""

    def test_no_user_messages(self):
        msgs = [{"role": "assistant", "text": "Merhaba", "ts": "2026-04-19"}]
        assert _extract_topic(msgs) == ""

    def test_truncates_at_120(self):
        long_text = "A" * 200
        msgs = [{"role": "user", "text": long_text, "ts": "2026-04-19"}]
        result = _extract_topic(msgs)
        assert len(result) == 120
        assert result == "A" * 120

    def test_collapses_newlines(self):
        msgs = [{"role": "user", "text": "satır 1\nsatır 2\nsatır 3", "ts": "2026-04-19"}]
        result = _extract_topic(msgs)
        assert "\n" not in result
        assert result == "satır 1 satır 2 satır 3"

    def test_strips_whitespace(self):
        msgs = [{"role": "user", "text": "   boşluklu mesaj   ", "ts": "2026-04-19"}]
        assert _extract_topic(msgs) == "boşluklu mesaj"


class TestSessionsSaveTopic(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._orig_dir = _SESSIONS_DIR

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_topic_saved_in_json(self):
        import myagent.repl as repl_mod
        orig = repl_mod._SESSIONS_DIR
        tmp_dir = Path(self._tmp)
        repl_mod._SESSIONS_DIR = tmp_dir
        try:
            msgs = [
                {"role": "user", "text": "Python decorator nedir?", "ts": "2026-04-19"},
                {"role": "assistant", "text": "Decorator...", "ts": "2026-04-19"},
            ]
            _sessions_save("test-id-123", "19 Apr 2026 10:00", msgs)
            saved = json.loads((tmp_dir / "test-id-123.json").read_text())
            assert saved["topic"] == "Python decorator nedir?"
        finally:
            repl_mod._SESSIONS_DIR = orig

    def test_empty_topic_when_no_messages(self):
        import myagent.repl as repl_mod
        orig = repl_mod._SESSIONS_DIR
        tmp_dir = Path(self._tmp)
        repl_mod._SESSIONS_DIR = tmp_dir
        try:
            _sessions_save("empty-id", "19 Apr 2026 11:00", [])
            saved = json.loads((tmp_dir / "empty-id.json").read_text())
            assert saved["topic"] == ""
        finally:
            repl_mod._SESSIONS_DIR = orig


class TestCmdSessionsDisplay(unittest.TestCase):

    def _run_cmd_sessions_with_mock_data(self, sessions_data):
        """Patch _sessions_list and capture console output."""
        import myagent.repl as repl_mod
        output_lines = []

        class CapturingConsole:
            def print(self, renderable=None, **kwargs):
                from rich.text import Text as RichText
                if isinstance(renderable, RichText):
                    output_lines.append(renderable.plain)
                else:
                    output_lines.append(str(renderable) if renderable else "")

        orig_console = repl_mod._console
        repl_mod._console = CapturingConsole()
        try:
            with patch.object(repl_mod, '_sessions_list', return_value=sessions_data):
                repl_mod._cmd_sessions()
        finally:
            repl_mod._console = orig_console

        return "\n".join(output_lines)

    def test_shows_topic_in_output(self):
        sessions = [{
            "id": "abc12345-0000-0000-0000-000000000000",
            "name": "19 Apr 2026 14:00",
            "updated_at": "2026-04-19T14:00:00",
            "topic": "FastAPI endpoint nasıl yazılır?",
            "messages": [
                {"role": "user", "text": "FastAPI endpoint nasıl yazılır?", "ts": "2026-04-19"},
            ],
        }]
        output = self._run_cmd_sessions_with_mock_data(sessions)
        assert "FastAPI endpoint nasıl yazılır?" in output, f"Topic not in output:\n{output}"

    def test_falls_back_to_messages_when_no_topic_field(self):
        sessions = [{
            "id": "def67890-0000-0000-0000-000000000000",
            "name": "19 Apr 2026 15:00",
            "updated_at": "2026-04-19T15:00:00",
            "messages": [
                {"role": "user", "text": "Eski oturum, topic alanı yok", "ts": "2026-04-19"},
            ],
        }]
        output = self._run_cmd_sessions_with_mock_data(sessions)
        assert "Eski oturum, topic alanı yok" in output, f"Fallback topic not in output:\n{output}"

    def test_no_crash_on_empty_sessions(self):
        output = self._run_cmd_sessions_with_mock_data([])
        assert "oturum yok" in output.lower() or "yok" in output

    def test_long_topic_truncated(self):
        long_topic = "X" * 200
        sessions = [{
            "id": "ghi11111-0000-0000-0000-000000000000",
            "name": "19 Apr 2026 16:00",
            "updated_at": "2026-04-19T16:00:00",
            "topic": long_topic,
            "messages": [],
        }]
        output = self._run_cmd_sessions_with_mock_data(sessions)
        assert "…" in output, "Long topic should be truncated with ellipsis"


if __name__ == "__main__":
    unittest.main(verbosity=2)

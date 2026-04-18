"""
Knowledge Hub — persistent memory logic for myAgent.
Stores successful patterns and resolutions to avoid repeating mistakes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime


class KnowledgeHub:
    def __init__(self, storage_path: str | Path | None = None):
        if storage_path is None:
            storage_path = Path.home() / ".myagent" / "knowledge.json"
        
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if not self.storage_path.exists():
            return {"lessons": [], "patterns": {}}
        try:
            return json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return {"lessons": [], "patterns": {}}

    def save(self) -> None:
        try:
            self.storage_path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False), 
                encoding="utf-8"
            )
        except Exception:
            pass

    def add_lesson(self, task: str, resolution: str):
        """Add a learned lesson (e.g. how a bug was fixed)."""
        self.data["lessons"].append({
            "ts": datetime.now().isoformat(),
            "task": task,
            "resolution": resolution
        })
        # Keep only last 50 lessons
        if len(self.data["lessons"]) > 50:
            self.data["lessons"] = self.data["lessons"][-50:]
        self.save()

    def get_context_for_planner(self) -> str:
        """Return a summarized context of past lessons for the Claude Planner."""
        if not self.data["lessons"]:
            return ""
        
        lines = ["\n[Past Lessons Learned]:"]
        # Take last 5 lessons for relevance
        for lesson in self.data["lessons"][-5:]:
            lines.append(f"- Task: {lesson['task']} | Lesson: {lesson['resolution']}")
        
        return "\n".join(lines)

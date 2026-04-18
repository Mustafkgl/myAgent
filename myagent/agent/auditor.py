"""
Auditor Agent — performs security (bandit) and complexity (mccabe) analysis.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AuditReport:
    score: int  # 0-100 (higher is better)
    security_issues: list[dict]
    complexity_issues: list[dict]
    summary: str


class AuditAgent:
    def __init__(self, work_dir: str | Path = "."):
        self.work_dir = Path(work_dir)

    def audit_files(self, files: list[str]) -> AuditReport:
        """Run bandit and mccabe on the given files."""
        sec_issues = []
        comp_issues = []
        
        for f in files:
            f_path = self.work_dir / f
            if not f_path.exists() or not f.endswith(".py"):
                continue
                
            # 1. Security (Bandit)
            try:
                # Run bandit on a single file to keep things focused
                res = subprocess.run(
                    ["bandit", "-f", "json", str(f_path)],
                    capture_output=True, text=True, check=False
                )
                if res.stdout:
                    data = json.loads(res.stdout)
                    for issue in data.get("results", []):
                        sec_issues.append({
                            "file": f,
                            "issue": issue.get("issue_text"),
                            "severity": issue.get("issue_severity"),
                            "line": issue.get("line_number")
                        })
            except Exception:
                pass

            # 2. Complexity (McCabe)
            try:
                # mccabe output format: line:col: 'function_name' complexity
                res = subprocess.run(
                    ["python", "-m", "mccabe", "--min", "10", str(f_path)],
                    capture_output=True, text=True, check=False
                )
                if res.stdout:
                    for line in res.stdout.splitlines():
                        parts = line.split(":")
                        if len(parts) >= 3:
                            comp_issues.append({
                                "file": f,
                                "line": parts[0],
                                "detail": parts[2].strip()
                            })
            except Exception:
                pass

        # Calculate Score
        # Simple heuristic: start at 100, deduct for issues
        score = 100
        score -= len(sec_issues) * 5
        score -= len(comp_issues) * 3
        score = max(0, score)

        summary = self._generate_summary(score, sec_issues, comp_issues)
        
        return AuditReport(
            score=score,
            security_issues=sec_issues,
            complexity_issues=comp_issues,
            summary=summary
        )

    def _generate_summary(self, score: int, sec: list, comp: list) -> str:
        if score == 100:
            return "Kod tertemiz! Güvenlik açığı veya aşırı karmaşıklık tespit edilmedi."
        
        parts = [f"Denetim Skoru: {score}/100."]
        if sec:
            parts.append(f"{len(sec)} adet potansiyel güvenlik uyarısı bulundu.")
        if comp:
            parts.append(f"{len(comp)} adet yüksek karmaşıklık uyarısı bulundu.")
            
        return " ".join(parts)

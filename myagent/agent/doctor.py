"""
Doctor module — diagnostic checks for system health.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
import importlib.util

from rich.text import Text
from myagent.ui import C_OK, C_WARN, C_ERR, C_DIM

def run_diagnostics() -> list[tuple[str, str, str]]:
    """Runs all health checks and returns a list of (category, status_icon, message)."""
    results = []
    
    # 1. Python Environment
    results.append(("System", *check_python()))
    results.append(("System", *check_venv()))
    
    # 2. API Keys
    results.extend([("API", *res) for res in check_api_keys()])
    
    # 3. CLI Tools
    results.extend([("Tools", *res) for res in check_cli_tools()])
    
    # 4. Core Packages
    results.extend([("Packages", *res) for res in check_packages()])
    
    # 5. Infrastructure
    results.append(("Infra", *check_docker()))
    
    return results

def check_python() -> tuple[str, str]:
    ver = sys.version_info
    v_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver.major >= 3 and ver.minor >= 10:
        return "✓", f"Python {v_str}"
    return "✗", f"Python {v_str} (3.10+ recommended)"

def check_venv() -> tuple[str, str]:
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return "✓", "Virtual environment (venv) active"
    return "!", "Virtual environment (venv) not active"

def check_api_keys() -> list[tuple[str, str]]:
    claude = os.environ.get("ANTHROPIC_API_KEY")
    gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    
    res = []
    if claude:
        res.append(("✓", f"Claude API Key: {claude[:8]}...{claude[-4:]}"))
    else:
        res.append(("!", "Claude API Key not found (not required in Claude Code mode)"))
        
    if gemini:
        res.append(("✓", f"Gemini API Key: {gemini[:8]}...{gemini[-4:]}"))
    else:
        res.append(("✗", "Gemini API Key not found (you can get it from Google AI Studio)"))
        
    return res

def check_cli_tools() -> list[tuple[str, str]]:
    tools = [
        ("claude", "Claude Code CLI"),
        ("gemini", "Gemini CLI"),
        ("ruff",   "Ruff Linter"),
        ("pytest", "Pytest"),
    ]
    res = []
    for cmd, name in tools:
        if shutil.which(cmd):
            res.append(("✓", f"{name} installed"))
        else:
            res.append(("!", f"{name} not found"))
    return res

def check_packages() -> list[tuple[str, str]]:
    pkgs = [
        ("textual", "Textual TUI"),
        ("rich", "Rich Terminal"),
        ("google.generativeai", "Gemini SDK"),
        ("anthropic", "Claude SDK"),
    ]
    res = []
    for mod_name, name in pkgs:
        spec = importlib.util.find_spec(mod_name)
        if spec:
            res.append(("✓", f"{name} package ready"))
        else:
            res.append(("✗", f"{name} package missing"))
    return res

def check_docker() -> tuple[str, str]:
    if shutil.which("docker"):
        try:
            subprocess.run(["docker", "ps"], capture_output=True, timeout=2)
            return "✓", "Docker running and accessible"
        except Exception:
            return "!", "Docker installed but not running"
    return "dim content", "Docker not found (required for Sandbox mode)"

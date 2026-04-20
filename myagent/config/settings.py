import os
from pathlib import Path

# API Keys — delegated to auth module for centralized management
from myagent.config.auth import ANTHROPIC_API_KEY, GEMINI_API_KEY

# Model identifiers
CLAUDE_MODEL: str = "claude-opus-4-6"
GEMINI_MODEL: str = "gemini-2.0-flash"

# Limits
MAX_STEPS: int = 10
BASH_TIMEOUT: int = 15

# Working directory
WORK_DIR: Path = Path(os.environ.get("MYAGENT_WORK_DIR", os.getcwd())).resolve()

# Prompts directory
PROMPTS_DIR: Path = Path(__file__).parent.parent / "prompts"


def validate() -> list[str]:
    """Return missing required config items."""
    from myagent.config.auth import API, get_claude_mode, get_gemini_mode

    missing: list[str] = []
    if get_claude_mode() == API and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if get_gemini_mode() == API and not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    return missing

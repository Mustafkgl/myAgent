"""
Model registry: curated model lists, alias resolution, and LIVE API discovery.
Automatically syncs with Anthropic and Google APIs to find the latest models.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
from myagent.utils.logger import log

@dataclass
class ModelInfo:
    id: str
    aliases: list[str]
    description: str
    provider: str           # "claude" | "gemini"
    is_recommended: bool = False


# ---------------------------------------------------------------------------
# Fallback Curated Models (Hardcoded defaults if API discovery fails)
# ---------------------------------------------------------------------------

CLAUDE_CURATED: list[ModelInfo] = [
    ModelInfo("claude-3-5-sonnet-20240620", ["sonnet", "3.5-sonnet"], "Balanced speed and intelligence", "claude", True),
    ModelInfo("claude-3-opus-20240229", ["opus", "3-opus"], "Most powerful for complex planning", "claude"),
    ModelInfo("claude-3-5-haiku-20241022", ["haiku", "3.5-haiku"], "Fast and inexpensive", "claude"),
]

GEMINI_CURATED: list[ModelInfo] = [
    ModelInfo("gemini-2.0-flash", ["flash", "2.0-flash"], "Latest generation, extremely fast", "gemini", True),
    ModelInfo("gemini-1.5-pro", ["pro", "1.5-pro"], "Best for complex reasoning tasks", "gemini"),
]

CLAUDE_DEFAULT = "claude-3-5-sonnet-20240620"
GEMINI_DEFAULT = "gemini-2.0-flash"

CONFIG_PATH = Path.home() / ".myagent" / "config.json"

# ---------------------------------------------------------------------------
# Helper: Load keys from config file if environment is empty
# ---------------------------------------------------------------------------

def _get_keys() -> tuple[str, str]:
    c_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    g_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
    
    if (not c_key or not g_key) and CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not c_key: c_key = data.get("anthropic_api_key", "").strip()
            if not g_key: g_key = data.get("gemini_api_key", "").strip()
        except Exception: pass
        
    return c_key, g_key


# ---------------------------------------------------------------------------
# Live Discovery
# ---------------------------------------------------------------------------

def fetch_all_models() -> list[ModelInfo]:
    """Fetch live models directly from APIs to ensure total sustainability."""
    log.info("Initiating Live Model Discovery (Direct API Sync)...")
    all_models: list[ModelInfo] = []
    c_key, g_key = _get_keys()
    
    # --- Live Claude Sync ---
    if c_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=c_key)
            for m in client.models.list().data:
                # Filter out older models or non-text models if needed
                all_models.append(ModelInfo(m.id, [], "(Direct API)", "claude"))
            log.info(f"Synced {len(all_models)} models from Anthropic.")
        except Exception as e:
            log.warning(f"Claude API Sync failed: {e}")
    
    # --- Live Gemini Sync ---
    if g_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=g_key)
            initial_count = len(all_models)
            for m in genai.list_models():
                if "generateContent" in getattr(m, "supported_generation_methods", []):
                    mid = m.name.replace("models/", "")
                    all_models.append(ModelInfo(mid, [], "(Direct API)", "gemini"))
            log.info(f"Synced {len(all_models) - initial_count} models from Google AI.")
        except Exception as e:
            log.warning(f"Gemini API Sync failed: {e}")

    # --- Deduplication and Fallback ---
    seen_ids = {m.id for m in all_models}
    
    # Add curated models if they were missed by API for some reason
    for fallback in CLAUDE_CURATED + GEMINI_CURATED:
        if fallback.id not in seen_ids:
            all_models.append(fallback)
            seen_ids.add(fallback.id)

    # Sort: Providers together, then alphabetical
    result = sorted(all_models, key=lambda x: (0 if x.provider == "claude" else 1, x.id))
    log.info(f"Sustainable Discovery Finished. Total models: {len(result)}")
    return result


def resolve_model(name: str, provider: str = "claude") -> str:
    """Resolve *name* to a full model ID."""
    curated = CLAUDE_CURATED if provider == "claude" else GEMINI_CURATED
    lower = name.lower().strip()
    for m in curated:
        if m.id.lower() == lower: return m.id
        if any(a.lower() == lower for a in m.aliases): return m.id
        if lower in m.id.lower(): return m.id
    return name

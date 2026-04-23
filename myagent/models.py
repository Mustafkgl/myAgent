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
# Dynamic Key Discovery: Search for keys in all possible formats
# ---------------------------------------------------------------------------

def _get_keys() -> tuple[str, str]:
    """Retrieves API keys from environment or config file with flexible naming."""
    # 1. Check Environment First (Priority)
    c_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    g_key = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")).strip()
    
    # 2. Check Config File (Fallback)
    if (not c_key or not g_key) and CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # Flexible searching: Check both upper and lower case variants
            if not c_key:
                c_key = (data.get("ANTHROPIC_API_KEY") or data.get("anthropic_api_key") or "").strip()
            if not g_key:
                g_key = (data.get("GEMINI_API_KEY") or data.get("gemini_api_key") or 
                         data.get("GOOGLE_API_KEY") or data.get("google_api_key") or "").strip()
        except Exception as e:
            log.warning(f"Failed to parse config.json for keys: {e}")
        
    return c_key, g_key


# ---------------------------------------------------------------------------
# Live Discovery: Real-time synchronization with AI providers
# ---------------------------------------------------------------------------

def fetch_all_models() -> list[ModelInfo]:
    """Fetch live models directly from APIs to ensure total sustainability."""
    log.info("Initiating Sustainable Live Model Discovery...")
    all_models: list[ModelInfo] = []
    c_key, g_key = _get_keys()
    
    # --- Live Anthropic Sync ---
    if c_key:
        try:
            log.debug("Connecting to Anthropic for model sync...")
            import anthropic
            client = anthropic.Anthropic(api_key=c_key)
            for m in client.models.list().data:
                # Add all discovered text models
                all_models.append(ModelInfo(m.id, [], "(Direct API)", "claude"))
            log.info(f"Successfully synced {len([m for m in all_models if m.provider == 'claude'])} models from Anthropic.")
        except Exception as e:
            log.warning(f"Anthropic Direct Sync failed: {e}")
    
    # --- Live Google AI Sync ---
    if g_key:
        try:
            log.debug("Connecting to Google AI for model sync...")
            import google.generativeai as genai
            genai.configure(api_key=g_key)
            g_count = 0
            for m in genai.list_models():
                if "generateContent" in getattr(m, "supported_generation_methods", []):
                    mid = m.name.replace("models/", "")
                    all_models.append(ModelInfo(mid, [], "(Direct API)", "gemini"))
                    g_count += 1
            log.info(f"Successfully synced {g_count} models from Google AI.")
        except Exception as e:
            log.warning(f"Gemini Direct Sync failed: {e}")

    # --- Robust Deduplication & Fallback Logic ---
    seen_ids = {m.id for m in all_models}
    
    # Always ensure our high-priority curated models exist (Safety Net)
    for fallback in CLAUDE_CURATED + GEMINI_CURATED:
        if fallback.id not in seen_ids:
            all_models.append(fallback)
            seen_ids.add(fallback.id)

    # Sort: Providers grouped together, then alphabetical order
    result = sorted(all_models, key=lambda x: (0 if x.provider == "claude" else 1, x.id))
    log.info(f"Dynamic Discovery complete. Total sustainable models: {len(result)}")
    return result


def resolve_model(name: str, provider: str = "claude") -> str:
    """Universal model ID resolver with alias support."""
    curated = CLAUDE_CURATED if provider == "claude" else GEMINI_CURATED
    lower = name.lower().strip()
    for m in curated:
        if m.id.lower() == lower: return m.id
        if any(a.lower() == lower for a in m.aliases): return m.id
        if lower in m.id.lower(): return m.id
    return name

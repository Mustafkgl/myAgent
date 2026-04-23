"""
Model registry: curated model lists, alias resolution, and LIVE API discovery.
"""

from __future__ import annotations

import os
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
    ModelInfo("gemini-1.5-flash", ["1.5-flash"], "High throughput, low latency", "gemini"),
]

CLAUDE_DEFAULT = "claude-3-5-sonnet-20240620"
GEMINI_DEFAULT = "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Live Discovery
# ---------------------------------------------------------------------------

def fetch_all_models() -> list[ModelInfo]:
    """Fetch live models from both Anthropic and Google APIs with detailed logging."""
    log.info("Starting live model discovery...")
    all_models: list[ModelInfo] = []
    
    # --- Try Claude API ---
    api_key_c = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key_c:
        try:
            log.debug("Fetching models from Anthropic API...")
            import anthropic
            client = anthropic.Anthropic(api_key=api_key_c)
            for m in client.models.list().data:
                all_models.append(ModelInfo(m.id, [], "(API)", "claude"))
            log.info(f"Successfully fetched {len(all_models)} models from Anthropic.")
        except Exception as e:
            log.warning(f"Anthropic API discovery failed: {str(e)}")
    else:
        log.debug("ANTHROPIC_API_KEY not found in environment.")

    # --- Try Gemini API ---
    api_key_g = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
    if api_key_g:
        try:
            log.debug("Fetching models from Google AI API...")
            import google.generativeai as genai
            genai.configure(api_key=api_key_g)
            g_count = 0
            for m in genai.list_models():
                if "generateContent" in getattr(m, "supported_generation_methods", []):
                    mid = m.name.replace("models/", "")
                    all_models.append(ModelInfo(mid, [], "(API)", "gemini"))
                    g_count += 1
            log.info(f"Successfully fetched {g_count} models from Google AI.")
        except Exception as e:
            log.warning(f"Google AI API discovery failed: {str(e)}")
    else:
        log.debug("GEMINI_API_KEY/GOOGLE_API_KEY not found in environment.")

    # --- Fallback/Safety Layer ---
    # Ensure our curated models are ALWAYS present even if API fails or returns partial list
    seen_ids = {m.id for m in all_models}
    
    for cm in CLAUDE_CURATED:
        if cm.id not in seen_ids:
            all_models.append(cm)
            seen_ids.add(cm.id)
            
    for gm in GEMINI_CURATED:
        if gm.id not in seen_ids:
            all_models.append(gm)
            seen_ids.add(gm.id)

    # --- Final Polish ---
    # Sort by provider (claude first for style) then by id
    result = sorted(all_models, key=lambda x: (0 if x.provider == "claude" else 1, x.id))
    log.info(f"Model discovery complete. Total unique models: {len(result)}")
    return result


def resolve_model(name: str, provider: str = "claude") -> str:
    """Resolve *name* to a full model ID for *provider*."""
    curated = CLAUDE_CURATED if provider == "claude" else GEMINI_CURATED
    lower = name.lower().strip()
    for m in curated:
        if m.id.lower() == lower: return m.id
        if any(a.lower() == lower for a in m.aliases): return m.id
        if lower in m.id.lower(): return m.id
    return name

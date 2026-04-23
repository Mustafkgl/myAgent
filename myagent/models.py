"""
Model registry: curated model lists, alias resolution, and LIVE API discovery.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ModelInfo:
    id: str
    aliases: list[str]
    description: str
    provider: str           # "claude" | "gemini"
    is_recommended: bool = False


# ---------------------------------------------------------------------------
# Fallback Curated Models (When API discovery fails)
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


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

CLAUDE_DEFAULT = "claude-3-5-sonnet-20240620"
GEMINI_DEFAULT = "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Live Discovery
# ---------------------------------------------------------------------------

def fetch_all_models() -> list[ModelInfo]:
    """Fetch live models from both Anthropic and Google APIs."""
    all_models = []
    
    # Try Claude API
    api_key_c = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key_c:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key_c)
            # Fetch and wrap
            for m in client.models.list().data:
                all_models.append(ModelInfo(m.id, [], "(Direct from API)", "claude"))
        except Exception: pass
    
    if not any(m.provider == "claude" for m in all_models):
        all_models.extend(CLAUDE_CURATED)

    # Try Gemini API
    api_key_g = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
    if api_key_g:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key_g)
            for m in genai.list_models():
                if "generateContent" in getattr(m, "supported_generation_methods", []):
                    mid = m.name.replace("models/", "")
                    all_models.append(ModelInfo(mid, [], "(Direct from API)", "gemini"))
        except Exception: pass

    if not any(m.provider == "gemini" for m in all_models):
        all_models.extend(GEMINI_CURATED)

    # Remove duplicates by ID
    unique = {}
    for m in all_models:
        unique[m.id] = m
    
    return sorted(list(unique.values()), key=lambda x: (x.provider, x.id))


def resolve_model(name: str, provider: str = "claude") -> str:
    """Resolve *name* to a full model ID for *provider*.
    If it's an exact match for an existing ID, return it.
    If it's an alias, return the full ID.
    Otherwise, return the name as-is.
    """
    curated = CLAUDE_CURATED if provider == "claude" else GEMINI_CURATED
    lower = name.lower().strip()
    
    # 1. Exact ID match
    for m in curated:
        if m.id.lower() == lower: return m.id
    
    # 2. Alias match
    for m in curated:
        if any(a.lower() == lower for a in m.aliases): return m.id
    
    # 3. Substring match
    for m in curated:
        if lower in m.id.lower(): return m.id
        
    return name

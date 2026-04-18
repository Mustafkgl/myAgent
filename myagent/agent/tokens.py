"""Token tracking — accumulates Claude + Gemini usage across the session."""
from __future__ import annotations

from dataclasses import dataclass, field

# Pricing: (input_per_MTok, output_per_MTok) USD
_CLAUDE_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":           (15.0,  75.0),
    "claude-sonnet-4-6":         (3.0,   15.0),
    "claude-haiku-4-5":          (0.80,   4.0),
    "claude-haiku-4-5-20251001": (0.80,   4.0),
}
_CLAUDE_DEFAULT = (3.0, 15.0)

_GEMINI_PRICES: dict[str, tuple[float, float]] = {
    "gemini-2.5-pro":   (1.25,  5.0),
    "gemini-2.5-flash": (0.15,  0.60),
    "gemini-2.0-flash": (0.10,  0.40),
    "gemini-1.5-pro":   (1.25,  5.0),
    "gemini-1.5-flash": (0.075, 0.30),
}
_GEMINI_DEFAULT = (0.15, 0.60)


def _claude_price(model: str) -> tuple[float, float]:
    for k, v in _CLAUDE_PRICES.items():
        if k in model:
            return v
    return _CLAUDE_DEFAULT


def _gemini_price(model: str) -> tuple[float, float]:
    for k, v in _GEMINI_PRICES.items():
        if k in model:
            return v
    return _GEMINI_DEFAULT


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    has_estimates: bool = False


@dataclass
class TokenTracker:
    claude: _Usage = field(default_factory=_Usage)
    gemini: _Usage = field(default_factory=_Usage)
    tasks_total: int = 0
    tasks_first_pass: int = 0
    _claude_model: str = ""
    _gemini_model: str = ""

    def reset(self) -> None:
        self.claude = _Usage()
        self.gemini = _Usage()
        self.tasks_total = 0
        self.tasks_first_pass = 0
        self._claude_model = ""
        self._gemini_model = ""

    def add_claude(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "",
        estimated: bool = False,
    ) -> None:
        self.claude.input_tokens += input_tokens
        self.claude.output_tokens += output_tokens
        if model:
            self._claude_model = model
        if estimated:
            self.claude.has_estimates = True

    def add_gemini(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "",
        estimated: bool = False,
    ) -> None:
        self.gemini.input_tokens += input_tokens
        self.gemini.output_tokens += output_tokens
        if model:
            self._gemini_model = model
        if estimated:
            self.gemini.has_estimates = True

    def record_task(self, first_pass: bool) -> None:
        self.tasks_total += 1
        if first_pass:
            self.tasks_first_pass += 1

    # ── Cost helpers ──────────────────────────────────────────────────────────

    def claude_cost(self) -> float:
        p = _claude_price(self._claude_model)
        return (self.claude.input_tokens * p[0] + self.claude.output_tokens * p[1]) / 1_000_000

    def gemini_cost(self) -> float:
        p = _gemini_price(self._gemini_model)
        return (self.gemini.input_tokens * p[0] + self.gemini.output_tokens * p[1]) / 1_000_000

    def hypothetical_cost(self) -> float:
        """What would it cost if all tokens (Claude + Gemini) were billed at Claude's rate?"""
        p = _claude_price(self._claude_model)
        total_in  = self.claude.input_tokens  + self.gemini.input_tokens
        total_out = self.claude.output_tokens + self.gemini.output_tokens
        return (total_in * p[0] + total_out * p[1]) / 1_000_000

    def savings(self) -> float:
        return self.hypothetical_cost() - self.claude_cost() - self.gemini_cost()

    def savings_pct(self) -> float:
        hyp = self.hypothetical_cost()
        return (self.savings() / hyp * 100) if hyp > 0 else 0.0

    def first_pass_rate(self) -> float:
        return (self.tasks_first_pass / self.tasks_total * 100) if self.tasks_total > 0 else 0.0

    def has_data(self) -> bool:
        return (
            self.claude.input_tokens > 0
            or self.claude.output_tokens > 0
            or self.gemini.input_tokens > 0
            or self.gemini.output_tokens > 0
        )


# Module-level singleton — import and use directly everywhere
tracker = TokenTracker()

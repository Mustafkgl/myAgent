"""Tests for TokenTracker (myagent/agent/tokens.py)."""
import pytest
from myagent.agent.tokens import TokenTracker, _claude_price, _gemini_price


# ---------------------------------------------------------------------------
# Price lookup
# ---------------------------------------------------------------------------

def test_claude_price_known_model():
    p = _claude_price("claude-sonnet-4-6")
    assert p == (3.0, 15.0)

def test_claude_price_opus():
    p = _claude_price("claude-opus-4-7")
    assert p == (15.0, 75.0)

def test_claude_price_haiku():
    p = _claude_price("claude-haiku-4-5-20251001")
    assert p == (0.80, 4.0)

def test_claude_price_unknown_falls_back_to_sonnet():
    p = _claude_price("claude-unknown-model")
    assert p == (3.0, 15.0)

def test_gemini_price_flash():
    p = _gemini_price("gemini-2.5-flash")
    assert p == (0.15, 0.60)

def test_gemini_price_pro():
    p = _gemini_price("gemini-2.5-pro")
    assert p == (1.25, 5.0)

def test_gemini_price_unknown_falls_back_to_flash():
    p = _gemini_price("gemini-unknown")
    assert p == (0.15, 0.60)


# ---------------------------------------------------------------------------
# TokenTracker — basic accumulation
# ---------------------------------------------------------------------------

def test_add_claude_accumulates():
    t = TokenTracker()
    t.add_claude(100, 50, "claude-sonnet-4-6")
    t.add_claude(200, 75, "claude-sonnet-4-6")
    assert t.claude.input_tokens == 300
    assert t.claude.output_tokens == 125

def test_add_gemini_accumulates():
    t = TokenTracker()
    t.add_gemini(1000, 500, "gemini-2.5-flash")
    t.add_gemini(500, 250, "gemini-2.5-flash")
    assert t.gemini.input_tokens == 1500
    assert t.gemini.output_tokens == 750

def test_model_name_is_stored():
    t = TokenTracker()
    t.add_claude(10, 10, "claude-opus-4-7")
    assert t._claude_model == "claude-opus-4-7"
    t.add_gemini(10, 10, "gemini-2.5-pro")
    assert t._gemini_model == "gemini-2.5-pro"

def test_estimated_flag_set_only_when_true():
    t = TokenTracker()
    t.add_claude(10, 10, estimated=False)
    assert not t.claude.has_estimates
    t.add_claude(10, 10, estimated=True)
    assert t.claude.has_estimates

def test_has_data_false_when_empty():
    t = TokenTracker()
    assert not t.has_data()

def test_has_data_true_after_add():
    t = TokenTracker()
    t.add_claude(1, 0)
    assert t.has_data()


# ---------------------------------------------------------------------------
# TokenTracker — cost calculations
# ---------------------------------------------------------------------------

def test_claude_cost_exact():
    t = TokenTracker()
    # claude-sonnet-4-6: $3/MTok in, $15/MTok out
    t.add_claude(1_000_000, 0, "claude-sonnet-4-6")
    assert abs(t.claude_cost() - 3.0) < 1e-9

def test_gemini_cost_exact():
    t = TokenTracker()
    # gemini-2.5-flash: $0.15/MTok in, $0.60/MTok out
    t.add_gemini(1_000_000, 0, "gemini-2.5-flash")
    assert abs(t.gemini_cost() - 0.15) < 1e-9

def test_hypothetical_cost_uses_claude_price_for_all_tokens():
    t = TokenTracker()
    t.add_claude(500_000, 0, "claude-sonnet-4-6")
    t.add_gemini(500_000, 0, "gemini-2.5-flash")
    # Hypothetical: 1M input at $3/MTok = $3.0
    assert abs(t.hypothetical_cost() - 3.0) < 1e-9

def test_savings_is_positive_when_gemini_cheaper():
    t = TokenTracker()
    t.add_claude(100_000, 50_000, "claude-sonnet-4-6")
    t.add_gemini(900_000, 450_000, "gemini-2.5-flash")
    assert t.savings() > 0

def test_savings_pct_range():
    t = TokenTracker()
    t.add_claude(100_000, 50_000, "claude-sonnet-4-6")
    t.add_gemini(900_000, 450_000, "gemini-2.5-flash")
    pct = t.savings_pct()
    assert 0 < pct < 100

def test_savings_zero_when_no_gemini_tokens():
    t = TokenTracker()
    t.add_claude(1_000_000, 0, "claude-sonnet-4-6")
    # No Gemini tokens → hypothetical == actual claude cost → savings = 0
    assert abs(t.savings()) < 1e-9

def test_no_data_costs_are_zero():
    t = TokenTracker()
    assert t.claude_cost() == 0.0
    assert t.gemini_cost() == 0.0
    assert t.hypothetical_cost() == 0.0
    assert t.savings() == 0.0
    assert t.savings_pct() == 0.0


# ---------------------------------------------------------------------------
# TokenTracker — first-pass rate
# ---------------------------------------------------------------------------

def test_first_pass_rate_zero_tasks():
    t = TokenTracker()
    assert t.first_pass_rate() == 0.0

def test_first_pass_rate_all_first_pass():
    t = TokenTracker()
    t.record_task(first_pass=True)
    t.record_task(first_pass=True)
    assert t.first_pass_rate() == 100.0

def test_first_pass_rate_none_first_pass():
    t = TokenTracker()
    t.record_task(first_pass=False)
    t.record_task(first_pass=False)
    assert t.first_pass_rate() == 0.0

def test_first_pass_rate_mixed():
    t = TokenTracker()
    t.record_task(first_pass=True)
    t.record_task(first_pass=False)
    t.record_task(first_pass=True)
    assert abs(t.first_pass_rate() - 200/3) < 0.01

def test_task_total_counter():
    t = TokenTracker()
    t.record_task(True)
    t.record_task(False)
    assert t.tasks_total == 2
    assert t.tasks_first_pass == 1


# ---------------------------------------------------------------------------
# TokenTracker — reset
# ---------------------------------------------------------------------------

def test_reset_clears_everything():
    t = TokenTracker()
    t.add_claude(999, 888, "claude-opus-4-7", estimated=True)
    t.add_gemini(777, 666, "gemini-2.5-pro", estimated=True)
    t.record_task(True)
    t.record_task(False)

    t.reset()

    assert t.claude.input_tokens == 0
    assert t.claude.output_tokens == 0
    assert t.gemini.input_tokens == 0
    assert t.gemini.output_tokens == 0
    assert not t.claude.has_estimates
    assert not t.gemini.has_estimates
    assert t.tasks_total == 0
    assert t.tasks_first_pass == 0
    assert not t.has_data()


# ---------------------------------------------------------------------------
# Realistic session simulation
# ---------------------------------------------------------------------------

def test_realistic_session():
    """Simulate a session: planner (Claude) + worker (Gemini) + reviewer (Claude)."""
    t = TokenTracker()

    # Planner call
    t.add_claude(800, 150, "claude-sonnet-4-6")
    # Worker call (Gemini batch)
    t.add_gemini(2500, 1200, "gemini-2.5-flash")
    # Reviewer (ruff clean, no Claude call needed)
    # Completer call
    t.add_claude(300, 30, "claude-sonnet-4-6")
    t.record_task(first_pass=True)

    assert t.claude.input_tokens == 1100
    assert t.claude.output_tokens == 180
    assert t.gemini.input_tokens == 2500
    assert t.gemini.output_tokens == 1200

    # Cost sanity: Claude sonnet + Gemini flash should be very cheap for small session
    total = t.claude_cost() + t.gemini_cost()
    assert total < 0.01  # well under 1 cent

    # Savings should be positive (Gemini far cheaper than Claude for same tokens)
    assert t.savings() > 0
    assert t.savings_pct() > 50  # substantial saving expected
    assert t.first_pass_rate() == 100.0

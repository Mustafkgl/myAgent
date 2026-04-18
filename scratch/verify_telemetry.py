
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from myagent.agent.pipeline import RunResult, StepRecord
from myagent.models import get_model_cost

def test_telemetry_aggregation():
    print("Testing Telemetry Aggregation...")
    
    # Create a RunResult
    result = RunResult(task_english="Test Task")
    
    # Mock some usage updates
    def update_usage(prov, u):
        if not u: return
        result.usage[prov]["input"] += u.get("input", 0)
        result.usage[prov]["output"] += u.get("output", 0)
        
    update_usage("claude", {"input": 1000, "output": 500})
    update_usage("gemini", {"input": 5000, "output": 2000})
    update_usage("claude", {"input": 200, "output": 100}) # Review round
    
    print(f"Aggregated Usage: {result.usage}")
    
    assert result.usage["claude"]["input"] == 1200
    assert result.usage["claude"]["output"] == 600
    assert result.usage["gemini"]["input"] == 5000
    assert result.usage["gemini"]["output"] == 2000
    
    # Test cost calculation
    c_cost = get_model_cost("claude-opus-4-6", "claude", result.usage["claude"]["input"], result.usage["claude"]["output"])
    g_cost = get_model_cost("gemini-2.5-flash", "gemini", result.usage["gemini"]["input"], result.usage["gemini"]["output"])
    
    print(f"Claude Cost: ${c_cost:.4f}")
    print(f"Gemini Cost: ${g_cost:.4f}")
    print(f"Total Cost: ${c_cost + g_cost:.4f}")
    
    # Expected: 
    # Claude (Opus): (1200 * 15 / 1M) + (600 * 75 / 1M) = 0.018 + 0.045 = 0.063
    # Gemini (Flash): (5000 * 0.1 / 1M) + (2000 * 0.4 / 1M) = 0.0005 + 0.0008 = 0.0013
    
    assert abs(c_cost - 0.063) < 0.0001
    assert abs(g_cost - 0.0013) < 0.0001
    
    print("✓ Telemetry aggregation and cost calculation verified.")

if __name__ == "__main__":
    try:
        test_telemetry_aggregation()
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        sys.exit(1)

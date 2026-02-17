"""
Omnigent — Few-Shot Examples System

Provides concrete examples for each tool to improve LLM tool accuracy.
2-3 examples per tool (2 good + 1 anti-pattern).

Architecture:
  EXAMPLES is a dict of {tool_name: [ToolExample, ...]}.
  Domain implementations populate this with their own examples.

Example (security domain):
  EXAMPLES["nmap"] = [
      ToolExample(
          scenario="What services are running?",
          thinking="Need service detection scan...",
          tool_name="nmap",
          tool_args={"target": "10.0.0.5", "scan_type": "service"},
          expected_result="22/tcp ssh, 80/tcp http",
          is_good=True,
      ),
  ]
"""

from dataclasses import dataclass


@dataclass
class ToolExample:
    """A single few-shot example for a tool."""
    scenario: str      # User request context
    thinking: str      # Chain-of-thought reasoning
    tool_name: str
    tool_args: dict
    expected_result: str
    is_good: bool      # True = good example, False = anti-pattern


# ═══════════════════════════════════════════════════════════════════════════
# Examples Registry — populate in your domain implementation
# ═══════════════════════════════════════════════════════════════════════════

# Structure:
#   {
#       "tool_name": [ToolExample(...), ...],
#   }

EXAMPLES: dict[str, list[ToolExample]] = {}


# ═══════════════════════════════════════════════════════════════════════════
# Core API
# ═══════════════════════════════════════════════════════════════════════════


def get_examples(tool_name: str) -> list[ToolExample]:
    """Get few-shot examples for a tool."""
    return EXAMPLES.get(tool_name, [])




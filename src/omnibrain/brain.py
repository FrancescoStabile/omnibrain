"""
OmniBrain — Agent (Omnigent Agent Subclass)

The OmniBrain agent — personal AI with proactive capabilities.

Subclasses Omnigent's Agent with:
    - OmniBrainProfile as structured memory
    - OmniBrainGraph as reasoning graph
    - Personal system prompt with dynamic context
    - Domain-specific failure detection
    - Finding → Observation pipeline

Follows manifesto Section 7: OmnibrainAgent specification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from omnibrain.graph import OmniBrainGraph
from omnibrain.models import Observation
from omnibrain.profile import OmniBrainProfile
from omnigent.agent import Agent
from omnigent.registry import DomainRegistry

logger = logging.getLogger("omnibrain.agent")


class OmniBrainAgent(Agent):
    """The OmniBrain agent — personal AI with proactive capabilities.

    Extends Omnigent's Agent with:
    - OmniBrainProfile: Personal knowledge about the user
    - OmniBrainGraph: 5 reasoning chains (email, meeting, code, pattern, financial)
    - Personal system prompt with safety constraints
    - Domain-specific failure detection (rate limits, auth errors)
    - Finding → Observation pipeline (auto-record insights)

    Usage:
        profile = OmniBrainProfile(user_name="Francesco", user_email="f@omnibrain.dev")
        agent = OmniBrainAgent(user_profile=profile)
        async for event in agent.run("Triage my inbox"):
            print(event)
    """

    def __init__(
        self,
        user_profile: OmniBrainProfile | None = None,
        graph: OmniBrainGraph | None = None,
        registry: DomainRegistry | None = None,
        **kwargs: Any,
    ):
        """Initialize OmniBrainAgent.

        Args:
            user_profile: The user's profile (or creates a default one).
            graph: The reasoning graph (or creates OmniBrainGraph).
            registry: Domain registry with OmniBrain extractors/chains.
            **kwargs: Additional Agent keyword arguments (router, tools, etc.)
        """
        _graph = graph or OmniBrainGraph()
        _registry = registry or self._build_default_registry()

        super().__init__(
            reasoning_graph=_graph,
            registry=_registry,
            **kwargs,
        )

        # Override the state profile with OmniBrainProfile
        self.state.profile = user_profile or OmniBrainProfile()

        # Load OmniBrain-specific system prompt
        self._omnibrain_system_prompt = self._load_omnibrain_prompt()

    @property
    def profile(self) -> OmniBrainProfile:
        """Typed access to the OmniBrain profile."""
        return self.state.profile  # type: ignore[return-value]

    # ── System Prompt ──

    def _build_dynamic_system_prompt(self) -> str:
        """Extended prompt with personal context.

        Layers:
        1. Omnigent base prompt (plan, graph, chains, knowledge)
        2. OmniBrain personal context (profile, calendar, email stats)
        3. Safety constraints and role definition
        """
        base = super()._build_dynamic_system_prompt()

        # Personal context from profile
        profile_ctx = ""
        if isinstance(self.state.profile, OmniBrainProfile):
            profile_ctx = self.state.profile.to_prompt_summary()

        # Role definition and safety constraints
        user_name = getattr(self.state.profile, "user_name", "the user")
        personal = f"""
## Your Role
You are OmniBrain, a personal AI assistant for {user_name}.
You are proactive, concise, and action-oriented.
You PROPOSE actions but NEVER execute without approval (unless pre-approved).

## Critical Rules
1. Never impersonate the user to third parties
2. All outgoing messages must be clearly from OmniBrain on behalf of user
3. When uncertain, ASK rather than act
4. Protect user privacy — never share personal info with third parties
5. Be honest about limitations — say "I don't know" when you don't
"""

        parts = [base]
        if profile_ctx:
            parts.append("\n\n---\n\n" + profile_ctx)
        parts.append("\n\n---\n\n" + personal)

        return "\n".join(parts)

    def _load_omnibrain_prompt(self) -> str:
        """Load OmniBrain system prompt from prompts/system.md."""
        prompt_file = Path(__file__).parent / "prompts" / "system.md"
        if prompt_file.exists():
            return prompt_file.read_text()
        return ""

    # ── Failure Detection ──

    def _is_failure(self, tool_name: str, result: str) -> bool:
        """OmniBrain-specific failure detection.

        Checks for:
        - Rate limit errors
        - Authentication failures
        - Empty/missing results
        - Google API-specific errors
        """
        result_lower = result.lower()

        # Rate limiting
        if "rate_limit" in result_lower or "rate limit" in result_lower:
            logger.warning(f"Rate limit detected for tool {tool_name}")
            return True

        # Auth failures
        if "authentication" in result_lower and "failed" in result_lower:
            logger.warning(f"Auth failure for tool {tool_name}")
            return True

        # Google-specific
        if "invalid_grant" in result_lower or "token expired" in result_lower:
            logger.warning(f"Google token error for tool {tool_name}")
            return True

        # Delegation to parent
        return super()._is_failure(tool_name, result)

    # ── Finding Pipeline ──

    def _on_finding(self, title: str, severity: str, description: str, evidence: str) -> None:
        """When OmniBrain discovers something notable.

        Converts findings into Observations stored on the profile.
        These feed the pattern detection and proactive engine.
        """
        if isinstance(self.state.profile, OmniBrainProfile):
            self.state.profile.add_observation(
                Observation(
                    type=title,
                    detail=description,
                    evidence=evidence,
                    confidence=_severity_to_confidence(severity),
                )
            )
            logger.info(f"OmniBrain finding → observation: {title} ({severity})")

    # ── Registry ──

    @staticmethod
    def _build_default_registry() -> DomainRegistry:
        """Build a DomainRegistry pre-populated with OmniBrain extractors and configs.

        Uses the EXTRACTORS from omnibrain.extractors module and adds
        OmniBrain-specific plan templates, tool timeouts, etc.
        """
        from omnibrain.extractors import EXTRACTORS

        return DomainRegistry(
            extractors=EXTRACTORS,
            plan_templates=_get_plan_templates(),
            tool_timeouts=_get_tool_timeouts(),
            error_patterns=_get_error_patterns(),
        )


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrain-Specific Registries
# ═══════════════════════════════════════════════════════════════════════════


def _severity_to_confidence(severity: str) -> float:
    """Map severity to confidence score."""
    return {
        "critical": 0.95,
        "high": 0.8,
        "medium": 0.6,
        "low": 0.4,
        "info": 0.3,
    }.get(severity.lower(), 0.5)


def _get_plan_templates() -> dict[str, list[dict]]:
    """OmniBrain plan templates for common tasks."""
    return {
        "email_triage": [
            {
                "name": "Email Triage",
                "objective": "Triage inbox emails by urgency and propose responses",
                "steps": [
                    {"action": "fetch_emails", "description": "Fetch recent unread emails"},
                    {"action": "classify_email", "description": "Classify each email by urgency"},
                    {"action": "draft_email", "description": "Draft responses for urgent emails"},
                    {"action": "submit_analysis", "description": "Present triage results to user"},
                ],
            }
        ],
        "morning_briefing": [
            {
                "name": "Morning Briefing",
                "objective": "Generate comprehensive morning briefing",
                "steps": [
                    {"action": "get_today_events", "description": "Fetch today's calendar"},
                    {"action": "fetch_emails", "description": "Fetch overnight emails"},
                    {"action": "search_memory", "description": "Check for pending tasks and patterns"},
                    {"action": "submit_analysis", "description": "Compile and deliver briefing"},
                ],
            }
        ],
        "meeting_prep": [
            {
                "name": "Meeting Preparation",
                "objective": "Prepare briefing for upcoming meeting",
                "steps": [
                    {"action": "generate_meeting_brief", "description": "Generate meeting brief with attendee context"},
                    {"action": "search_memory", "description": "Find related past conversations"},
                    {"action": "submit_analysis", "description": "Deliver meeting preparation"},
                ],
            }
        ],
    }


def _get_tool_timeouts() -> dict[str, int]:
    """Per-tool timeout values (seconds)."""
    return {
        "fetch_emails": 30,
        "search_emails": 30,
        "classify_email": 10,
        "get_today_events": 20,
        "get_upcoming_events": 20,
        "generate_meeting_brief": 20,
        "search_memory": 15,
        "store_observation": 5,
        "draft_email": 60,
        "send_email": 30,
    }


def _get_error_patterns() -> dict[str, dict]:
    """Error patterns for OmniBrain tools.

    Maps tool names to patterns with indicators and recovery strategies.
    """
    return {
        "fetch_emails": {
            "auth_expired": {
                "indicators": ["invalid_grant", "token expired", "401"],
                "strategy": "Re-authenticate with Google. Suggest user run 'omnibrain setup-google'.",
            },
            "rate_limit": {
                "indicators": ["rate_limit", "quota exceeded", "429"],
                "strategy": "Back off for 60 seconds, then retry with smaller batch.",
            },
        },
        "get_today_events": {
            "auth_expired": {
                "indicators": ["invalid_grant", "token expired", "401"],
                "strategy": "Re-authenticate with Google. Suggest user run 'omnibrain setup-google'.",
            },
        },
        "draft_email": {
            "context_too_long": {
                "indicators": ["context length", "token limit", "max_tokens"],
                "strategy": "Truncate email body and retry with shorter context.",
            },
        },
    }

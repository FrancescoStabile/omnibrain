"""
OmniBrain — Reasoning Graph (ReasoningGraph Subclass)

Personal reasoning graph — chains context observations into actionable insights.

Defines 5 reasoning chains per manifesto Section 7:
    1. Email → Response (classify → contextualize → draft)
    2. Meeting Prep (detect → gather context → brief)
    3. Issue → Fix (report → analyze → propose fix)
    4. Pattern Detection (observe → confirm → automate)
    5. Financial Intelligence (detect → anomaly → saving)

Each chain has registered nodes, edges, and named paths that guide
the agent's multi-step reasoning. When a node is marked as confirmed,
downstream paths become available automatically.
"""

from __future__ import annotations

from omnigent.reasoning_graph import ReasoningGraph


class OmniBrainGraph(ReasoningGraph):
    """Personal reasoning graph — chains context into actionable insights.

    Override of Omnigent's ReasoningGraph._build_default_graph() to
    pre-populate with OmniBrain's 5 reasoning chains plus aliases
    for fuzzy matching.
    """

    def _build_default_graph(self) -> None:
        """Build the default OmniBrain reasoning graph.

        Called automatically by ReasoningGraph.__init__().
        """
        self._build_email_chain()
        self._build_meeting_chain()
        self._build_code_chain()
        self._build_pattern_chain()
        self._build_financial_chain()
        self._build_aliases()

    # ── Chain 1: Email Intelligence ──

    def _build_email_chain(self) -> None:
        """Email → Response: classify → contextualize → draft."""

        self.register_node("email_received", "email_received", "New Email Received")
        self.register_node("email_urgent", "email_urgent", "Urgent Email Detected")
        self.register_node("email_context", "email_context", "Email Context Retrieved")
        self.register_node("response_drafted", "response_drafted", "Response Draft Ready")
        self.register_node("response_approved", "response_approved", "Response Sent")

        self.register_edge(
            "email_received", "email_urgent", "urgency_classification",
            "Classify email urgency based on sender, subject, content",
            tool_hint="classify_email",
        )
        self.register_edge(
            "email_urgent", "email_context", "context_retrieval",
            "Retrieve past conversations and context with this sender",
            tool_hint="search_memory",
        )
        self.register_edge(
            "email_context", "response_drafted", "draft_response",
            "Draft a response using context and user's writing style",
            tool_hint="draft_email",
        )

        self.register_path(
            "Email → Response",
            ["email_received", "email_urgent", "email_context", "response_drafted"],
            impact="high",
            description="Full email processing: classify → contextualize → draft",
        )

    # ── Chain 2: Meeting Preparation ──

    def _build_meeting_chain(self) -> None:
        """Meeting Prep: detect → gather context → brief."""

        self.register_node("meeting_upcoming", "meeting_upcoming", "Meeting Approaching")
        self.register_node("meeting_context", "meeting_context", "Meeting Context Gathered")
        self.register_node("meeting_brief", "meeting_brief", "Meeting Brief Ready")

        self.register_edge(
            "meeting_upcoming", "meeting_context", "gather_context",
            "Find all related emails, docs, and past meetings with attendees",
            tool_hint="search_memory",
        )
        self.register_edge(
            "meeting_context", "meeting_brief", "generate_brief",
            "Generate concise briefing document",
            tool_hint="generate_meeting_brief",
        )

        self.register_path(
            "Meeting Prep",
            ["meeting_upcoming", "meeting_context", "meeting_brief"],
            impact="high",
            description="Auto-prepare meeting briefs from context",
        )

    # ── Chain 3: Code Intelligence (for developers) ──

    def _build_code_chain(self) -> None:
        """Issue → Fix: report → analyze → propose fix."""

        self.register_node("issue_reported", "issue_reported", "Issue Reported")
        self.register_node("code_analyzed", "code_analyzed", "Code Analyzed")
        self.register_node("fix_proposed", "fix_proposed", "Fix Proposed")

        self.register_edge(
            "issue_reported", "code_analyzed", "analyze_code",
            "Analyze codebase for root cause",
            tool_hint="analyze_github_issue",
        )
        self.register_edge(
            "code_analyzed", "fix_proposed", "propose_fix",
            "Generate fix based on analysis",
            tool_hint="propose_code_fix",
        )

        self.register_path(
            "Issue → Fix",
            ["issue_reported", "code_analyzed", "fix_proposed"],
            impact="high",
            description="Automated issue analysis and fix proposal",
        )

    # ── Chain 4: Pattern Detection ──

    def _build_pattern_chain(self) -> None:
        """Pattern Detection: observe → confirm → automate."""

        self.register_node("pattern_observed", "pattern_observed", "Pattern Observed")
        self.register_node("pattern_confirmed", "pattern_confirmed", "Pattern Confirmed")
        self.register_node("automation_proposed", "automation_proposed", "Automation Proposed")

        self.register_edge(
            "pattern_observed", "pattern_confirmed", "confirm_pattern",
            "Verify pattern with 3+ observations",
            tool_hint="verify_pattern",
        )
        self.register_edge(
            "pattern_confirmed", "automation_proposed", "propose_automation",
            "Propose automation for confirmed pattern",
            tool_hint="propose_automation",
        )

        self.register_path(
            "Pattern → Automation",
            ["pattern_observed", "pattern_confirmed", "automation_proposed"],
            impact="medium",
            description="Detect repeated behaviors and propose automations",
        )

    # ── Chain 5: Financial Intelligence ──

    def _build_financial_chain(self) -> None:
        """Financial: detect → anomaly → saving."""

        self.register_node("transaction_detected", "transaction_detected", "Transaction Detected")
        self.register_node("anomaly_found", "anomaly_found", "Spending Anomaly")
        self.register_node("saving_proposed", "saving_proposed", "Saving Opportunity")

        self.register_edge(
            "transaction_detected", "anomaly_found", "detect_anomaly",
            "Detect unusual spending or forgotten subscriptions",
            tool_hint="analyze_transactions",
        )
        self.register_edge(
            "anomaly_found", "saving_proposed", "propose_saving",
            "Propose cancellation or alternative",
            tool_hint="propose_saving",
        )

        self.register_path(
            "Financial Intelligence",
            ["transaction_detected", "anomaly_found", "saving_proposed"],
            impact="medium",
            description="Detect spending anomalies and propose savings",
        )

    # ── Aliases for fuzzy matching ──

    def _build_aliases(self) -> None:
        """Register aliases for natural language → node mapping."""
        self.register_aliases({
            "new email": "email_received",
            "email": "email_received",
            "urgent email": "email_urgent",
            "inbox": "email_received",
            "meeting": "meeting_upcoming",
            "calendar": "meeting_upcoming",
            "standup": "meeting_upcoming",
            "github issue": "issue_reported",
            "bug": "issue_reported",
            "issue": "issue_reported",
            "pull request": "issue_reported",
            "pattern": "pattern_observed",
            "habit": "pattern_observed",
            "routine": "pattern_observed",
            "spending": "transaction_detected",
            "subscription": "transaction_detected",
            "payment": "transaction_detected",
            "invoice": "transaction_detected",
        })

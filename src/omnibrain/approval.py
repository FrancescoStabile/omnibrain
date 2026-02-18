"""
OmniBrain — Approval Gate (Day 19-20)

Central approval system for all actions that need user confirmation
before execution. This is the "trust but verify" layer.

Flow (from manifesto Section 8):
    1. OmniBrain proposes an action (creates Proposal)
    2. User reviews via Telegram/CLI/API
    3. User approves or rejects
    4. If approved, action is executed
    5. Result logged

Approval levels:
    - PRE_APPROVED: Execute immediately (e.g., email classification)
    - NEEDS_APPROVAL: Create proposal, wait for user (e.g., send email)
    - NEVER: Never auto-execute (e.g., delete account data)

The ApprovalGate is wired into the ProactiveEngine and email tools.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from omnibrain.db import OmniBrainDB
from omnibrain.models import ProposalStatus

logger = logging.getLogger("omnibrain.approval")


# ═══════════════════════════════════════════════════════════════════════════
# Approval Levels
# ═══════════════════════════════════════════════════════════════════════════


class ApprovalLevel:
    """What level of approval an action needs."""
    PRE_APPROVED = "pre_approved"     # No approval needed
    NEEDS_APPROVAL = "needs_approval" # Must be approved before execution
    NEVER = "never"                   # Cannot be auto-executed


# Default approval requirements per action type
DEFAULT_APPROVAL_MAP: dict[str, str] = {
    # Read-only – always pre-approved
    "fetch_emails": ApprovalLevel.PRE_APPROVED,
    "search_emails": ApprovalLevel.PRE_APPROVED,
    "search_memory": ApprovalLevel.PRE_APPROVED,
    "classify_email": ApprovalLevel.PRE_APPROVED,
    "get_calendar": ApprovalLevel.PRE_APPROVED,
    "store_observation": ApprovalLevel.PRE_APPROVED,
    # Write actions – need approval
    "send_email": ApprovalLevel.NEEDS_APPROVAL,
    "send_draft": ApprovalLevel.NEEDS_APPROVAL,
    "draft_email": ApprovalLevel.PRE_APPROVED,   # Creating a draft is safe
    "create_calendar_event": ApprovalLevel.NEEDS_APPROVAL,
    "delete_event": ApprovalLevel.NEEDS_APPROVAL,
    # Dangerous – never auto-execute
    "delete_data": ApprovalLevel.NEVER,
    "reset_preferences": ApprovalLevel.NEVER,
}


# ═══════════════════════════════════════════════════════════════════════════
# Email Draft
# ═══════════════════════════════════════════════════════════════════════════


class EmailDraft:
    """Represents an email draft waiting for approval.

    This is the bridge between "AI proposes" and "user approves."
    """

    def __init__(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        thread_id: str = "",
        gmail_draft_id: str = "",
        original_email_id: str = "",
        reasoning: str = "",
    ):
        self.to = to
        self.subject = subject
        self.body = body
        self.cc = cc
        self.bcc = bcc
        self.in_reply_to = in_reply_to
        self.thread_id = thread_id
        self.gmail_draft_id = gmail_draft_id
        self.original_email_id = original_email_id
        self.reasoning = reasoning

    def to_dict(self) -> dict[str, str]:
        return {
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "cc": self.cc,
            "bcc": self.bcc,
            "in_reply_to": self.in_reply_to,
            "thread_id": self.thread_id,
            "gmail_draft_id": self.gmail_draft_id,
            "original_email_id": self.original_email_id,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmailDraft:
        return cls(
            to=data.get("to", ""),
            subject=data.get("subject", ""),
            body=data.get("body", ""),
            cc=data.get("cc", ""),
            bcc=data.get("bcc", ""),
            in_reply_to=data.get("in_reply_to", ""),
            thread_id=data.get("thread_id", ""),
            gmail_draft_id=data.get("gmail_draft_id", ""),
            original_email_id=data.get("original_email_id", ""),
            reasoning=data.get("reasoning", ""),
        )

    def preview(self, max_body: int = 200) -> str:
        """Short preview for display."""
        body_preview = self.body[:max_body] + ("..." if len(self.body) > max_body else "")
        lines = [
            f"To: {self.to}",
            f"Subject: {self.subject}",
        ]
        if self.cc:
            lines.append(f"Cc: {self.cc}")
        lines.append(f"\n{body_preview}")
        if self.reasoning:
            lines.append(f"\n💡 Reasoning: {self.reasoning}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Approval Gate
# ═══════════════════════════════════════════════════════════════════════════


class ApprovalGate:
    """Central approval system for all OmniBrain actions.

    Usage:
        gate = ApprovalGate(db)

        # Check if action needs approval
        level = gate.get_approval_level("send_email")
        if level == ApprovalLevel.NEEDS_APPROVAL:
            proposal_id = gate.propose_email_draft(draft)
            # Wait for user to approve via Telegram/CLI/API
        elif level == ApprovalLevel.PRE_APPROVED:
            # Execute immediately

        # When user approves
        result = gate.execute_approved(proposal_id, executor_fn)
    """

    def __init__(
        self,
        db: OmniBrainDB,
        approval_map: dict[str, str] | None = None,
        default_expiry_hours: int = 24,
    ):
        self._db = db
        self._approval_map = approval_map or dict(DEFAULT_APPROVAL_MAP)
        self._default_expiry_hours = default_expiry_hours
        self._executors: dict[str, Callable[..., Any]] = {}

    def get_approval_level(self, action_type: str) -> str:
        """Get the approval level for an action type."""
        return self._approval_map.get(action_type, ApprovalLevel.NEEDS_APPROVAL)

    def set_approval_level(self, action_type: str, level: str) -> None:
        """Override the approval level for an action type."""
        self._approval_map[action_type] = level

    def register_executor(self, action_type: str, executor: Callable[..., Any]) -> None:
        """Register a function that executes an approved action.

        The executor receives the proposal's action_data dict and returns a result string.
        """
        self._executors[action_type] = executor

    def needs_approval(self, action_type: str) -> bool:
        """Quick check: does this action need user approval?"""
        level = self.get_approval_level(action_type)
        return level == ApprovalLevel.NEEDS_APPROVAL

    def is_blocked(self, action_type: str) -> bool:
        """Quick check: is this action blocked (NEVER)?"""
        return self.get_approval_level(action_type) == ApprovalLevel.NEVER

    # ── Proposing Actions ──

    def propose(
        self,
        action_type: str,
        title: str,
        description: str,
        action_data: dict[str, Any] | None = None,
        priority: int = 2,
        expiry_hours: int | None = None,
    ) -> int:
        """Create a proposal for user approval. Returns proposal ID.

        If the action is pre-approved, returns 0 (no proposal needed).
        If the action is blocked, returns -1.
        """
        level = self.get_approval_level(action_type)

        if level == ApprovalLevel.PRE_APPROVED:
            return 0
        if level == ApprovalLevel.NEVER:
            return -1

        expiry = datetime.now() + timedelta(hours=expiry_hours or self._default_expiry_hours)
        proposal_id = self._db.insert_proposal(
            type=action_type,
            title=title,
            description=description,
            action_data=action_data,
            priority=priority,
            expires_at=expiry,
        )
        logger.info(f"Proposal created: #{proposal_id} [{action_type}] {title}")
        return proposal_id

    def propose_email_draft(self, draft: EmailDraft, priority: int = 3) -> int:
        """Create a proposal specifically for an email draft.

        This is the most common approval flow:
        AI drafts email → creates proposal → user sees in Telegram → approves/rejects.
        """
        return self.propose(
            action_type="send_email",
            title=f"Send email to {draft.to}: {draft.subject}",
            description=draft.preview(),
            action_data=draft.to_dict(),
            priority=priority,
        )

    # ── Executing Approved Actions ──

    def execute_approved(
        self,
        proposal_id: int,
        executor: Callable[[dict[str, Any]], str] | None = None,
    ) -> dict[str, Any]:
        """Execute an approved proposal.

        Args:
            proposal_id: The proposal to execute.
            executor: Optional function to execute the action.
                      If not provided, looks up registered executors.

        Returns:
            {"ok": bool, "result": str, "proposal_id": int}
        """
        # Get proposal
        proposals = self._db.get_pending_proposals()
        proposal = None
        for p in proposals:
            if p["id"] == proposal_id:
                proposal = p
                break

        if not proposal:
            # Check if already approved (not pending)
            return {"ok": False, "result": f"Proposal #{proposal_id} not found or not pending", "proposal_id": proposal_id}

        action_type = proposal.get("type", "")
        action_data_str = proposal.get("action_data", "{}")
        try:
            action_data = json.loads(action_data_str) if isinstance(action_data_str, str) else action_data_str
        except (json.JSONDecodeError, TypeError):
            action_data = {}

        # Find executor
        exec_fn = executor or self._executors.get(action_type)
        if not exec_fn:
            self._db.update_proposal_status(proposal_id, "approved", result="No executor registered")
            return {"ok": False, "result": "No executor registered", "proposal_id": proposal_id}

        # Execute
        try:
            result = exec_fn(action_data)
            self._db.update_proposal_status(
                proposal_id,
                ProposalStatus.EXECUTED.value,
                result=str(result)[:500],
            )
            logger.info(f"Proposal #{proposal_id} executed: {result}")
            return {"ok": True, "result": str(result), "proposal_id": proposal_id}
        except Exception as e:
            self._db.update_proposal_status(proposal_id, "approved", result=f"Execution failed: {e}")
            logger.error(f"Proposal #{proposal_id} execution failed: {e}")
            return {"ok": False, "result": f"Execution failed: {e}", "proposal_id": proposal_id}

    # ── Maintenance ──

    def expire_old(self) -> int:
        """Expire old proposals. Returns count expired."""
        return self._db.expire_old_proposals()

    def get_pending(self) -> list[dict[str, Any]]:
        """Get all pending proposals."""
        return self._db.get_pending_proposals()

    def approve(self, proposal_id: int) -> bool:
        """Approve a proposal (mark as approved, don't execute yet)."""
        return self._db.update_proposal_status(proposal_id, ProposalStatus.APPROVED.value)

    def reject(self, proposal_id: int, reason: str = "") -> bool:
        """Reject a proposal."""
        return self._db.update_proposal_status(proposal_id, ProposalStatus.REJECTED.value, result=reason)


# ═══════════════════════════════════════════════════════════════════════════
# Email Draft Tool
# ═══════════════════════════════════════════════════════════════════════════

DRAFT_EMAIL_SCHEMA = {
    "name": "draft_email",
    "description": "Create an email draft for user review. The draft will be shown to the user for approval before sending.",
    "parameters": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address(es)"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body (plain text)"},
            "cc": {"type": "string", "description": "CC addresses", "default": ""},
            "reasoning": {"type": "string", "description": "Why this draft is being created"},
            "in_reply_to": {"type": "string", "description": "Email ID being replied to", "default": ""},
            "thread_id": {"type": "string", "description": "Gmail thread ID for threading", "default": ""},
        },
        "required": ["to", "subject", "body"],
    },
}

SEND_APPROVED_EMAIL_SCHEMA = {
    "name": "send_approved_email",
    "description": "Send an email that has been approved by the user. Requires a proposal_id that was approved.",
    "parameters": {
        "type": "object",
        "properties": {
            "proposal_id": {"type": "integer", "description": "Approved proposal ID"},
        },
        "required": ["proposal_id"],
    },
}


def draft_email_tool(gate: ApprovalGate, args: dict[str, Any]) -> dict[str, Any]:
    """Tool handler: create an email draft and submit for approval.

    Returns:
        {"draft_created": bool, "proposal_id": int, "preview": str}
    """
    draft = EmailDraft(
        to=args.get("to", ""),
        subject=args.get("subject", ""),
        body=args.get("body", ""),
        cc=args.get("cc", ""),
        in_reply_to=args.get("in_reply_to", ""),
        thread_id=args.get("thread_id", ""),
        reasoning=args.get("reasoning", ""),
    )

    if not draft.to or not draft.subject:
        return {"draft_created": False, "error": "Missing 'to' or 'subject'"}

    proposal_id = gate.propose_email_draft(draft)

    return {
        "draft_created": True,
        "proposal_id": proposal_id,
        "preview": draft.preview(),
        "awaiting_approval": True,
    }


def send_approved_email_tool(
    gate: ApprovalGate,
    gmail_client: Any,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Tool handler: send an approved email draft.

    This is called after the user approves a proposal. It:
    1. Gets the proposal action_data (the draft)
    2. Sends via GmailClient
    3. Marks proposal as executed

    Returns:
        {"sent": bool, "message_id": str}
    """
    proposal_id = args.get("proposal_id", 0)
    if not proposal_id:
        return {"sent": False, "error": "Missing proposal_id"}

    def _send_executor(action_data: dict[str, Any]) -> str:
        result = gmail_client.send_email(
            to=action_data.get("to", ""),
            subject=action_data.get("subject", ""),
            body=action_data.get("body", ""),
            cc=action_data.get("cc", ""),
            bcc=action_data.get("bcc", ""),
            in_reply_to=action_data.get("in_reply_to", ""),
            thread_id=action_data.get("thread_id", ""),
        )
        return f"Sent: message_id={result.get('message_id', '')}"

    result = gate.execute_approved(proposal_id, executor=_send_executor)
    return {
        "sent": result["ok"],
        "result": result["result"],
        "proposal_id": proposal_id,
    }

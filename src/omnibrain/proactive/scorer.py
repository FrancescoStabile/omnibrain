"""
OmniBrain — Priority Scorer & Notification Level Selector

Unified scoring system for all items flowing through OmniBrain:
emails, calendar events, proposals, observations, patterns.

PriorityScorer:
    Produces a 0.0–1.0 score from multiple weighted signals:
    - urgency (explicit labels or inferred)
    - deadline proximity (hours until due)
    - contact importance (VIP, relationship type, interaction count)
    - item type weight (action-required email > newsletter)
    - pattern strength (recurring high-confidence patterns)

NotificationLevelSelector:
    Maps a scored item to one of four notification levels:
    CRITICAL  (≥ 0.85)  — Immediate, persistent
    IMPORTANT (≥ 0.55)  — Immediate, non-intrusive
    FYI       (≥ 0.25)  — Batched into next briefing
    SILENT    (< 0.25)  — Stored only
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from omnibrain.models import (
    NotificationLevel,
    Priority,
    Urgency,
)

logger = logging.getLogger("omnibrain.proactive.scorer")


# ═══════════════════════════════════════════════════════════════════════════
# Signal Weights — tuneable knobs
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS: dict[str, float] = {
    "urgency": 0.30,
    "deadline": 0.25,
    "contact": 0.20,
    "type": 0.15,
    "pattern": 0.10,
}

# Notification level thresholds
CRITICAL_THRESHOLD = 0.85
IMPORTANT_THRESHOLD = 0.55
FYI_THRESHOLD = 0.25

# Urgency label → raw score (0.0-1.0)
URGENCY_SCORES: dict[str, float] = {
    Urgency.CRITICAL.value: 1.0,
    Urgency.HIGH.value: 0.8,
    Urgency.MEDIUM.value: 0.5,
    Urgency.LOW.value: 0.2,
}

# Priority enum → raw score
PRIORITY_SCORES: dict[int, float] = {
    Priority.CRITICAL.value: 1.0,
    Priority.HIGH.value: 0.8,
    Priority.MEDIUM.value: 0.5,
    Priority.LOW.value: 0.2,
    Priority.UNSET.value: 0.3,
}

# Item category → base type score
TYPE_SCORES: dict[str, float] = {
    "action_required": 0.9,
    "urgent_email": 0.9,
    "meeting_prep": 0.8,
    "email_draft": 0.7,
    "proposal": 0.7,
    "personal": 0.5,
    "fyi": 0.3,
    "newsletter": 0.2,
    "spam": 0.0,
    "archive": 0.1,
    "observation": 0.3,
    "pattern": 0.4,
}

# Relationship type → contact importance multiplier
RELATIONSHIP_SCORES: dict[str, float] = {
    "client": 0.9,
    "investor": 0.9,
    "family": 0.8,
    "colleague": 0.6,
    "friend": 0.5,
    "vendor": 0.4,
    "unknown": 0.2,
}


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ScoringSignals:
    """Raw signals extracted from an item before scoring."""

    # Urgency
    urgency_label: str = ""             # "critical", "high", "medium", "low"
    priority_value: int = Priority.UNSET.value

    # Deadline
    deadline: datetime | None = None    # When the item is due
    reference_time: datetime | None = None  # "now" for scoring

    # Contact
    is_vip: bool = False
    relationship: str = "unknown"
    interaction_count: int = 0

    # Type
    item_type: str = ""                 # "action_required", "newsletter", etc.

    # Pattern
    pattern_strength: float = 0.0       # 0.0-1.0 from DetectedPattern.strength
    pattern_occurrences: int = 0

    # Overrides
    force_critical: bool = False        # Hard override to CRITICAL
    force_silent: bool = False          # Hard override to SILENT

    def to_dict(self) -> dict[str, Any]:
        return {
            "urgency_label": self.urgency_label,
            "priority_value": self.priority_value,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "is_vip": self.is_vip,
            "relationship": self.relationship,
            "interaction_count": self.interaction_count,
            "item_type": self.item_type,
            "pattern_strength": self.pattern_strength,
            "pattern_occurrences": self.pattern_occurrences,
            "force_critical": self.force_critical,
            "force_silent": self.force_silent,
        }


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of how a score was computed."""

    urgency_raw: float = 0.0
    deadline_raw: float = 0.0
    contact_raw: float = 0.0
    type_raw: float = 0.0
    pattern_raw: float = 0.0

    urgency_weighted: float = 0.0
    deadline_weighted: float = 0.0
    contact_weighted: float = 0.0
    type_weighted: float = 0.0
    pattern_weighted: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "urgency": {"raw": self.urgency_raw, "weighted": self.urgency_weighted},
            "deadline": {"raw": self.deadline_raw, "weighted": self.deadline_weighted},
            "contact": {"raw": self.contact_raw, "weighted": self.contact_weighted},
            "type": {"raw": self.type_raw, "weighted": self.type_weighted},
            "pattern": {"raw": self.pattern_raw, "weighted": self.pattern_weighted},
        }


@dataclass
class PriorityScore:
    """Result of scoring an item."""

    score: float                        # 0.0-1.0 final score
    notification_level: str             # "silent", "fyi", "important", "critical"
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    signals: ScoringSignals = field(default_factory=ScoringSignals)
    reason: str = ""                    # Human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "notification_level": self.notification_level,
            "breakdown": self.breakdown.to_dict(),
            "reason": self.reason,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Priority Scorer
# ═══════════════════════════════════════════════════════════════════════════


class PriorityScorer:
    """Unified priority scoring for all OmniBrain items.

    Usage:
        scorer = PriorityScorer()

        # Score an email
        signals = ScoringSignals(
            urgency_label="high",
            is_vip=True,
            item_type="action_required",
        )
        result = scorer.score(signals)
        print(f"Score: {result.score}, Level: {result.notification_level}")

        # Quick score with kwargs
        result = scorer.score_email(urgency="critical", is_vip=True)
        result = scorer.score_event(deadline=meeting_start, attendee_count=5)
        result = scorer.score_proposal(priority=Priority.HIGH)
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        critical_threshold: float = CRITICAL_THRESHOLD,
        important_threshold: float = IMPORTANT_THRESHOLD,
        fyi_threshold: float = FYI_THRESHOLD,
    ):
        self._weights = weights or dict(DEFAULT_WEIGHTS)
        self._critical = critical_threshold
        self._important = important_threshold
        self._fyi = fyi_threshold

        # Validate weights sum roughly to 1.0
        total = sum(self._weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(
                f"Signal weights sum to {total:.3f}, normalizing to 1.0"
            )
            for k in self._weights:
                self._weights[k] /= total

    @property
    def weights(self) -> dict[str, float]:
        """Current signal weights (read-only copy)."""
        return dict(self._weights)

    @property
    def thresholds(self) -> dict[str, float]:
        """Current notification thresholds."""
        return {
            "critical": self._critical,
            "important": self._important,
            "fyi": self._fyi,
        }

    # ── Core Scoring ──

    def score(self, signals: ScoringSignals) -> PriorityScore:
        """Score an item from its signals. Returns PriorityScore."""
        # Hard overrides
        if signals.force_critical:
            return PriorityScore(
                score=1.0,
                notification_level=NotificationLevel.CRITICAL.value,
                signals=signals,
                reason="Force-critical override",
            )
        if signals.force_silent:
            return PriorityScore(
                score=0.0,
                notification_level=NotificationLevel.SILENT.value,
                signals=signals,
                reason="Force-silent override",
            )

        breakdown = ScoreBreakdown()

        # 1. Urgency signal
        breakdown.urgency_raw = self._score_urgency(signals)
        breakdown.urgency_weighted = breakdown.urgency_raw * self._weights.get("urgency", 0)

        # 2. Deadline signal
        breakdown.deadline_raw = self._score_deadline(signals)
        breakdown.deadline_weighted = breakdown.deadline_raw * self._weights.get("deadline", 0)

        # 3. Contact importance signal
        breakdown.contact_raw = self._score_contact(signals)
        breakdown.contact_weighted = breakdown.contact_raw * self._weights.get("contact", 0)

        # 4. Item type signal
        breakdown.type_raw = self._score_type(signals)
        breakdown.type_weighted = breakdown.type_raw * self._weights.get("type", 0)

        # 5. Pattern signal
        breakdown.pattern_raw = self._score_pattern(signals)
        breakdown.pattern_weighted = breakdown.pattern_raw * self._weights.get("pattern", 0)

        # Final score = sum of weighted signals, capped at 1.0
        final = min(1.0, (
            breakdown.urgency_weighted
            + breakdown.deadline_weighted
            + breakdown.contact_weighted
            + breakdown.type_weighted
            + breakdown.pattern_weighted
        ))
        final = round(final, 4)

        # Determine notification level
        level = self._select_level(final)

        # Build reason
        reason = self._build_reason(signals, breakdown, final)

        return PriorityScore(
            score=final,
            notification_level=level,
            breakdown=breakdown,
            signals=signals,
            reason=reason,
        )

    # ── Convenience Methods ──

    def score_email(
        self,
        urgency: str = "medium",
        sender_is_vip: bool = False,
        sender_relationship: str = "unknown",
        category: str = "fyi",
        deadline: datetime | None = None,
        interaction_count: int = 0,
    ) -> PriorityScore:
        """Score an email with email-specific parameters."""
        signals = ScoringSignals(
            urgency_label=urgency,
            is_vip=sender_is_vip,
            relationship=sender_relationship,
            item_type=category,
            deadline=deadline,
            interaction_count=interaction_count,
        )
        return self.score(signals)

    def score_event(
        self,
        deadline: datetime | None = None,
        attendee_count: int = 0,
        is_recurring: bool = False,
        has_vip_attendee: bool = False,
        priority: int = Priority.MEDIUM.value,
    ) -> PriorityScore:
        """Score a calendar event."""
        # More attendees → more important
        item_type = "meeting_prep"
        if attendee_count >= 5:
            item_type = "action_required"

        signals = ScoringSignals(
            priority_value=priority,
            deadline=deadline,
            is_vip=has_vip_attendee,
            item_type=item_type,
            interaction_count=attendee_count,
        )
        return self.score(signals)

    def score_proposal(
        self,
        priority: int = Priority.MEDIUM.value,
        proposal_type: str = "proposal",
        deadline: datetime | None = None,
    ) -> PriorityScore:
        """Score an action proposal."""
        signals = ScoringSignals(
            priority_value=priority,
            item_type=proposal_type,
            deadline=deadline,
        )
        return self.score(signals)

    def score_pattern(
        self,
        strength: float = 0.0,
        occurrences: int = 0,
    ) -> PriorityScore:
        """Score a detected pattern."""
        signals = ScoringSignals(
            item_type="pattern",
            pattern_strength=strength,
            pattern_occurrences=occurrences,
        )
        return self.score(signals)

    # ── Signal Scoring Functions ──

    def _score_urgency(self, signals: ScoringSignals) -> float:
        """Urgency signal: from label or priority enum."""
        if signals.urgency_label:
            return URGENCY_SCORES.get(signals.urgency_label, 0.3)
        return PRIORITY_SCORES.get(signals.priority_value, 0.3)

    def _score_deadline(self, signals: ScoringSignals) -> float:
        """Deadline proximity signal: closer deadline → higher score.

        Scoring curve:
            ≤ 30 min  → 1.0
            ≤ 2 hours → 0.8
            ≤ 8 hours → 0.6
            ≤ 24 hours → 0.4
            ≤ 72 hours → 0.2
            > 72 hours → 0.1
            No deadline → 0.0
        """
        if not signals.deadline:
            return 0.0

        now = signals.reference_time or datetime.now()
        delta = signals.deadline - now

        if delta <= timedelta(0):
            return 1.0  # Past due
        hours = delta.total_seconds() / 3600

        if hours <= 0.5:
            return 1.0
        if hours <= 2:
            return 0.8
        if hours <= 8:
            return 0.6
        if hours <= 24:
            return 0.4
        if hours <= 72:
            return 0.2
        return 0.1

    def _score_contact(self, signals: ScoringSignals) -> float:
        """Contact importance signal: VIP + relationship + interactions."""
        base = RELATIONSHIP_SCORES.get(signals.relationship, 0.2)

        # VIP boost
        if signals.is_vip:
            base = max(base, 0.8)

        # Interaction count boost (capped at 0.2 extra)
        if signals.interaction_count > 0:
            interaction_bonus = min(signals.interaction_count / 50, 0.2)
            base = min(1.0, base + interaction_bonus)

        return base

    def _score_type(self, signals: ScoringSignals) -> float:
        """Item type signal."""
        return TYPE_SCORES.get(signals.item_type, 0.3)

    def _score_pattern(self, signals: ScoringSignals) -> float:
        """Pattern signal: strength + occurrence bonus."""
        if signals.pattern_strength <= 0 and signals.pattern_occurrences <= 0:
            return 0.0

        base = signals.pattern_strength
        # Extra 0.1 for every 5 occurrences, capped at 0.3
        if signals.pattern_occurrences > 0:
            occ_bonus = min(signals.pattern_occurrences / 50, 0.3)
            base = min(1.0, base + occ_bonus)

        return base

    # ── Notification Level Selection ──

    def _select_level(self, score: float) -> str:
        """Map a score to a notification level."""
        if score >= self._critical:
            return NotificationLevel.CRITICAL.value
        if score >= self._important:
            return NotificationLevel.IMPORTANT.value
        if score >= self._fyi:
            return NotificationLevel.FYI.value
        return NotificationLevel.SILENT.value

    def _build_reason(
        self, signals: ScoringSignals, breakdown: ScoreBreakdown, final: float
    ) -> str:
        """Build human-readable explanation for the score."""
        parts = []

        # Find top signal
        weighted = {
            "urgency": breakdown.urgency_weighted,
            "deadline": breakdown.deadline_weighted,
            "contact": breakdown.contact_weighted,
            "type": breakdown.type_weighted,
            "pattern": breakdown.pattern_weighted,
        }
        top_signal = max(weighted, key=weighted.get)  # type: ignore[arg-type]

        if top_signal == "urgency":
            label = signals.urgency_label or f"priority={signals.priority_value}"
            parts.append(f"urgency ({label})")
        elif top_signal == "deadline":
            if signals.deadline:
                parts.append(f"deadline approaching ({signals.deadline.strftime('%H:%M')})")
            else:
                parts.append("deadline signal")
        elif top_signal == "contact":
            if signals.is_vip:
                parts.append("VIP contact")
            else:
                parts.append(f"contact ({signals.relationship})")
        elif top_signal == "type":
            parts.append(f"item type ({signals.item_type})")
        elif top_signal == "pattern":
            parts.append(f"pattern strength ({signals.pattern_strength:.2f})")

        # Add secondary signals > 0.1 weighted
        for sig, val in sorted(weighted.items(), key=lambda x: -x[1]):
            if sig != top_signal and val >= 0.1:
                parts.append(sig)

        level_name = self._select_level(final).upper()
        return f"[{level_name}] Driven by {', '.join(parts)}" if parts else f"[{level_name}]"


# ═══════════════════════════════════════════════════════════════════════════
# Notification Level Selector (standalone)
# ═══════════════════════════════════════════════════════════════════════════


class NotificationLevelSelector:
    """Dynamically selects notification level for proactive engine events.

    Used by ProactiveEngine handlers to determine how to notify the user.
    Wraps PriorityScorer with domain-specific logic for escalation and
    user-preference overrides.

    Usage:
        selector = NotificationLevelSelector()

        # For an email
        level = selector.for_email(urgency="critical", sender_is_vip=True)
        # → "critical"

        # For a calendar event
        level = selector.for_event(minutes_until=15, attendees=8)
        # → "important"

        # With quiet hours
        selector = NotificationLevelSelector(quiet_hours=(22, 7))
        level = selector.for_email(urgency="high")
        # → "fyi" (downgraded during quiet hours)
    """

    def __init__(
        self,
        scorer: PriorityScorer | None = None,
        quiet_hours: tuple[int, int] | None = None,
        max_critical_per_hour: int = 5,
    ):
        self._scorer = scorer or PriorityScorer()
        self._quiet_hours = quiet_hours  # (start_hour, end_hour)
        self._max_critical = max_critical_per_hour
        self._critical_history: list[datetime] = []

    def for_email(
        self,
        urgency: str = "medium",
        sender_is_vip: bool = False,
        sender_relationship: str = "unknown",
        category: str = "fyi",
    ) -> str:
        """Select notification level for an email event."""
        result = self._scorer.score_email(
            urgency=urgency,
            sender_is_vip=sender_is_vip,
            sender_relationship=sender_relationship,
            category=category,
        )
        return self._apply_modifiers(result.notification_level)

    def for_event(
        self,
        minutes_until: int | None = None,
        attendees: int = 0,
        has_vip: bool = False,
        priority: int = Priority.MEDIUM.value,
    ) -> str:
        """Select notification level for a calendar event."""
        deadline = None
        if minutes_until is not None:
            deadline = datetime.now() + timedelta(minutes=minutes_until)

        result = self._scorer.score_event(
            deadline=deadline,
            attendee_count=attendees,
            has_vip_attendee=has_vip,
            priority=priority,
        )
        return self._apply_modifiers(result.notification_level)

    def for_proposal(
        self,
        priority: int = Priority.MEDIUM.value,
        proposal_type: str = "proposal",
    ) -> str:
        """Select notification level for a pending proposal."""
        result = self._scorer.score_proposal(
            priority=priority,
            proposal_type=proposal_type,
        )
        return self._apply_modifiers(result.notification_level)

    def for_pattern(
        self,
        strength: float = 0.0,
        occurrences: int = 0,
    ) -> str:
        """Select notification level for a detected pattern."""
        result = self._scorer.score_pattern(
            strength=strength,
            occurrences=occurrences,
        )
        return self._apply_modifiers(result.notification_level)

    def for_score(self, score: float) -> str:
        """Select notification level directly from a numeric score."""
        level = self._scorer._select_level(score)
        return self._apply_modifiers(level)

    @property
    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        if not self._quiet_hours:
            return False
        return _in_quiet_hours(datetime.now().hour, self._quiet_hours)

    def _apply_modifiers(self, level: str) -> str:
        """Apply quiet hours and rate limiting to the base level."""
        # Quiet hours: downgrade IMPORTANT → FYI, CRITICAL → IMPORTANT
        if self.is_quiet_hours:
            level = _downgrade_level(level)

        # Rate limit CRITICAL notifications
        if level == NotificationLevel.CRITICAL.value:
            if self._is_critical_rate_limited():
                level = NotificationLevel.IMPORTANT.value
            else:
                self._critical_history.append(datetime.now())

        return level

    def _is_critical_rate_limited(self) -> bool:
        """Check if CRITICAL notifications are being sent too frequently."""
        if self._max_critical <= 0:
            return False

        now = datetime.now()
        cutoff = now - timedelta(hours=1)

        # Prune old entries
        self._critical_history = [
            t for t in self._critical_history if t > cutoff
        ]

        return len(self._critical_history) >= self._max_critical


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _in_quiet_hours(hour: int, window: tuple[int, int]) -> bool:
    """Check if an hour falls within a quiet window.

    Handles overnight windows like (22, 7) = 22:00 → 07:00.
    """
    start, end = window
    if start <= end:
        return start <= hour < end
    # Overnight window
    return hour >= start or hour < end


def _downgrade_level(level: str) -> str:
    """Downgrade a notification level by one step."""
    if level == NotificationLevel.CRITICAL.value:
        return NotificationLevel.IMPORTANT.value
    if level == NotificationLevel.IMPORTANT.value:
        return NotificationLevel.FYI.value
    return level  # FYI and SILENT stay


# ═══════════════════════════════════════════════════════════════════════════
# Module-level convenience
# ═══════════════════════════════════════════════════════════════════════════

_default_scorer = PriorityScorer()
_default_selector = NotificationLevelSelector()


def score_item(signals: ScoringSignals) -> PriorityScore:
    """Score an item with the default scorer."""
    return _default_scorer.score(signals)


def select_notification_level(score: float) -> str:
    """Select notification level from a score using the default selector."""
    return _default_selector.for_score(score)

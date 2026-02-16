"""
OmniBrain — Pattern Detection (Day 21)

Detects recurring patterns from observations and action history,
proposes automations, and feeds the proactive engine.

Architecture:
    PatternDetector
    ├── observe()           — record an observation from any action
    ├── detect()            — run full pattern analysis
    ├── get_patterns()      — return detected patterns
    └── propose_automations() — suggest automations for strong patterns

Pattern types (from manifesto Section 10):
    - time_pattern:           "Reads email at 09:00 every day"
    - communication_pattern:  "Always replies to Marco within 1h"
    - recurring_search:       "Searches for 'pricing' every Monday"
    - action_sequence:        "After meeting, always sends follow-up"
    - email_routing:          "Archives all newsletters from X"
    - calendar_habit:         "Creates prep doc before client meetings"

Detection algorithm:
    1. Group observations by pattern_type
    2. Within each group, cluster by description similarity
    3. If a cluster has ≥ min_occurrences with avg confidence ≥ threshold → pattern detected
    4. For strong patterns (≥ strong_threshold), propose automations
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from omnibrain.db import OmniBrainDB
from omnibrain.models import Observation

logger = logging.getLogger("omnibrain.proactive.patterns")


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DetectedPattern:
    """A pattern detected from observation history."""

    pattern_type: str
    description: str
    occurrences: int
    avg_confidence: float
    first_seen: datetime
    last_seen: datetime
    observation_ids: list[int] = field(default_factory=list)
    automation_proposed: bool = False
    automation_description: str = ""

    @property
    def strength(self) -> float:
        """Pattern strength: combines frequency and confidence (0.0 - 1.0)."""
        freq_score = min(self.occurrences / 10, 1.0)  # caps at 10 occurrences
        return round(freq_score * self.avg_confidence, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "description": self.description,
            "occurrences": self.occurrences,
            "avg_confidence": self.avg_confidence,
            "strength": self.strength,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "observation_ids": self.observation_ids,
            "automation_proposed": self.automation_proposed,
            "automation_description": self.automation_description,
        }


@dataclass
class AutomationProposal:
    """A proposed automation based on a detected pattern."""

    pattern: DetectedPattern
    action_type: str
    title: str
    description: str
    trigger: str          # When the automation should fire
    action_spec: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "title": self.title,
            "description": self.description,
            "trigger": self.trigger,
            "pattern_strength": self.pattern.strength,
            "pattern_occurrences": self.pattern.occurrences,
            "action_spec": self.action_spec,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Pattern Detector
# ═══════════════════════════════════════════════════════════════════════════


class PatternDetector:
    """Detects patterns from observations and proposes automations.

    Usage:
        detector = PatternDetector(db)

        # Record observations from actions
        detector.observe("time_pattern", "Reads email at 09:00", confidence=0.8)
        detector.observe("time_pattern", "Reads email at 09:05", confidence=0.7)

        # Run detection
        patterns = detector.detect()
        for p in patterns:
            print(f"{p.description}: {p.occurrences}x (strength: {p.strength})")

        # Get automation proposals
        proposals = detector.propose_automations()
    """

    def __init__(
        self,
        db: OmniBrainDB,
        min_occurrences: int = 3,
        confidence_threshold: float = 0.5,
        strong_threshold: float = 0.7,
        analysis_days: int = 30,
        similarity_threshold: float = 0.6,
    ):
        self._db = db
        self._min_occurrences = min_occurrences
        self._confidence_threshold = confidence_threshold
        self._strong_threshold = strong_threshold
        self._analysis_days = analysis_days
        self._similarity_threshold = similarity_threshold
        self._detected_patterns: list[DetectedPattern] = []

    # ── Recording ──

    def observe(
        self,
        pattern_type: str,
        description: str,
        evidence: str = "",
        confidence: float = 0.5,
    ) -> int:
        """Record an observation. Returns observation ID."""
        obs = Observation(
            type=pattern_type,
            detail=description,
            evidence=evidence,
            confidence=confidence,
        )
        obs_id = self._db.insert_observation(obs)
        logger.debug(f"Observation #{obs_id}: [{pattern_type}] {description}")
        return obs_id

    def observe_action(
        self,
        action: str,
        context: dict[str, Any] | None = None,
        confidence: float = 0.5,
    ) -> int:
        """Record an observation from an action execution.

        Automatically classifies into pattern types:
        - Email actions → communication_pattern or email_routing
        - Calendar actions → calendar_habit
        - Search actions → recurring_search
        - Time-based → time_pattern
        """
        ctx = context or {}
        pattern_type = _classify_action(action, ctx)
        detail = _describe_action(action, ctx)
        evidence = json.dumps(ctx)[:500] if ctx else ""

        return self.observe(pattern_type, detail, evidence, confidence)

    # ── Detection ──

    def detect(self) -> list[DetectedPattern]:
        """Run full pattern detection. Returns detected patterns."""
        observations = self._db.get_observations(
            days=self._analysis_days,
            min_confidence=0.0,  # don't filter yet, we'll filter after clustering
        )

        if not observations:
            self._detected_patterns = []
            return []

        # Group by pattern_type
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for obs in observations:
            by_type[obs.get("pattern_type", "unknown")].append(obs)

        patterns: list[DetectedPattern] = []

        for ptype, obs_list in by_type.items():
            # Cluster similar descriptions
            clusters = _cluster_observations(obs_list, self._similarity_threshold)

            for cluster in clusters:
                if len(cluster) < self._min_occurrences:
                    continue

                avg_conf = sum(o.get("confidence", 0) for o in cluster) / len(cluster)
                if avg_conf < self._confidence_threshold:
                    continue

                # Parse timestamps
                timestamps = []
                for o in cluster:
                    ts_str = o.get("last_seen") or o.get("timestamp", "")
                    if ts_str:
                        try:
                            timestamps.append(datetime.fromisoformat(ts_str))
                        except (ValueError, TypeError):
                            pass

                first_seen = min(timestamps) if timestamps else datetime.now()
                last_seen = max(timestamps) if timestamps else datetime.now()

                pattern = DetectedPattern(
                    pattern_type=ptype,
                    description=cluster[0].get("description", ""),
                    occurrences=len(cluster),
                    avg_confidence=round(avg_conf, 3),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    observation_ids=[o.get("id", 0) for o in cluster],
                )
                patterns.append(pattern)

        # Sort by strength descending
        patterns.sort(key=lambda p: p.strength, reverse=True)
        self._detected_patterns = patterns
        logger.info(f"Detected {len(patterns)} patterns from {len(observations)} observations")
        return patterns

    def get_patterns(self) -> list[DetectedPattern]:
        """Return last detected patterns (call detect() first)."""
        return list(self._detected_patterns)

    def get_strong_patterns(self) -> list[DetectedPattern]:
        """Return only strong patterns (above strong_threshold)."""
        return [p for p in self._detected_patterns if p.avg_confidence >= self._strong_threshold]

    # ── Automation Proposals ──

    def propose_automations(self) -> list[AutomationProposal]:
        """Propose automations for strong patterns.

        Only proposes for patterns with avg_confidence ≥ strong_threshold.
        """
        if not self._detected_patterns:
            self.detect()

        proposals: list[AutomationProposal] = []
        strong = self.get_strong_patterns()

        for pattern in strong:
            proposal = _build_automation_proposal(pattern)
            if proposal:
                pattern.automation_proposed = True
                pattern.automation_description = proposal.title
                proposals.append(proposal)

        logger.info(f"Proposed {len(proposals)} automations from {len(strong)} strong patterns")
        return proposals

    # ── Promotion ──

    def promote_pattern(self, pattern: DetectedPattern) -> None:
        """Mark observations in a pattern as promoted to automation."""
        for obs_id in pattern.observation_ids:
            try:
                self._db.promote_observation(obs_id)
            except Exception as e:
                logger.warning(f"Failed to promote observation #{obs_id}: {e}")

    # ── Summary ──

    def summary(self) -> dict[str, Any]:
        """Get a summary of current pattern state."""
        total_obs = len(self._db.get_observations(days=self._analysis_days))
        return {
            "total_observations": total_obs,
            "detected_patterns": len(self._detected_patterns),
            "strong_patterns": len(self.get_strong_patterns()),
            "patterns": [p.to_dict() for p in self._detected_patterns],
        }

    def weekly_analysis(self) -> dict[str, Any]:
        """Run weekly pattern analysis (called by ProactiveEngine)."""
        patterns = self.detect()
        proposals = self.propose_automations()

        return {
            "patterns_detected": len(patterns),
            "automations_proposed": len(proposals),
            "top_patterns": [p.to_dict() for p in patterns[:5]],
            "proposals": [p.to_dict() for p in proposals],
        }


# ═══════════════════════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _classify_action(action: str, context: dict[str, Any]) -> str:
    """Classify an action into a pattern type."""
    action_lower = action.lower()

    if any(kw in action_lower for kw in ("email", "mail", "reply", "send", "draft")):
        # Distinguish routing from communication
        if any(kw in action_lower for kw in ("archive", "label", "filter", "route")):
            return "email_routing"
        return "communication_pattern"

    if any(kw in action_lower for kw in ("calendar", "meeting", "event", "schedule")):
        return "calendar_habit"

    if any(kw in action_lower for kw in ("search", "query", "find", "lookup")):
        return "recurring_search"

    # Check context for time cues
    if context.get("time_of_day") or context.get("scheduled"):
        return "time_pattern"

    if context.get("after_action"):
        return "action_sequence"

    return "time_pattern"  # default


def _describe_action(action: str, context: dict[str, Any]) -> str:
    """Generate a human-readable description of an action."""
    parts = [action]

    if recipient := context.get("recipient"):
        parts.append(f"to {recipient}")
    if subject := context.get("subject"):
        parts.append(f"re: {subject[:50]}")
    if time_of_day := context.get("time_of_day"):
        parts.append(f"at {time_of_day}")
    if source := context.get("source"):
        parts.append(f"from {source}")

    return " ".join(parts)


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Remove common variable parts (times, IDs)
    text = re.sub(r"\d{2}:\d{2}", "HH:MM", text)
    text = re.sub(r"\b[a-f0-9]{8,}\b", "ID", text)
    return text


def _word_overlap(a: str, b: str) -> float:
    """Word-level Jaccard similarity."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _cluster_observations(
    observations: list[dict[str, Any]],
    threshold: float = 0.6,
) -> list[list[dict[str, Any]]]:
    """Cluster observations by description similarity.

    Uses greedy single-linkage clustering with word overlap.
    """
    if not observations:
        return []

    clusters: list[list[dict[str, Any]]] = []
    assigned = set()

    for i, obs in enumerate(observations):
        if i in assigned:
            continue

        cluster = [obs]
        assigned.add(i)
        desc_i = _normalize(obs.get("description", ""))

        for j, other in enumerate(observations):
            if j in assigned:
                continue
            desc_j = _normalize(other.get("description", ""))
            if _word_overlap(desc_i, desc_j) >= threshold:
                cluster.append(other)
                assigned.add(j)

        clusters.append(cluster)

    return clusters


def _build_automation_proposal(pattern: DetectedPattern) -> AutomationProposal | None:
    """Build an automation proposal for a detected pattern."""
    ptype = pattern.pattern_type
    desc = pattern.description

    if ptype == "email_routing":
        return AutomationProposal(
            pattern=pattern,
            action_type="auto_route_email",
            title=f"Auto-route: {desc[:60]}",
            description=f"Automatically apply routing based on pattern seen {pattern.occurrences}x",
            trigger="on_email_received",
            action_spec={"pattern_description": desc},
        )

    if ptype == "communication_pattern":
        return AutomationProposal(
            pattern=pattern,
            action_type="auto_draft_reply",
            title=f"Auto-draft: {desc[:60]}",
            description=f"Draft reply template based on pattern seen {pattern.occurrences}x",
            trigger="on_email_received",
            action_spec={"pattern_description": desc},
        )

    if ptype == "recurring_search":
        return AutomationProposal(
            pattern=pattern,
            action_type="scheduled_search",
            title=f"Scheduled search: {desc[:60]}",
            description=f"Run this search automatically (seen {pattern.occurrences}x)",
            trigger="scheduled",
            action_spec={"pattern_description": desc},
        )

    if ptype == "time_pattern":
        return AutomationProposal(
            pattern=pattern,
            action_type="scheduled_task",
            title=f"Scheduled: {desc[:60]}",
            description=f"Schedule this task automatically (seen {pattern.occurrences}x)",
            trigger="scheduled",
            action_spec={"pattern_description": desc},
        )

    if ptype == "calendar_habit":
        return AutomationProposal(
            pattern=pattern,
            action_type="calendar_automation",
            title=f"Calendar auto: {desc[:60]}",
            description=f"Automate calendar action (seen {pattern.occurrences}x)",
            trigger="on_calendar_event",
            action_spec={"pattern_description": desc},
        )

    if ptype == "action_sequence":
        return AutomationProposal(
            pattern=pattern,
            action_type="action_chain",
            title=f"Chain: {desc[:60]}",
            description=f"Auto-chain actions (seen {pattern.occurrences}x)",
            trigger="on_action_complete",
            action_spec={"pattern_description": desc},
        )

    return None

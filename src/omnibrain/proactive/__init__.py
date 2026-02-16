"""OmniBrain proactive engine — scheduler, briefing, patterns, priorities."""

from omnibrain.proactive.engine import (
    NotificationLevel,
    ProactiveEngine,
    ScheduledTask,
)
from omnibrain.proactive.patterns import (
    AutomationProposal,
    DetectedPattern,
    PatternDetector,
)
from omnibrain.proactive.scorer import (
    NotificationLevelSelector,
    PriorityScore,
    PriorityScorer,
    ScoreBreakdown,
    ScoringSignals,
)

__all__ = [
    "AutomationProposal",
    "DetectedPattern",
    "NotificationLevel",
    "NotificationLevelSelector",
    "PatternDetector",
    "PriorityScore",
    "PriorityScorer",
    "ProactiveEngine",
    "ScheduledTask",
    "ScoreBreakdown",
    "ScoringSignals",
]

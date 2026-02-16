"""
OmniBrain — Prompt Injection Sanitizer

Sanitizes external input (emails, calendar events, Telegram messages)
before it reaches LLM prompts. This is a critical security layer.

Threat model:
    1. Malicious email body contains "IGNORE PREVIOUS INSTRUCTIONS..."
    2. Calendar event title contains system prompt overrides
    3. Contact names/subjects contain role-play injections
    4. URLs or code blocks containing encoded instructions

Approach:
    - Pattern-based detection (known attack vectors)
    - Structural analysis (instruction-like patterns)
    - Sandboxing (wrap external content in clear delimiters)
    - Score-based escalation (suspicious → block)

Usage:
    sanitizer = PromptSanitizer()
    result = sanitizer.sanitize(user_input)
    if result.is_blocked:
        log.warning(f"Blocked input: {result.reason}")
    else:
        safe_text = result.safe_text
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("omnibrain.prompt_injection")


# ═══════════════════════════════════════════════════════════════════════════
# Detection Patterns
# ═══════════════════════════════════════════════════════════════════════════

# Instruction override patterns — common prompt injection vectors
INSTRUCTION_PATTERNS: list[tuple[str, float, str]] = [
    # (regex, threat_score, description)
    (r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?|rules?)", 0.9, "Instruction override attempt"),
    (r"disregard\s+(all\s+)?previous\s+(instructions?|context|rules?)", 0.9, "Instruction disregard attempt"),
    (r"forget\s+(all\s+)?previous\s+(instructions?|context|rules?)", 0.9, "Memory reset attempt"),
    (r"you\s+are\s+now\s+(?:a|an|the)\s+\w+", 0.7, "Role reassignment attempt"),
    (r"new\s+instructions?:\s*", 0.8, "New instruction injection"),
    (r"system\s*:\s*you\s+are", 0.9, "System prompt injection"),
    (r"<\|?(?:system|assistant|user)\|?>", 0.9, "Chat template injection"),
    (r"\[(?:INST|SYS)\]", 0.8, "Instruction tag injection"),
    (r"(?:act|behave|respond)\s+as\s+(?:if\s+)?(?:you\s+(?:are|were))?", 0.6, "Behavior override attempt"),
    (r"pretend\s+(?:you\s+are|to\s+be)", 0.7, "Role-play injection"),
    (r"do\s+not\s+follow\s+(?:your|the)\s+(?:instructions?|rules?|guidelines?)", 0.9, "Rule bypass attempt"),
    (r"override\s+(?:your|the|all)\s+(?:instructions?|rules?|settings?)", 0.9, "Override attempt"),
    (r"(?:reveal|show|print|output)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?|rules?)", 0.8, "Prompt extraction attempt"),
    (r"what\s+(?:are|is)\s+your\s+(?:system\s+)?(?:prompt|instructions?|rules?)", 0.5, "Prompt probing"),
    (r"(?:base64|hex|rot13)\s*(?:decode|encode)", 0.4, "Encoding manipulation"),
    (r"```(?:system|instruction|prompt)", 0.7, "Code block injection"),
    (r"BEGIN\s+(?:SYSTEM|INSTRUCTION|OVERRIDE)", 0.9, "Instruction block injection"),
    (r"END\s+(?:SYSTEM|INSTRUCTION)", 0.6, "Instruction block terminator"),
]

# Structural patterns that indicate suspicious formatting
STRUCTURAL_PATTERNS: list[tuple[str, float, str]] = [
    (r"^#{1,3}\s+system\s+(?:prompt|message|instruction)", 0.8, "Markdown system header"),
    (r"(?:---+|===+)\s*\n.*(?:instruction|system|prompt)", 0.5, "Markdown divider + instruction"),
    (r"\n{3,}.*(?:ignore|disregard|forget)\s+(?:everything|all)", 0.7, "Whitespace padding + override"),
]

# Block threshold — inputs scoring above this are rejected
BLOCK_THRESHOLD = 0.8

# Warn threshold — inputs scoring above this are flagged
WARN_THRESHOLD = 0.4


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ThreatMatch:
    """A single detected threat pattern."""

    pattern: str
    score: float
    description: str
    matched_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "score": self.score,
            "description": self.description,
            "matched_text": self.matched_text[:100],  # Truncate for safety
        }


@dataclass
class SanitizeResult:
    """Result of sanitization analysis."""

    original_text: str
    safe_text: str
    threat_score: float = 0.0
    threats: list[ThreatMatch] = field(default_factory=list)
    is_blocked: bool = False
    is_warned: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_score": round(self.threat_score, 3),
            "is_blocked": self.is_blocked,
            "is_warned": self.is_warned,
            "reason": self.reason,
            "threat_count": len(self.threats),
            "threats": [t.to_dict() for t in self.threats],
        }


# ═══════════════════════════════════════════════════════════════════════════
# Sanitizer
# ═══════════════════════════════════════════════════════════════════════════


class PromptSanitizer:
    """Sanitizes external input before LLM prompt injection.

    Three-layer defense:
        1. Pattern detection (regex-based threat scoring)
        2. Structural analysis (suspicious formatting)
        3. Content sandboxing (wrap in safe delimiters)

    Usage:
        sanitizer = PromptSanitizer()
        result = sanitizer.sanitize(email_body)
        if result.is_blocked:
            log_threat(result)
        else:
            prompt = f"Analyze this email: {result.safe_text}"
    """

    def __init__(
        self,
        block_threshold: float = BLOCK_THRESHOLD,
        warn_threshold: float = WARN_THRESHOLD,
        custom_patterns: list[tuple[str, float, str]] | None = None,
    ):
        self._block_threshold = block_threshold
        self._warn_threshold = warn_threshold
        self._patterns = INSTRUCTION_PATTERNS + STRUCTURAL_PATTERNS
        if custom_patterns:
            self._patterns = self._patterns + custom_patterns

    def sanitize(self, text: str, source: str = "unknown") -> SanitizeResult:
        """Sanitize external text for safe LLM prompt inclusion.

        Args:
            text: The raw external input.
            source: Where the text came from (email, calendar, telegram, etc.)

        Returns:
            SanitizeResult with safe_text, threat_score, blocking decision.
        """
        if not text or not text.strip():
            return SanitizeResult(
                original_text=text or "",
                safe_text=text or "",
                threat_score=0.0,
            )

        threats = self._detect_threats(text)
        threat_score = self._compute_score(threats)

        is_blocked = threat_score >= self._block_threshold
        is_warned = threat_score >= self._warn_threshold and not is_blocked

        reason = ""
        if is_blocked:
            top = max(threats, key=lambda t: t.score)
            reason = f"BLOCKED ({source}): {top.description} (score={threat_score:.2f})"
            logger.warning(reason)
        elif is_warned:
            reason = f"WARNING ({source}): {len(threats)} suspicious pattern(s) (score={threat_score:.2f})"
            logger.info(reason)

        safe_text = self._sandbox(text, source) if not is_blocked else "[CONTENT BLOCKED — potential prompt injection]"

        return SanitizeResult(
            original_text=text,
            safe_text=safe_text,
            threat_score=threat_score,
            threats=threats,
            is_blocked=is_blocked,
            is_warned=is_warned,
            reason=reason,
        )

    def sanitize_email(self, subject: str, body: str, sender: str = "") -> SanitizeResult:
        """Sanitize email content — checks subject + body combined."""
        combined = f"Subject: {subject}\nFrom: {sender}\n\n{body}"
        return self.sanitize(combined, source="email")

    def sanitize_calendar(self, title: str, description: str = "") -> SanitizeResult:
        """Sanitize calendar event content."""
        combined = f"Event: {title}\n{description}" if description else title
        return self.sanitize(combined, source="calendar")

    def sanitize_message(self, text: str) -> SanitizeResult:
        """Sanitize a chat/Telegram message."""
        return self.sanitize(text, source="telegram")

    def is_safe(self, text: str) -> bool:
        """Quick check — returns True if text passes sanitization."""
        return not self.sanitize(text).is_blocked

    def get_threat_score(self, text: str) -> float:
        """Get threat score without full sanitization."""
        threats = self._detect_threats(text)
        return self._compute_score(threats)

    # ── Internal ──

    def _detect_threats(self, text: str) -> list[ThreatMatch]:
        """Run all patterns against the text."""
        threats: list[ThreatMatch] = []
        text_lower = text.lower()

        for pattern, score, description in self._patterns:
            try:
                matches = re.finditer(pattern, text_lower, re.MULTILINE | re.IGNORECASE)
                for match in matches:
                    threats.append(ThreatMatch(
                        pattern=pattern,
                        score=score,
                        description=description,
                        matched_text=match.group(0),
                    ))
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")

        return threats

    def _compute_score(self, threats: list[ThreatMatch]) -> float:
        """Compute aggregate threat score.

        Uses max + attenuation for multiple threats:
        score = max_score + 0.1 * (num_additional_threats)
        Capped at 1.0.
        """
        if not threats:
            return 0.0

        max_score = max(t.score for t in threats)
        additional = len(threats) - 1
        score = max_score + 0.1 * additional
        return min(score, 1.0)

    def _sandbox(self, text: str, source: str) -> str:
        """Wrap external content in safe delimiters.

        This makes it clear to the LLM that the content is external/untrusted.
        """
        # Strip any attempt to close the sandbox
        safe = text.replace("---END EXTERNAL---", "")
        safe = safe.replace("---BEGIN EXTERNAL---", "")

        return (
            f"---BEGIN EXTERNAL CONTENT (source: {source})---\n"
            f"{safe}\n"
            f"---END EXTERNAL CONTENT---"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════


# Module-level default instance
_default_sanitizer = PromptSanitizer()


def sanitize(text: str, source: str = "unknown") -> SanitizeResult:
    """Module-level sanitize using default configuration."""
    return _default_sanitizer.sanitize(text, source)


def is_safe(text: str) -> bool:
    """Module-level safety check."""
    return _default_sanitizer.is_safe(text)


def sanitize_email(subject: str, body: str, sender: str = "") -> SanitizeResult:
    """Module-level email sanitizer."""
    return _default_sanitizer.sanitize_email(subject, body, sender)

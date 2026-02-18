"""
OmniBrain — Behavioral Preference Model

Learns how the user communicates, works, and prioritizes — automatically,
from every interaction.

The ``BehavioralProfile`` is the user's digital behavioral fingerprint:
    - Communication style: formality, greetings, sign-offs, language
    - Work patterns: active hours, peak productivity, meeting density
    - Priorities: response urgency per contact, topic importance
    - Relationships: inner circle, response patterns, delegation targets
    - Commitments: promises tracked from conversations

The profile is *never* revealed to external parties — it only feeds the
system prompt and the proactive engine.

Storage: serialized as JSON blob in ``preferences`` table
(key = ``"behavioral_profile"``).

Architecture::

    Data Sources
    ├── Email analysis      → writing_formality, greetings, sign_offs
    ├── Calendar events     → meeting_density, active_hours
    ├── Chat messages       → explicit preferences, commitments
    ├── Action approvals    → topic_importance, response_urgency
    └── Pattern detector    → active_hours, peak_productivity
              │
              ▼
    PreferenceModel
    ├── update_from_email()
    ├── update_from_calendar()
    ├── update_from_chat()
    ├── update_from_approval()
    ├── update_from_patterns()
    ├── track_commitment()
    ├── check_commitments()
    └── to_system_prompt()      → injected into agent system prompt
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("omnibrain.preference_model")


# ═══════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Commitment:
    """A promise the user made in conversation."""

    text: str                               # "send pricing doc to Marco"
    recipient: str = ""                     # who it's promised to
    deadline: datetime | None = None        # when it's due
    detected_at: datetime = field(default_factory=datetime.now)
    fulfilled: bool = False
    fulfilled_at: datetime | None = None

    def is_overdue(self) -> bool:
        if self.fulfilled or self.deadline is None:
            return False
        return datetime.now() > self.deadline

    def hours_until_deadline(self) -> float | None:
        if self.deadline is None:
            return None
        delta = self.deadline - datetime.now()
        return delta.total_seconds() / 3600

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "recipient": self.recipient,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "detected_at": self.detected_at.isoformat(),
            "fulfilled": self.fulfilled,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Commitment:
        return cls(
            text=data["text"],
            recipient=data.get("recipient", ""),
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            detected_at=datetime.fromisoformat(data.get("detected_at", datetime.now().isoformat())),
            fulfilled=data.get("fulfilled", False),
            fulfilled_at=datetime.fromisoformat(data["fulfilled_at"]) if data.get("fulfilled_at") else None,
        )


@dataclass
class BehavioralProfile:
    """Learned behavioral model — evolves over time.

    Every field uses sensible defaults. The model gradually converges
    as more data flows in. Fields are updated via exponential moving
    average (EMA) to weight recent behavior more heavily.
    """

    # ── Communication style ──
    writing_formality: float = 0.5      # 0=casual, 1=formal
    avg_response_length: int = 0        # in words
    common_greetings: list[str] = field(default_factory=list)
    sign_off_style: str = ""            # "Best", "Cheers", "—F"
    language_preference: str = "en"
    emoji_usage: float = 0.0            # 0=never, 1=heavy

    # ── Work patterns ──
    active_hours: list[tuple[int, int]] = field(default_factory=list)   # [(9,12), (14,18)]
    peak_productivity_hour: int = 10
    meeting_density_preferred: float = 0.3  # 0=no meetings, 1=all meetings
    avg_daily_emails_sent: float = 0.0
    avg_daily_meetings: float = 0.0

    # ── Priorities ──
    response_urgency: dict[str, float] = field(default_factory=dict)    # contact→urgency (0-1)
    topic_importance: dict[str, float] = field(default_factory=dict)    # topic→importance (0-1)

    # ── Relationships ──
    inner_circle: list[str] = field(default_factory=list)               # top contacts
    response_patterns: dict[str, float] = field(default_factory=dict)   # contact→avg_reply_hours
    delegation_targets: dict[str, list[str]] = field(default_factory=dict)  # topic→[contacts]

    # ── Commitments ──
    commitments: list[Commitment] = field(default_factory=list)

    # ── Meta ──
    total_emails_analyzed: int = 0
    total_chats_analyzed: int = 0
    total_approvals_analyzed: int = 0
    last_updated: str = ""

    # ── Serialization ──

    def to_dict(self) -> dict[str, Any]:
        return {
            "writing_formality": self.writing_formality,
            "avg_response_length": self.avg_response_length,
            "common_greetings": self.common_greetings,
            "sign_off_style": self.sign_off_style,
            "language_preference": self.language_preference,
            "emoji_usage": self.emoji_usage,
            "active_hours": self.active_hours,
            "peak_productivity_hour": self.peak_productivity_hour,
            "meeting_density_preferred": self.meeting_density_preferred,
            "avg_daily_emails_sent": self.avg_daily_emails_sent,
            "avg_daily_meetings": self.avg_daily_meetings,
            "response_urgency": self.response_urgency,
            "topic_importance": self.topic_importance,
            "inner_circle": self.inner_circle,
            "response_patterns": self.response_patterns,
            "delegation_targets": self.delegation_targets,
            "commitments": [c.to_dict() for c in self.commitments],
            "total_emails_analyzed": self.total_emails_analyzed,
            "total_chats_analyzed": self.total_chats_analyzed,
            "total_approvals_analyzed": self.total_approvals_analyzed,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BehavioralProfile:
        commitments = [
            Commitment.from_dict(c) for c in data.get("commitments", [])
        ]
        active_hours = [
            tuple(pair) for pair in data.get("active_hours", [])
        ]
        return cls(
            writing_formality=data.get("writing_formality", 0.5),
            avg_response_length=data.get("avg_response_length", 0),
            common_greetings=data.get("common_greetings", []),
            sign_off_style=data.get("sign_off_style", ""),
            language_preference=data.get("language_preference", "en"),
            emoji_usage=data.get("emoji_usage", 0.0),
            active_hours=active_hours,
            peak_productivity_hour=data.get("peak_productivity_hour", 10),
            meeting_density_preferred=data.get("meeting_density_preferred", 0.3),
            avg_daily_emails_sent=data.get("avg_daily_emails_sent", 0.0),
            avg_daily_meetings=data.get("avg_daily_meetings", 0.0),
            response_urgency=data.get("response_urgency", {}),
            topic_importance=data.get("topic_importance", {}),
            inner_circle=data.get("inner_circle", []),
            response_patterns=data.get("response_patterns", {}),
            delegation_targets=data.get("delegation_targets", {}),
            commitments=commitments,
            total_emails_analyzed=data.get("total_emails_analyzed", 0),
            total_chats_analyzed=data.get("total_chats_analyzed", 0),
            total_approvals_analyzed=data.get("total_approvals_analyzed", 0),
            last_updated=data.get("last_updated", ""),
        )


# ═══════════════════════════════════════════════════════════════════════════
# EMA (Exponential Moving Average) Helper
# ═══════════════════════════════════════════════════════════════════════════


def _ema(old: float, new: float, alpha: float = 0.1) -> float:
    """Exponential moving average — weights recent data more heavily.

    alpha=0.1 → 10% new data, 90% old
    alpha=0.3 → 30% new data, 70% old
    """
    return round(old * (1 - alpha) + new * alpha, 4)


def _update_top_n(lst: list[str], item: str, max_n: int = 10) -> list[str]:
    """Add item to list if not present; keep max_n most recent."""
    if item in lst:
        lst.remove(item)
    lst.insert(0, item)
    return lst[:max_n]


def _update_frequency_dict(
    d: dict[str, float], key: str, value: float, alpha: float = 0.1
) -> None:
    """Update a frequency/score dict with EMA."""
    if key in d:
        d[key] = _ema(d[key], value, alpha)
    else:
        d[key] = value


# ═══════════════════════════════════════════════════════════════════════════
# Preference Model
# ═══════════════════════════════════════════════════════════════════════════


class PreferenceModel:
    """Manages the BehavioralProfile lifecycle — learns, persists, queries.

    Usage::

        model = PreferenceModel(db)

        # Learn from data
        model.update_from_email(sender, body, reply_time_hours)
        model.update_from_calendar(events_today)
        model.update_from_chat(message_text)
        model.update_from_approval(action_type, approved=True)

        # Track commitments
        model.track_commitment("send pricing to Marco", "Marco", deadline)
        overdue = model.check_commitments()

        # Generate system prompt fragment
        prompt_fragment = model.to_system_prompt()
    """

    PROFILE_KEY = "behavioral_profile"

    def __init__(self, db: Any) -> None:
        self._db = db
        self._profile: BehavioralProfile | None = None

    @property
    def profile(self) -> BehavioralProfile:
        """Get or load the behavioral profile."""
        if self._profile is None:
            self._load()
        return self._profile

    def _load(self) -> None:
        """Load profile from DB preferences table."""
        data = self._db.get_preference(self.PROFILE_KEY)
        if data and isinstance(data, dict):
            self._profile = BehavioralProfile.from_dict(data)
            logger.debug("Loaded behavioral profile from DB")
        else:
            self._profile = BehavioralProfile()
            logger.info("Created new behavioral profile")

    def _save(self) -> None:
        """Persist profile to DB."""
        p = self.profile
        p.last_updated = datetime.now().isoformat()
        self._db.set_preference(
            self.PROFILE_KEY,
            p.to_dict(),
            confidence=0.9,
            learned_from="behavioral_model",
        )

    # ──────────────────────────────────────────────────────────
    # Update methods — called from various data pipelines
    # ──────────────────────────────────────────────────────────

    def update_from_email(
        self,
        sender: str,
        body: str,
        reply_time_hours: float | None = None,
        is_outgoing: bool = False,
    ) -> None:
        """Learn from an email — communication style, relationships, response time."""
        p = self.profile

        if is_outgoing and body:
            # Analyze formality
            formality = _estimate_formality(body)
            p.writing_formality = _ema(p.writing_formality, formality)

            # Word count
            word_count = len(body.split())
            if p.avg_response_length > 0:
                p.avg_response_length = int(_ema(p.avg_response_length, word_count, 0.05))
            else:
                p.avg_response_length = word_count

            # Greetings
            greeting = _extract_greeting(body)
            if greeting:
                p.common_greetings = _update_top_n(p.common_greetings, greeting, 5)

            # Sign-off
            sign_off = _extract_sign_off(body)
            if sign_off:
                p.sign_off_style = sign_off

            # Language detection
            lang = _detect_language(body)
            if lang:
                p.language_preference = lang

            # Emoji usage
            emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]|[😀-🙏]|[:;]-?[)(/|\\]", body))
            emoji_ratio = min(emoji_count / max(word_count, 1), 1.0)
            p.emoji_usage = _ema(p.emoji_usage, emoji_ratio)

        # Response time tracking
        if reply_time_hours is not None and sender:
            _update_frequency_dict(p.response_patterns, sender, reply_time_hours, 0.15)

            # Urgency: faster response → higher urgency
            urgency = max(0.0, 1.0 - (reply_time_hours / 24))
            _update_frequency_dict(p.response_urgency, sender, urgency, 0.15)

        # Inner circle: contacts with most interactions
        if sender and sender not in p.inner_circle:
            # We'll rebuild inner circle periodically, but track all contacts
            pass

        p.total_emails_analyzed += 1

        # Save periodically (every 10 emails)
        if p.total_emails_analyzed % 10 == 0:
            self._save()

    def update_from_calendar(
        self,
        events_today: list[dict[str, Any]],
    ) -> None:
        """Learn from today's calendar — meeting density, active hours."""
        p = self.profile

        if not events_today:
            return

        # Meeting density: meetings per 8-hour workday
        meeting_count = len(events_today)
        density = min(meeting_count / 8, 1.0)
        p.meeting_density_preferred = _ema(p.meeting_density_preferred, density, 0.1)

        # Daily meetings average
        p.avg_daily_meetings = _ema(p.avg_daily_meetings, meeting_count, 0.1)

        # Active hours detection from meeting start times
        hours_active = set()
        for event in events_today:
            start_str = event.get("start") or event.get("start_time", "")
            if start_str:
                try:
                    start = datetime.fromisoformat(start_str)
                    hours_active.add(start.hour)
                except (ValueError, TypeError):
                    pass

        if hours_active:
            # Merge hours into contiguous ranges
            sorted_hours = sorted(hours_active)
            ranges = _hours_to_ranges(sorted_hours)
            if ranges:
                p.active_hours = ranges

        self._save()

    def update_from_chat(self, message_text: str) -> None:
        """Learn from a chat message — explicit preferences, commitments."""
        p = self.profile

        # Detect explicit preferences
        prefs = _extract_explicit_preferences(message_text)
        for key, value in prefs.items():
            if key == "language":
                p.language_preference = value
            elif key == "timezone":
                pass  # handled by config, not profile

        # Detect commitments
        commitment = _extract_commitment(message_text)
        if commitment:
            p.commitments.append(commitment)
            logger.info(f"Commitment detected: {commitment.text}")

        p.total_chats_analyzed += 1

        if p.total_chats_analyzed % 5 == 0:
            self._save()

    def update_from_approval(
        self,
        action_type: str,
        approved: bool,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Learn from approval/rejection — topic importance, delegation patterns."""
        p = self.profile
        ctx = context or {}

        # Topic importance: approved actions increase, rejected decrease
        topic = ctx.get("topic", action_type)
        current = p.topic_importance.get(topic, 0.5)
        adjustment = 0.7 if approved else 0.3
        p.topic_importance[topic] = _ema(current, adjustment, 0.2)

        # Delegation patterns from forwarding/assigning
        if approved and action_type in ("forward_email", "assign_task"):
            target = ctx.get("target_contact", "")
            topic_key = ctx.get("topic", "general")
            if target:
                if topic_key not in p.delegation_targets:
                    p.delegation_targets[topic_key] = []
                if target not in p.delegation_targets[topic_key]:
                    p.delegation_targets[topic_key].append(target)

        p.total_approvals_analyzed += 1
        self._save()

    def update_from_patterns(
        self,
        active_hours: list[tuple[int, int]] | None = None,
        peak_hour: int | None = None,
    ) -> None:
        """Integrate signals from the PatternDetector."""
        p = self.profile

        if active_hours:
            p.active_hours = active_hours
        if peak_hour is not None:
            p.peak_productivity_hour = peak_hour

        self._save()

    # ──────────────────────────────────────────────────────────
    # Inner circle computation
    # ──────────────────────────────────────────────────────────

    def rebuild_inner_circle(self, top_n: int = 10) -> list[str]:
        """Rebuild inner circle from response patterns.

        Contacts with fastest response times and highest volume are inner circle.
        """
        p = self.profile

        if not p.response_patterns:
            return p.inner_circle

        # Score: lower response time + higher urgency = higher score
        scores: dict[str, float] = {}
        for contact, avg_hours in p.response_patterns.items():
            urgency = p.response_urgency.get(contact, 0.5)
            speed_score = max(0, 1 - (avg_hours / 48))
            scores[contact] = speed_score * 0.6 + urgency * 0.4

        ranked = sorted(scores, key=scores.get, reverse=True)
        p.inner_circle = ranked[:top_n]
        self._save()
        return p.inner_circle

    # ──────────────────────────────────────────────────────────
    # Commitments
    # ──────────────────────────────────────────────────────────

    def track_commitment(
        self,
        text: str,
        recipient: str = "",
        deadline: datetime | None = None,
    ) -> Commitment:
        """Manually track a commitment."""
        c = Commitment(
            text=text,
            recipient=recipient,
            deadline=deadline,
        )
        self.profile.commitments.append(c)
        self._save()
        return c

    def fulfill_commitment(self, index: int) -> bool:
        """Mark a commitment as fulfilled."""
        p = self.profile
        if 0 <= index < len(p.commitments):
            p.commitments[index].fulfilled = True
            p.commitments[index].fulfilled_at = datetime.now()
            self._save()
            return True
        return False

    def check_commitments(self) -> list[Commitment]:
        """Return overdue commitments."""
        return [c for c in self.profile.commitments if c.is_overdue()]

    def get_upcoming_commitments(self, hours: float = 24) -> list[Commitment]:
        """Return commitments due within *hours*."""
        now = datetime.now()
        cutoff = now + timedelta(hours=hours)
        return [
            c for c in self.profile.commitments
            if not c.fulfilled and c.deadline and now < c.deadline <= cutoff
        ]

    def prune_old_commitments(self, days: int = 30) -> int:
        """Remove fulfilled commitments older than *days*."""
        p = self.profile
        cutoff = datetime.now() - timedelta(days=days)
        before = len(p.commitments)
        p.commitments = [
            c for c in p.commitments
            if not (c.fulfilled and c.detected_at < cutoff)
        ]
        removed = before - len(p.commitments)
        if removed > 0:
            self._save()
        return removed

    # ──────────────────────────────────────────────────────────
    # System prompt generation
    # ──────────────────────────────────────────────────────────

    def to_system_prompt(self) -> str:
        """Generate a system prompt fragment describing the user's behavioral profile.

        Injected into the agent's system prompt to personalize responses.
        """
        p = self.profile
        lines: list[str] = ["## Your User's Behavioral Profile"]

        # Communication
        formality_desc = "formally" if p.writing_formality > 0.65 else (
            "casually" if p.writing_formality < 0.35 else "mixed formal/casual"
        )
        lines.append(f"- Writes {formality_desc}")

        if p.avg_response_length:
            lines.append(f"- Average response length: ~{p.avg_response_length} words")

        if p.common_greetings:
            greetings = ", ".join(f'"{g}"' for g in p.common_greetings[:3])
            lines.append(f"- Common greetings: {greetings}")

        if p.sign_off_style:
            lines.append(f'- Signs off with: "{p.sign_off_style}"')

        lines.append(f"- Primary language: {p.language_preference}")

        # Work patterns
        if p.active_hours:
            hours_str = ", ".join(f"{s}-{e}" for s, e in p.active_hours)
            lines.append(f"- Active hours: {hours_str}")
            lines.append(f"- Peak productivity: {p.peak_productivity_hour}:00")

        if p.avg_daily_meetings > 0:
            lines.append(f"- Average {p.avg_daily_meetings:.1f} meetings/day")

        # Inner circle
        if p.inner_circle:
            names = ", ".join(p.inner_circle[:5])
            lines.append(f"- Inner circle: {names}")

        # Response patterns
        if p.response_patterns:
            fast_contacts = sorted(p.response_patterns.items(), key=lambda x: x[1])[:3]
            for contact, hours in fast_contacts:
                if hours < 2:
                    lines.append(f"- Responds to {contact} within {hours:.0f}h")

        # Priorities
        if p.topic_importance:
            sorted_topics = sorted(p.topic_importance.items(), key=lambda x: x[1], reverse=True)
            top_topics = [t[0] for t in sorted_topics[:3]]
            if top_topics:
                lines.append(f"- Priorities: {' > '.join(top_topics)}")

        # Delegation
        if p.delegation_targets:
            for topic, targets in list(p.delegation_targets.items())[:2]:
                lines.append(f"- Delegates {topic} to {', '.join(targets[:2])}")

        # Active commitments
        active = [c for c in p.commitments if not c.fulfilled]
        if active:
            lines.append(f"\n### Active Commitments ({len(active)})")
            for c in active[:5]:
                deadline_str = f" (due: {c.deadline.strftime('%a %b %d')})" if c.deadline else ""
                overdue = " ⚠️ OVERDUE" if c.is_overdue() else ""
                lines.append(f"- {c.text}{deadline_str}{overdue}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Text Analysis Helpers
# ═══════════════════════════════════════════════════════════════════════════


# Formal indicators
_FORMAL_MARKERS = {
    "dear", "sincerely", "regards", "respectfully", "cordially",
    "pleased", "appreciate", "kindly", "herewith", "pursuant",
    "accordingly", "furthermore", "therefore", "enclosed",
}

# Casual indicators
_CASUAL_MARKERS = {
    "hey", "hi", "yo", "sup", "lol", "haha", "yeah", "yep",
    "nope", "cool", "awesome", "gonna", "wanna", "gotta",
    "btw", "fyi", "imo", "ngl", "tbh",
}


def _estimate_formality(text: str) -> float:
    """Estimate text formality on a 0-1 scale.

    Uses a bag-of-markers approach with sentence structure signals.
    """
    words = text.lower().split()
    if not words:
        return 0.5

    word_set = set(words)
    formal_count = len(word_set & _FORMAL_MARKERS)
    casual_count = len(word_set & _CASUAL_MARKERS)

    # Sentence length as formality signal
    sentences = re.split(r"[.!?]+", text)
    avg_sentence_len = sum(len(s.split()) for s in sentences if s.strip()) / max(len(sentences), 1)
    length_signal = min(avg_sentence_len / 20, 1.0)  # longer = more formal

    # Contraction detection (informal)
    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    contraction_ratio = contractions / max(len(words), 1)

    # Combine signals
    marker_score = (formal_count - casual_count) / max(formal_count + casual_count, 1)
    marker_score = (marker_score + 1) / 2  # normalize to 0-1

    formality = (marker_score * 0.5 + length_signal * 0.3 + (1 - contraction_ratio) * 0.2)
    return max(0.0, min(1.0, formality))


def _extract_greeting(text: str) -> str | None:
    """Extract the opening greeting from text."""
    first_line = text.strip().split("\n")[0].strip()
    patterns = [
        r"^(Dear\s+\w+)",
        r"^(Hi\s+\w+)",
        r"^(Hey\s*\w*)",
        r"^(Hello\s*\w*)",
        r"^(Ciao\s*\w*)",
        r"^(Buongiorno\s*\w*)",
        r"^(Good\s+(?:morning|afternoon|evening)\s*\w*)",
    ]
    for pattern in patterns:
        m = re.match(pattern, first_line, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(",")
    return None


def _extract_sign_off(text: str) -> str | None:
    """Extract the closing sign-off."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if len(lines) < 2:
        return None

    # Check last 3 lines for sign-off patterns
    for line in reversed(lines[-3:]):
        patterns = [
            r"^(Best\s*(?:regards)?)",
            r"^(Kind\s*regards)",
            r"^(Regards)",
            r"^(Cheers)",
            r"^(Thanks)",
            r"^(Thank\s*you)",
            r"^(Sincerely)",
            r"^(Cordiali\s*saluti)",
            r"^(A\s*presto)",
            r"^(—\s*\w+)",  # —F, —Francesco
            r"^(-\s*\w+)",  # -F
        ]
        for pattern in patterns:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                return m.group(1).strip().rstrip(",")
    return None


def _detect_language(text: str) -> str | None:
    """Simple language detection from common words."""
    text_lower = text.lower()
    words = set(text_lower.split())

    italian = {"ciao", "buongiorno", "grazie", "saluti", "cordiali",
               "presto", "anche", "sono", "questo", "della", "nella"}
    english = {"the", "and", "this", "that", "with", "from",
               "your", "have", "been", "would", "could"}
    spanish = {"hola", "gracias", "buenos", "días", "señor",
               "también", "este", "como", "para", "con"}
    german = {"danke", "sehr", "geehrte", "freundlichen", "grüße",
              "bitte", "diese", "nicht", "haben", "werden"}

    scores = {
        "it": len(words & italian),
        "en": len(words & english),
        "es": len(words & spanish),
        "de": len(words & german),
    }

    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return None


def _hours_to_ranges(hours: list[int]) -> list[tuple[int, int]]:
    """Convert a sorted list of hours to contiguous ranges.

    [9, 10, 11, 14, 15, 16] → [(9, 12), (14, 17)]
    """
    if not hours:
        return []

    ranges = []
    start = hours[0]
    end = hours[0]

    for h in hours[1:]:
        if h <= end + 1:
            end = h
        else:
            ranges.append((start, end + 1))
            start = h
            end = h

    ranges.append((start, end + 1))
    return ranges


# ── Commitment extraction ──

_COMMITMENT_PATTERNS = [
    # "I'll send X by/before/on Friday"
    r"I(?:'ll| will)\s+(.{5,60}?)\s+(?:by|before|on)\s+(\w+(?:\s+\w+)?)",
    # "I promise to X"
    r"I\s+promise\s+to\s+(.{5,60})",
    # "I'll get back to X"
    r"I(?:'ll| will)\s+get\s+back\s+to\s+(\w+)",
    # "Let me X by Friday"
    r"Let\s+me\s+(.{5,60}?)\s+(?:by|before|on)\s+(\w+(?:\s+\w+)?)",
]

_DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "tomorrow": -1, "today": -2,
}


def _parse_deadline(text: str) -> datetime | None:
    """Parse a fuzzy deadline like 'Friday' or 'tomorrow'."""
    text_lower = text.lower().strip()
    now = datetime.now()

    if text_lower in ("today", "tonight"):
        return now.replace(hour=23, minute=59)

    if text_lower == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=18, minute=0)

    # Day name → next occurrence
    for day_name, day_num in _DAY_NAMES.items():
        if day_name in text_lower:
            if day_num < 0:
                continue  # handled above
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (now + timedelta(days=days_ahead)).replace(hour=18, minute=0)

    return None


def _extract_commitment(text: str) -> Commitment | None:
    """Extract a commitment from chat text."""
    for pattern in _COMMITMENT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = m.groups()
            action_text = groups[0].strip()
            deadline_text = groups[1] if len(groups) > 1 else None
            deadline = _parse_deadline(deadline_text) if deadline_text else None

            # Try to extract recipient
            recipient = ""
            recip_match = re.search(r"to\s+(\w+)", action_text)
            if recip_match:
                recipient = recip_match.group(1)

            return Commitment(
                text=action_text,
                recipient=recipient,
                deadline=deadline,
            )
    return None


def _extract_explicit_preferences(text: str) -> dict[str, str]:
    """Extract explicit preference statements from chat.

    E.g. "I prefer Italian", "Please use dark mode", "My timezone is CET"
    """
    prefs: dict[str, str] = {}

    # Language preference
    lang_match = re.search(
        r"(?:prefer|use|speak|write\s+in)\s+(Italian|English|Spanish|German|French)",
        text,
        re.IGNORECASE,
    )
    if lang_match:
        lang_map = {
            "italian": "it", "english": "en", "spanish": "es",
            "german": "de", "french": "fr",
        }
        prefs["language"] = lang_map.get(lang_match.group(1).lower(), "en")

    return prefs

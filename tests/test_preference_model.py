"""
Tests for Behavioral Preference Model — BehavioralProfile, PreferenceModel,
commitment tracking, text analysis, and system prompt generation.

Groups:
    BehavioralProfile  — serialization, defaults
    TextAnalysis       — formality, greetings, sign-offs, language detection
    Commitments        — tracking, deadlines, overdue detection
    PreferenceModel    — update_from_*, to_system_prompt
    TemporalPatterns   — day-of-week and time-of-day pattern detection
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from omnibrain.preference_model import (
    BehavioralProfile,
    Commitment,
    PreferenceModel,
    _detect_language,
    _ema,
    _estimate_formality,
    _extract_commitment,
    _extract_greeting,
    _extract_sign_off,
    _hours_to_ranges,
    _update_top_n,
)


# ═══════════════════════════════════════════════════════════════════════════
# BehavioralProfile
# ═══════════════════════════════════════════════════════════════════════════


class TestBehavioralProfile:
    def test_default_values(self):
        p = BehavioralProfile()
        assert p.writing_formality == 0.5
        assert p.language_preference == "en"
        assert p.inner_circle == []
        assert p.commitments == []

    def test_round_trip_serialization(self):
        p = BehavioralProfile(
            writing_formality=0.8,
            common_greetings=["Dear", "Hello"],
            active_hours=[(9, 12), (14, 18)],
            inner_circle=["Marco", "Luca"],
            response_patterns={"Marco": 1.5},
        )
        d = p.to_dict()
        p2 = BehavioralProfile.from_dict(d)
        assert p2.writing_formality == 0.8
        assert p2.common_greetings == ["Dear", "Hello"]
        assert p2.active_hours == [(9, 12), (14, 18)]
        assert p2.inner_circle == ["Marco", "Luca"]
        assert p2.response_patterns == {"Marco": 1.5}

    def test_from_dict_with_commitments(self):
        now = datetime.now()
        data = {
            "commitments": [{
                "text": "send report",
                "recipient": "Marco",
                "deadline": (now + timedelta(days=1)).isoformat(),
                "detected_at": now.isoformat(),
                "fulfilled": False,
            }],
        }
        p = BehavioralProfile.from_dict(data)
        assert len(p.commitments) == 1
        assert p.commitments[0].text == "send report"
        assert p.commitments[0].recipient == "Marco"


# ═══════════════════════════════════════════════════════════════════════════
# Text Analysis
# ═══════════════════════════════════════════════════════════════════════════


class TestTextAnalysis:
    def test_formality_formal(self):
        text = "Dear Mr. Smith, I appreciate your prompt response regarding the enclosed documents."
        score = _estimate_formality(text)
        assert score > 0.5  # Should be formal

    def test_formality_casual(self):
        text = "hey man, lol that's awesome! gonna grab lunch, wanna join?"
        score = _estimate_formality(text)
        assert score < 0.5  # Should be casual

    def test_formality_empty(self):
        assert _estimate_formality("") == 0.5

    def test_extract_greeting_dear(self):
        assert _extract_greeting("Dear Marco,\nhow are you?") == "Dear Marco"

    def test_extract_greeting_hi(self):
        assert _extract_greeting("Hi Sara,\nquick question") == "Hi Sara"

    def test_extract_greeting_ciao(self):
        assert _extract_greeting("Ciao Marco,\ncome stai?") == "Ciao Marco"

    def test_extract_greeting_none(self):
        assert _extract_greeting("The meeting is at 3pm") is None

    def test_extract_sign_off_best(self):
        text = "Thanks for the update.\n\nBest regards,\nFrancesco"
        assert "Best" in (_extract_sign_off(text) or "")

    def test_extract_sign_off_cheers(self):
        text = "See you tomorrow.\n\nCheers,\nF"
        assert _extract_sign_off(text) == "Cheers"

    def test_extract_sign_off_dash(self):
        text = "That works for me.\n\n—Francesco"
        result = _extract_sign_off(text)
        assert result is not None
        assert "Francesco" in result

    def test_detect_language_english(self):
        assert _detect_language("This is the report that we have been working on") == "en"

    def test_detect_language_italian(self):
        assert _detect_language("Ciao, questo è anche il report della settimana") == "it"

    def test_detect_language_ambiguous(self):
        # Single word, no clear language
        result = _detect_language("OK")
        # Could be None or any language, just shouldn't crash
        assert result is None or isinstance(result, str)


class TestHoursToRanges:
    def test_contiguous(self):
        assert _hours_to_ranges([9, 10, 11]) == [(9, 12)]

    def test_gap(self):
        assert _hours_to_ranges([9, 10, 11, 14, 15, 16]) == [(9, 12), (14, 17)]

    def test_single_hour(self):
        assert _hours_to_ranges([10]) == [(10, 11)]

    def test_empty(self):
        assert _hours_to_ranges([]) == []


class TestEMA:
    def test_basic(self):
        result = _ema(0.5, 1.0, alpha=0.1)
        assert abs(result - 0.55) < 0.001

    def test_full_weight(self):
        result = _ema(0.0, 1.0, alpha=1.0)
        assert result == 1.0

    def test_no_weight(self):
        result = _ema(0.5, 1.0, alpha=0.0)
        assert result == 0.5


class TestUpdateTopN:
    def test_add_new(self):
        result = _update_top_n(["a", "b"], "c")
        assert result == ["c", "a", "b"]

    def test_move_existing(self):
        result = _update_top_n(["a", "b", "c"], "b")
        assert result == ["b", "a", "c"]

    def test_max_n(self):
        result = _update_top_n(["a", "b"], "c", max_n=2)
        assert result == ["c", "a"]


# ═══════════════════════════════════════════════════════════════════════════
# Commitments
# ═══════════════════════════════════════════════════════════════════════════


class TestCommitments:
    def test_not_overdue(self):
        c = Commitment(text="test", deadline=datetime.now() + timedelta(days=1))
        assert c.is_overdue() is False

    def test_overdue(self):
        c = Commitment(text="test", deadline=datetime.now() - timedelta(hours=1))
        assert c.is_overdue() is True

    def test_fulfilled_not_overdue(self):
        c = Commitment(
            text="test",
            deadline=datetime.now() - timedelta(hours=1),
            fulfilled=True,
        )
        assert c.is_overdue() is False

    def test_no_deadline_not_overdue(self):
        c = Commitment(text="test")
        assert c.is_overdue() is False

    def test_hours_until_deadline(self):
        c = Commitment(text="test", deadline=datetime.now() + timedelta(hours=5))
        hours = c.hours_until_deadline()
        assert 4.9 < hours < 5.1

    def test_round_trip(self):
        c = Commitment(
            text="send report",
            recipient="Marco",
            deadline=datetime(2026, 3, 1, 18, 0),
        )
        d = c.to_dict()
        c2 = Commitment.from_dict(d)
        assert c2.text == "send report"
        assert c2.recipient == "Marco"
        assert c2.deadline == datetime(2026, 3, 1, 18, 0)

    def test_extract_commitment_will(self):
        c = _extract_commitment("I'll send the report to Marco by Friday")
        assert c is not None
        assert "report" in c.text.lower() or "send" in c.text.lower()

    def test_extract_commitment_promise(self):
        c = _extract_commitment("I promise to finish the design review")
        assert c is not None
        assert "finish" in c.text.lower() or "design" in c.text.lower()

    def test_no_commitment(self):
        c = _extract_commitment("The weather is nice today")
        assert c is None


# ═══════════════════════════════════════════════════════════════════════════
# PreferenceModel
# ═══════════════════════════════════════════════════════════════════════════


class TestPreferenceModel:
    def _make_model(self) -> PreferenceModel:
        db = MagicMock()
        db.get_preference.return_value = None
        db.set_preference = MagicMock()
        return PreferenceModel(db)

    def test_new_profile_created(self):
        model = self._make_model()
        assert model.profile.writing_formality == 0.5

    def test_load_existing_profile(self):
        db = MagicMock()
        db.get_preference.return_value = {
            "writing_formality": 0.8,
            "language_preference": "it",
        }
        model = PreferenceModel(db)
        assert model.profile.writing_formality == 0.8
        assert model.profile.language_preference == "it"

    def test_update_from_email_outgoing(self):
        model = self._make_model()
        model.update_from_email(
            sender="",
            body="Dear Mr. Smith, I appreciate your kind response. Sincerely, Francesco",
            is_outgoing=True,
        )
        # Formality should have moved toward formal
        assert model.profile.writing_formality > 0.5
        assert model.profile.total_emails_analyzed == 1

    def test_update_from_email_response_time(self):
        model = self._make_model()
        model.update_from_email(
            sender="marco@example.com",
            body="",
            reply_time_hours=1.5,
        )
        assert "marco@example.com" in model.profile.response_patterns
        assert model.profile.response_patterns["marco@example.com"] == 1.5

    def test_update_from_calendar(self):
        model = self._make_model()
        events = [
            {"start": "2026-03-01T09:00:00"},
            {"start": "2026-03-01T11:00:00"},
            {"start": "2026-03-01T14:00:00"},
        ]
        model.update_from_calendar(events)
        assert model.profile.avg_daily_meetings > 0

    def test_update_from_chat_commitment(self):
        model = self._make_model()
        model.update_from_chat("I'll send the pricing to Marco by Friday")
        assert len(model.profile.commitments) == 1

    def test_update_from_approval(self):
        model = self._make_model()
        model.update_from_approval("send_email", approved=True, context={"topic": "pricing"})
        assert "pricing" in model.profile.topic_importance
        assert model.profile.topic_importance["pricing"] > 0.5

    def test_update_from_approval_rejected(self):
        model = self._make_model()
        model.update_from_approval("send_email", approved=False, context={"topic": "newsletter"})
        assert "newsletter" in model.profile.topic_importance
        assert model.profile.topic_importance["newsletter"] < 0.5

    def test_track_and_check_commitments(self):
        model = self._make_model()
        model.track_commitment(
            "finish report",
            "Marco",
            deadline=datetime.now() - timedelta(hours=1),
        )
        overdue = model.check_commitments()
        assert len(overdue) == 1

    def test_fulfill_commitment(self):
        model = self._make_model()
        model.track_commitment("task", deadline=datetime.now() - timedelta(hours=1))
        assert model.fulfill_commitment(0) is True
        assert model.check_commitments() == []

    def test_get_upcoming_commitments(self):
        model = self._make_model()
        model.track_commitment(
            "task1",
            deadline=datetime.now() + timedelta(hours=2),
        )
        model.track_commitment(
            "task2",
            deadline=datetime.now() + timedelta(days=5),
        )
        upcoming = model.get_upcoming_commitments(hours=24)
        assert len(upcoming) == 1
        assert upcoming[0].text == "task1"

    def test_prune_old_commitments(self):
        model = self._make_model()
        old = Commitment(
            text="old task",
            detected_at=datetime.now() - timedelta(days=60),
            fulfilled=True,
            fulfilled_at=datetime.now() - timedelta(days=59),
        )
        model.profile.commitments.append(old)
        model.track_commitment("new task")
        removed = model.prune_old_commitments(days=30)
        assert removed == 1
        assert len(model.profile.commitments) == 1

    def test_rebuild_inner_circle(self):
        model = self._make_model()
        model.profile.response_patterns = {
            "marco": 1.0,
            "luca": 5.0,
            "sara": 2.0,
        }
        model.profile.response_urgency = {
            "marco": 0.9,
            "sara": 0.7,
            "luca": 0.3,
        }
        circle = model.rebuild_inner_circle(top_n=2)
        assert circle[0] == "marco"  # Fastest + most urgent
        assert len(circle) == 2


class TestSystemPrompt:
    def test_basic_prompt(self):
        model = TestPreferenceModel._make_model(None)
        model.profile.writing_formality = 0.8
        model.profile.language_preference = "it"
        model.profile.inner_circle = ["Marco", "Luca"]
        model.profile.active_hours = [(9, 12), (14, 18)]

        prompt = model.to_system_prompt()
        assert "formally" in prompt
        assert "it" in prompt
        assert "Marco" in prompt
        assert "9-12" in prompt

    def test_prompt_with_commitments(self):
        model = TestPreferenceModel._make_model(None)
        model.track_commitment(
            "send pricing",
            "Marco",
            deadline=datetime.now() - timedelta(hours=1),
        )

        prompt = model.to_system_prompt()
        assert "Commitments" in prompt
        assert "send pricing" in prompt
        assert "OVERDUE" in prompt

    def test_prompt_with_priorities(self):
        model = TestPreferenceModel._make_model(None)
        model.profile.topic_importance = {
            "pricing": 0.9,
            "meetings": 0.7,
            "newsletters": 0.3,
        }

        prompt = model.to_system_prompt()
        assert "pricing" in prompt
        assert "Priorities" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Temporal Pattern Detection (from patterns.py)
# ═══════════════════════════════════════════════════════════════════════════


class TestTemporalPatterns:
    def test_day_of_week_detection(self):
        from omnibrain.proactive.patterns import _detect_day_of_week_pattern

        # 5 Mondays at ~9:00
        base = datetime(2026, 2, 2, 9, 0)  # a Monday
        timestamps = [base + timedelta(weeks=i, minutes=j)
                      for i, j in enumerate([0, 10, -5, 15, 20])]
        result = _detect_day_of_week_pattern(timestamps)
        assert result is not None
        day_name, count, stddev = result
        assert day_name == "Monday"
        assert count == 5

    def test_no_day_pattern_when_scattered(self):
        from omnibrain.proactive.patterns import _detect_day_of_week_pattern

        # One observation per day of week — no pattern
        base = datetime(2026, 2, 2)
        timestamps = [base + timedelta(days=i) for i in range(7)]
        result = _detect_day_of_week_pattern(timestamps)
        assert result is None

    def test_time_of_day_detection(self):
        from omnibrain.proactive.patterns import _detect_time_of_day_pattern

        # 6 observations at ~9:00 on different days
        base = datetime(2026, 2, 1, 9, 0)
        timestamps = [base + timedelta(days=i, minutes=j)
                      for i, j in enumerate([0, 5, -3, 10, -8, 15])]
        result = _detect_time_of_day_pattern(timestamps)
        assert result is not None
        hour, count, stddev = result
        assert hour == 9
        assert count == 6
        assert stddev < 1.0

    def test_no_time_pattern_when_spread(self):
        from omnibrain.proactive.patterns import _detect_time_of_day_pattern

        # Observations spread across 12 hours
        timestamps = [
            datetime(2026, 2, i, h, 0)
            for i, h in zip(range(1, 7), [7, 9, 12, 15, 18, 21])
        ]
        result = _detect_time_of_day_pattern(timestamps)
        assert result is None

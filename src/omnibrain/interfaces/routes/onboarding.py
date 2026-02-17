"""Onboarding routes for OmniBrain API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Depends, HTTPException

from omnibrain.interfaces.api_models import (
    InsightCardResponse,
    OnboardingProfileRequest,
    OnboardingResultResponse,
)

logger = logging.getLogger("omnibrain.api")


def register_onboarding_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register onboarding routes."""

    @app.post("/api/v1/onboarding/analyze", response_model=OnboardingResultResponse)
    async def onboarding_analyze(
        token: str = Depends(verify_api_key),
    ) -> OnboardingResultResponse:
        """Run first-time analysis (Holy Shit moment).

        Fetches 7 days of emails + upcoming events, counts contacts,
        and generates insight cards. Runs in a thread pool to avoid
        blocking the event loop.
        """
        from omnibrain.auth.google_oauth import GoogleOAuthManager
        from omnibrain.auth.onboarding import OnboardingAnalyzer

        mgr = GoogleOAuthManager(server._data_dir)
        if not mgr.is_connected():
            raise HTTPException(
                status_code=400,
                detail="Google not connected — complete OAuth first",
            )

        analyzer = OnboardingAnalyzer(server._data_dir)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, analyzer.analyze)

        # Store onboarding completion in preferences
        try:
            server._db.set_preference("onboarding_complete", True, learned_from="onboarding")
            if result.user_name:
                server._db.set_preference("user_name", result.user_name, learned_from="onboarding")
            if result.user_email:
                server._db.set_preference("user_email", result.user_email, learned_from="onboarding")
        except Exception as e:
            logger.warning("Failed to store onboarding prefs: %s", e)

        # ── Persist raw Google data that was previously discarded ──
        try:
            import json as _json
            # Persist emails as events
            for em in result.raw_emails:
                subject = getattr(em, "subject", "") or ""
                snippet = getattr(em, "snippet", "") or getattr(em, "body", "")[:500] if hasattr(em, "body") else ""
                sender = getattr(em, "sender", "")
                ts = getattr(em, "date", None) or getattr(em, "timestamp", None)
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else None
                server._db.insert_event(
                    source="gmail",
                    event_type="email",
                    title=subject or "(no subject)",
                    content=snippet,
                    metadata=_json.dumps({"sender": sender, "from_onboarding": True}),
                    timestamp=ts_str,
                )
            # Persist calendar events
            for ev in result.raw_events:
                title = getattr(ev, "title", "") or getattr(ev, "summary", "") or ""
                start = getattr(ev, "start_time", None) or getattr(ev, "start", None)
                end = getattr(ev, "end_time", None) or getattr(ev, "end", None)
                attendees = getattr(ev, "attendees", [])
                ts_str = start.isoformat() if hasattr(start, "isoformat") else str(start) if start else None
                server._db.insert_event(
                    source="calendar",
                    event_type="meeting",
                    title=title or "(untitled event)",
                    metadata=_json.dumps({
                        "start_time": start.isoformat() if hasattr(start, "isoformat") else str(start or ""),
                        "end_time": end.isoformat() if hasattr(end, "isoformat") else str(end or ""),
                        "attendees": _json.dumps(list(attendees) if attendees else []),
                        "from_onboarding": True,
                    }),
                    timestamp=ts_str,
                )
            # Persist contacts
            for contact_email in result.raw_contacts:
                if contact_email and "@" in contact_email:
                    from omnibrain.models import ContactInfo
                    server._db.upsert_contact(ContactInfo(
                        email=contact_email,
                        name=contact_email.split("@")[0].replace(".", " ").title(),
                        source="gmail",
                    ))
            if result.raw_emails or result.raw_events:
                logger.info(
                    "Onboarding: persisted %d emails, %d events, %d contacts",
                    len(result.raw_emails), len(result.raw_events), len(result.raw_contacts),
                )
        except Exception as e:
            logger.warning("Failed to persist onboarding raw data: %s", e)

        return OnboardingResultResponse(
            greeting=result.greeting,
            stats=result.stats,
            insights=[
                InsightCardResponse(
                    icon=c.icon,
                    title=c.title,
                    body=c.body,
                    action=c.action,
                    action_type=c.action_type,
                    priority=c.priority,
                )
                for c in result.insights
            ],
            user_email=result.user_email,
            user_name=result.user_name,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
        )

    # ══════════════════════════════════════════════════════════════════
    # Onboarding — conversational profile save
    # ══════════════════════════════════════════════════════════════════

    @app.post("/api/v1/onboarding/profile")
    async def onboarding_save_profile(
        body: OnboardingProfileRequest,
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Save profile info from conversational onboarding (no Google needed)."""
        saved: dict[str, str] = {}

        if body.name:
            server._db.set_preference("user_name", body.name, learned_from="onboarding_chat")
            saved["name"] = body.name
        if body.work:
            server._db.set_preference("user_work", body.work, learned_from="onboarding_chat")
            saved["work"] = body.work
        if body.goals:
            server._db.set_preference("user_goals", body.goals, learned_from="onboarding_chat")
            saved["goals"] = body.goals
        if body.timezone:
            server._db.set_preference("timezone", body.timezone, learned_from="onboarding_chat")
            saved["timezone"] = body.timezone

        # Also store in memory for the LLM to reference
        if server._memory:
            profile_parts = []
            if body.name:
                profile_parts.append(f"The user's name is {body.name}.")
            if body.work:
                profile_parts.append(f"They work on: {body.work}.")
            if body.goals:
                profile_parts.append(f"Their goals: {body.goals}.")
            if profile_parts:
                server._memory.store(
                    text=" ".join(profile_parts),
                    source="onboarding",
                    source_type="profile",
                )

        server._db.set_preference("onboarding_complete", True, learned_from="onboarding_chat")

        # ── Extract structured data from interview answers ──
        # Run LLM extraction on the profile to populate events table
        # so the briefing has data from day zero.
        if server._router and (body.work or body.goals):
            try:
                from omnibrain.conversation_extractor import extract_and_persist

                profile_text = []
                if body.name:
                    profile_text.append(f"My name is {body.name}.")
                if body.work:
                    profile_text.append(f"I work on: {body.work}.")
                if body.goals:
                    profile_text.append(f"What I wish I had more time for: {body.goals}.")

                user_msg = " ".join(profile_text)
                assistant_msg = f"Welcome {body.name or 'there'}! I've saved your profile."

                asyncio.create_task(
                    extract_and_persist(
                        user_message=user_msg,
                        assistant_response=assistant_msg,
                        router=server._router,
                        db=server._db,
                        memory=server._memory,
                        session_id="onboarding",
                    )
                )
            except Exception as e:
                logger.debug("Onboarding extraction failed: %s", e)

        return {"ok": True, "saved": saved}

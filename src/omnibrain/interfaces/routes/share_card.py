"""Share Card route for OmniBrain API."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response

logger = logging.getLogger("omnibrain.api")


def register_share_card_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register share card routes."""

    @app.get("/api/v1/share-card")
    async def get_share_card(
        token: str = Depends(verify_api_key),
        user_name: str = Query("", description="User display name"),
    ) -> Response:
        """Generate a 1200×630 PNG share card with onboarding stats.

        Reads the most recent onboarding result from preferences.
        Returns a PNG image suitable for Open Graph / social sharing.
        """
        from omnibrain.share_card import generate_share_card

        # Pull stats from stored preferences
        stats: dict[str, int] = {}
        name = user_name
        duration_ms = 0

        try:
            # Try to get stored onboarding stats
            pref_name = server._db.get_preference("user_name")
            if pref_name and not name:
                name = str(pref_name)

            # Count actual data as a fallback / enrichment
            try:
                email_count = server._db.count_events(source="gmail")
                stats["emails"] = email_count
            except Exception:
                stats["emails"] = 0

            try:
                event_count = server._db.count_events(source="calendar")
                stats["events"] = event_count
            except Exception:
                stats["events"] = 0

            try:
                contact_count = server._db.count_contacts()
                stats["contacts"] = contact_count
            except Exception:
                stats["contacts"] = 0

        except Exception as e:
            logger.warning("Failed to load share card data: %s", e)
            stats = {"emails": 0, "contacts": 0, "events": 0}

        png_bytes = generate_share_card(
            stats=stats,
            insights_count=0,
            user_name=name,
            duration_ms=duration_ms,
        )

        if png_bytes is None:
            raise HTTPException(
                status_code=501,
                detail="Pillow is not installed — run `pip install Pillow` to enable share card generation",
            )

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache",
                "Content-Disposition": 'inline; filename="omnibrain-share.png"',
            },
        )

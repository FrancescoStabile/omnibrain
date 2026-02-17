"""Pattern detection routes for OmniBrain API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends

logger = logging.getLogger("omnibrain.api")


def register_patterns_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register pattern detection routes."""

    @app.get("/api/v1/patterns")
    async def get_patterns(
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get detected patterns and automation proposals."""
        pd = getattr(server, "_pattern_detector", None)
        if not pd:
            return {"patterns": [], "automations": [], "summary": {}}
        try:
            patterns = pd.get_patterns()
            strong = pd.get_strong_patterns()
            automations = pd.propose_automations()
            summary = pd.summary()
            return {
                "patterns": [
                    {
                        "type": p.pattern_type,
                        "description": p.description,
                        "occurrences": p.occurrences,
                        "confidence": round(p.avg_confidence, 2),
                        "strength": p.strength,
                        "first_seen": p.first_seen,
                        "last_seen": p.last_seen,
                    }
                    for p in patterns
                ],
                "strong_patterns": [
                    {"type": p.pattern_type, "description": p.description, "strength": p.strength}
                    for p in strong
                ],
                "automations": [
                    {
                        "title": a.title,
                        "description": a.description,
                        "pattern_type": a.pattern_type,
                        "confidence": round(a.confidence, 2),
                    }
                    for a in automations
                ],
                "summary": summary,
            }
        except Exception as e:
            logger.warning("Patterns fetch failed: %s", e)
            return {"patterns": [], "automations": [], "summary": {}, "error": str(e)}

    @app.get("/api/v1/patterns/weekly")
    async def get_patterns_weekly(
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get weekly pattern analysis."""
        pd = getattr(server, "_pattern_detector", None)
        if not pd:
            return {"analysis": {}}
        try:
            return {"analysis": pd.weekly_analysis()}
        except Exception as e:
            logger.warning("Weekly patterns failed: %s", e)
            return {"analysis": {}, "error": str(e)}

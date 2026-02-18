"""
OmniBrain — Transparency API Routes

Endpoints:
    GET /api/v1/transparency/calls  — Paginated LLM call history
    GET /api/v1/transparency/stats  — Aggregated cost/usage statistics
    GET /api/v1/transparency/daily  — Daily cost breakdown (for charts)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

logger = logging.getLogger("omnibrain.api.transparency")


def register_transparency_routes(app: Any, server: Any, verify_api_key: Any) -> None:
    """Register transparency audit routes."""

    router = APIRouter(prefix="/api/v1/transparency", tags=["transparency"])

    def _get_logger():
        """Lazy-get TransparencyLogger from server."""
        tlog = getattr(server, "_transparency_logger", None)
        if tlog is None:
            # Create on demand if not wired yet
            from omnibrain.transparency import TransparencyLogger
            tlog = TransparencyLogger(server._data_dir)
            server._transparency_logger = tlog
        return tlog

    @router.get("/calls")
    async def get_calls(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        provider: str = Query("", description="Filter by provider"),
        source: str = Query("", description="Filter by source (chat, briefing, etc.)"),
        since: str = Query("", description="ISO date filter (>=)"),
        until: str = Query("", description="ISO date filter (<=)"),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get paginated LLM call history."""
        tlog = _get_logger()
        calls = tlog.get_calls(
            limit=limit,
            offset=offset,
            provider=provider,
            source=source,
            since=since,
            until=until,
        )
        return {
            "calls": [c.to_dict() for c in calls],
            "limit": limit,
            "offset": offset,
        }

    @router.get("/stats")
    async def get_stats(
        days: int = Query(0, ge=0, description="0 = all time, N = last N days"),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get aggregated transparency statistics."""
        tlog = _get_logger()
        stats = tlog.get_stats(days=days)
        return stats.to_dict()

    @router.get("/daily")
    async def get_daily_costs(
        days: int = Query(30, ge=1, le=365),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get daily cost breakdown for charting."""
        tlog = _get_logger()
        return {
            "days": days,
            "data": tlog.get_daily_costs(days=days),
        }

    app.include_router(router)

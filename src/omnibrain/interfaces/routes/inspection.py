"""
OmniBrain — Agent Inspection Routes

Transparency endpoint that exposes the agent's internal state
(system prompt, tools, plan, findings) for debugging and frontend display.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Query

logger = logging.getLogger("omnibrain.api")


def register_inspection_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register agent inspection/transparency routes."""

    @app.get("/api/v1/chat/inspect")
    async def inspect_agent(
        session_id: str = Query("default"),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Inspect the agent's internal state for a given session.

        Returns the system prompt preview, registered tools, current plan,
        findings, message count, and running status. Useful for debugging
        and building transparency UIs.
        """
        bridge = getattr(server, "_agent_bridge", None)
        if not bridge:
            return {
                "error": "Agent bridge not initialized",
                "hint": "The agent bridge is only available when an LLM router is configured.",
            }

        return bridge.inspect(session_id)

    @app.get("/api/v1/chat/agents")
    async def list_active_agents(
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List all active agent sessions."""
        bridge = getattr(server, "_agent_bridge", None)
        if not bridge:
            return {"sessions": [], "count": 0}

        sessions = list(bridge._agents.keys())
        return {
            "sessions": sessions,
            "count": len(sessions),
            "max_cached": bridge.MAX_CACHED_AGENTS,
        }

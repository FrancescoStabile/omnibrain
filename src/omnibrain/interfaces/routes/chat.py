"""Chat streaming routes for OmniBrain API.

Phase 2: Routes through OmniBrainAgent's ReAct loop via AgentChatBridge.
Falls back to direct LLM streaming if the agent bridge is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import Depends, Query
from fastapi.responses import StreamingResponse

from omnibrain.interfaces.api_models import ChatRequest

logger = logging.getLogger("omnibrain.api")


def register_chat_routes(app, server, verify_api_key) -> None:  # noqa: ANN001
    """Register chat streaming and session management routes."""

    @app.post("/api/v1/chat")
    async def chat_stream(
        body: ChatRequest, token: str = Depends(verify_api_key),
    ) -> StreamingResponse:
        """Streaming chat via Server-Sent Events.

        Uses OmniBrainAgent's ReAct loop (via AgentChatBridge) for
        intelligent multi-step reasoning with tool use. Falls back
        to direct LLM streaming if the agent bridge is unavailable.
        """
        session_id = body.session_id or "default"

        async def event_generator() -> Any:
            # ── Try Agent bridge (Phase 2) ──
            bridge = getattr(server, "_agent_bridge", None)
            if bridge and server._router:
                try:
                    async for frame in bridge.stream(
                        message=body.message,
                        session_id=session_id,
                    ):
                        yield frame
                    return
                except Exception as e:
                    logger.error(f"Agent bridge failed, falling back to direct LLM: {e}", exc_info=True)
                    # Fall through to legacy path below

            # ── Legacy fallback: direct LLM streaming (no agent) ──
            # Persist user message
            try:
                server._db.save_chat_message(session_id, "user", body.message)
            except Exception as e:
                logger.warning(f"Failed to save user message: {e}")

            full_response = ""
            if server._router:
                try:
                    from omnibrain.chat_tools import CHAT_TOOLS

                    system = server._system_prompt
                    from datetime import datetime
                    now = datetime.now()
                    system += (
                        f"\n\n## Current Date & Time\n"
                        f"Today is {now.strftime('%A, %B %d, %Y')}. "
                        f"Current time: {now.strftime('%H:%M')} (local)."
                    )

                    messages: list[dict[str, str]] = []
                    try:
                        history = server._db.get_chat_messages(session_id, limit=20)
                        for msg in history[:-1]:
                            messages.append({"role": msg["role"], "content": msg["content"]})
                    except Exception:
                        pass
                    messages.append({"role": "user", "content": body.message})

                    async for chunk in server._router.stream(
                        messages=messages, tools=CHAT_TOOLS, system=system,
                    ):
                        if chunk.content:
                            full_response += chunk.content
                            data = json.dumps({"type": "token", "content": chunk.content})
                            yield f"data: {data}\n\n"
                        if chunk.done:
                            break
                except Exception as e:
                    logger.error(f"Legacy LLM streaming failed: {e}")
                    fallback = "I'm having trouble connecting right now. Please try again."
                    yield f"data: {json.dumps({'type': 'token', 'content': fallback})}\n\n"
                    full_response = fallback
            else:
                fallback = "Ciao! I'm OmniBrain. The LLM router isn't configured yet. Check your API keys in .env."
                words = fallback.split()
                for i, word in enumerate(words):
                    tok = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'type': 'token', 'content': tok})}\n\n"
                    await asyncio.sleep(0.02)
                full_response = fallback

            # Persist response
            if full_response.strip():
                try:
                    server._db.save_chat_message(session_id, "assistant", full_response)
                except Exception:
                    pass

            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ══════════════════════════════════════════════════════════════════
    # Chat history & session management
    # ══════════════════════════════════════════════════════════════════

    @app.get("/api/v1/chat/sessions")
    async def get_chat_sessions(
        limit: int = Query(20, ge=1, le=100),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """List recent chat sessions."""
        sessions = server._db.get_chat_sessions(limit)
        return {"sessions": sessions}

    @app.get("/api/v1/chat/history")
    async def get_chat_history(
        session_id: str = Query("default"),
        limit: int = Query(100, ge=1, le=500),
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Get chat messages for a session."""
        messages = server._db.get_chat_messages(session_id, limit)
        return {"session_id": session_id, "messages": messages}

    @app.delete("/api/v1/chat/sessions/{session_id}")
    async def delete_chat_session(
        session_id: str,
        token: str = Depends(verify_api_key),
    ) -> dict[str, Any]:
        """Delete a chat session."""
        deleted = server._db.delete_chat_session(session_id)
        return {"ok": True, "deleted": deleted}

"""
OmniBrain — Data Export / Wipe Routes (GDPR Compliance)

Endpoints:
    POST /api/v1/data/export  — Download full JSON archive of all user data
    POST /api/v1/data/wipe    — Request data wipe (double-delete pattern)
    DELETE /api/v1/data/wipe  — Confirm data wipe with token

Design:
    - Export streams JSON incrementally to handle large datasets
    - Wipe uses double-delete pattern: first call returns a confirmation token
      (valid 60s), second call with token performs the actual wipe
    - All tables are cleared but schema is preserved (clean reset)
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("omnibrain.api.data")

# Pending wipe confirmations: {token: expiry_timestamp}
_pending_wipes: dict[str, float] = {}
WIPE_TOKEN_TTL = 60  # seconds


class WipeRequest(BaseModel):
    """Request body for confirming a data wipe."""
    confirmation_token: str | None = None


class WipeResponse(BaseModel):
    """Response from wipe initiation or execution."""
    status: str
    confirmation_token: str | None = None
    message: str
    expires_in: int | None = None


def register_data_routes(app: Any, server: Any, verify_api_key: Any) -> None:
    """Register GDPR data export/wipe routes."""

    router = APIRouter(prefix="/api/v1/data", tags=["data"])

    @router.post("/export")
    async def export_data(token: str = Depends(verify_api_key)) -> StreamingResponse:
        """Export all user data as a JSON archive.

        Returns a streaming JSON response containing all user data:
        events, contacts, proposals, observations, chat sessions,
        briefings, preferences, memory documents, and knowledge graph data.
        """
        db = server._db

        async def generate_export() -> Any:
            yield '{\n'

            # ── Events ──
            try:
                events = db.get_events(limit=10000)
                yield f'"events": {json.dumps(events, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: events failed: {e}")
                yield '"events": [],\n'

            # ── Contacts ──
            try:
                contacts = db.get_contacts(limit=10000)
                contact_dicts = []
                for c in contacts:
                    if hasattr(c, '__dict__'):
                        contact_dicts.append({k: v for k, v in c.__dict__.items() if not k.startswith('_')})
                    elif isinstance(c, dict):
                        contact_dicts.append(c)
                yield f'"contacts": {json.dumps(contact_dicts, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: contacts failed: {e}")
                yield '"contacts": [],\n'

            # ── Proposals ──
            try:
                proposals = db.get_proposals(limit=10000)
                yield f'"proposals": {json.dumps(proposals, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: proposals failed: {e}")
                yield '"proposals": [],\n'

            # ── Observations ──
            try:
                observations = db.get_observations(days=36500)  # ~100 years
                yield f'"observations": {json.dumps(observations, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: observations failed: {e}")
                yield '"observations": [],\n'

            # ── Chat Sessions ──
            try:
                sessions = db.get_chat_sessions(limit=10000)
                chat_data = []
                for s in sessions:
                    sid = s.get("id") or s.get("session_id", "")
                    messages = db.get_chat_messages(sid) if sid else []
                    chat_data.append({"session": s, "messages": messages})
                yield f'"chat_sessions": {json.dumps(chat_data, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: chat sessions failed: {e}")
                yield '"chat_sessions": [],\n'

            # ── Briefings ──
            try:
                briefings = db.get_briefings(limit=10000)
                yield f'"briefings": {json.dumps(briefings, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: briefings failed: {e}")
                yield '"briefings": [],\n'

            # ── Preferences ──
            try:
                prefs = db.get_all_preferences()
                yield f'"preferences": {json.dumps(prefs, default=str)},\n'
            except Exception as e:
                logger.warning(f"Export: preferences failed: {e}")
                yield '"preferences": [],\n'

            # ── Memory Documents ──
            try:
                memory = getattr(server, "_memory", None)
                if memory and hasattr(memory, "search"):
                    # Search with empty query returns recent entries
                    docs = memory.search("", max_results=50000)
                    doc_dicts = []
                    for d in docs:
                        entry = {
                            "text": getattr(d, "text", str(d)),
                            "source": getattr(d, "source", ""),
                            "source_type": getattr(d, "source_type", ""),
                            "timestamp": getattr(d, "timestamp", ""),
                        }
                        doc_dicts.append(entry)
                    yield f'"memory_documents": {json.dumps(doc_dicts, default=str)},\n'
                else:
                    yield '"memory_documents": [],\n'
            except Exception as e:
                logger.warning(f"Export: memory documents failed: {e}")
                yield '"memory_documents": [],\n'

            # ── Knowledge Graph ──
            try:
                kg = getattr(server, "_knowledge_graph", None)
                if kg and hasattr(kg, "get_all_nodes"):
                    nodes = kg.get_all_nodes()
                    edges = kg.get_all_edges() if hasattr(kg, "get_all_edges") else []
                    yield f'"knowledge_graph": {{"nodes": {json.dumps(nodes, default=str)}, "edges": {json.dumps(edges, default=str)}}},\n'
                else:
                    yield '"knowledge_graph": {"nodes": [], "edges": []},\n'
            except Exception as e:
                logger.warning(f"Export: knowledge graph failed: {e}")
                yield '"knowledge_graph": {"nodes": [], "edges": []},\n'

            # ── Export metadata ──
            metadata = {
                "exported_at": datetime.now().isoformat(),
                "version": getattr(server, "_version", "unknown"),
                "format_version": "1.0",
            }
            yield f'"_metadata": {json.dumps(metadata)}\n'
            yield '}\n'

        filename = f"omnibrain-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        return StreamingResponse(
            generate_export(),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @router.post("/wipe")
    async def request_wipe(token: str = Depends(verify_api_key)) -> WipeResponse:
        """Request data wipe — returns a confirmation token.

        This is the first step of the double-delete pattern.
        The returned token must be sent back via DELETE /api/v1/data/wipe
        within 60 seconds to confirm the wipe.
        """
        # Clean expired tokens
        now = time.time()
        expired = [t for t, exp in _pending_wipes.items() if exp < now]
        for t in expired:
            del _pending_wipes[t]

        confirmation_token = secrets.token_urlsafe(32)
        _pending_wipes[confirmation_token] = now + WIPE_TOKEN_TTL

        logger.warning("Data wipe requested — confirmation token issued")

        return WipeResponse(
            status="pending_confirmation",
            confirmation_token=confirmation_token,
            message=(
                "⚠️ DATA WIPE REQUESTED. This will permanently delete ALL your data. "
                "Send a DELETE request to /api/v1/data/wipe with this confirmation_token "
                f"within {WIPE_TOKEN_TTL} seconds to confirm."
            ),
            expires_in=WIPE_TOKEN_TTL,
        )

    @router.delete("/wipe")
    async def confirm_wipe(
        body: WipeRequest, token: str = Depends(verify_api_key),
    ) -> WipeResponse:
        """Confirm and execute data wipe.

        Requires a valid confirmation token from POST /api/v1/data/wipe.
        Permanently deletes all user data. Schema is preserved.
        """
        if not body.confirmation_token:
            raise HTTPException(status_code=400, detail="confirmation_token is required")

        now = time.time()
        expiry = _pending_wipes.get(body.confirmation_token)

        if expiry is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired confirmation token. Request a new one via POST.",
            )

        if now > expiry:
            del _pending_wipes[body.confirmation_token]
            raise HTTPException(
                status_code=400,
                detail="Confirmation token has expired. Request a new one via POST.",
            )

        # Token is valid — execute the wipe
        del _pending_wipes[body.confirmation_token]

        db = server._db
        tables_wiped = []

        try:
            # Wipe all data tables via the DB's own connection context manager
            wipe_tables = [
                "events", "contacts", "proposals", "observations",
                "chat_messages", "chat_sessions", "briefings", "preferences",
                "installed_skills", "skill_data",
            ]
            import sqlite3 as _sqlite3
            with _sqlite3.connect(str(db.db_path)) as _conn:
                for table in wipe_tables:
                    try:
                        _conn.execute(f"DELETE FROM {table}")  # noqa: S608
                        tables_wiped.append(table)
                    except Exception as e:
                        logger.warning(f"Wipe table '{table}' failed: {e}")
                _conn.commit()

            # Clear memory store if available
            memory = getattr(server, "_memory", None)
            if memory and hasattr(memory, "clear"):
                try:
                    memory.clear()
                    tables_wiped.append("memory_store")
                except Exception as e:
                    logger.warning(f"Memory clear failed: {e}")

            # Clear knowledge graph if available
            kg = getattr(server, "_knowledge_graph", None)
            if kg and hasattr(kg, "clear"):
                try:
                    kg.clear()
                    tables_wiped.append("knowledge_graph")
                except Exception as e:
                    logger.warning(f"Knowledge graph clear failed: {e}")

            logger.warning(f"DATA WIPE EXECUTED — cleared: {', '.join(tables_wiped)}")

            return WipeResponse(
                status="wiped",
                message=f"All data has been permanently deleted. Tables cleared: {', '.join(tables_wiped)}",
            )

        except Exception as e:
            logger.error(f"Data wipe failed: {e}")
            raise HTTPException(status_code=500, detail=f"Wipe failed: {e}") from e

    # ── Demo Mode routes ──

    @router.get("/demo/status")
    async def demo_status(token: str = Depends(verify_api_key)) -> dict[str, Any]:
        """Return current demo mode status."""
        try:
            from omnibrain.demo_data import DemoDataManager
            mgr = DemoDataManager(db=server._db, memory=getattr(server, "_memory", None))
            return mgr.get_status()
        except Exception as e:
            return {"active": False, "error": str(e)}

    @router.post("/demo/activate")
    async def demo_activate(token: str = Depends(verify_api_key)) -> dict[str, Any]:
        """Activate demo mode with sample data."""
        try:
            from omnibrain.demo_data import DemoDataManager
            mgr = DemoDataManager(db=server._db, memory=getattr(server, "_memory", None))
            count = mgr.activate()
            return {"activated": True, "records_inserted": count}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/demo/deactivate")
    async def demo_deactivate(token: str = Depends(verify_api_key)) -> dict[str, Any]:
        """Deactivate demo mode and remove sample data."""
        try:
            from omnibrain.demo_data import DemoDataManager
            mgr = DemoDataManager(db=server._db, memory=getattr(server, "_memory", None))
            count = mgr.deactivate()
            return {"deactivated": True, "records_removed": count}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    app.include_router(router)

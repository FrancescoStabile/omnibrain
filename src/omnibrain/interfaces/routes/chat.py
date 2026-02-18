"""Chat streaming routes for OmniBrain API."""

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

        Sends the user message to the LLM router with memory context,
        conversation history, and streams the response token by token.
        Persists all messages to DB for session continuity.
        """
        session_id = body.session_id or "default"

        async def event_generator() -> Any:
            # ── 1. Persist user message ──
            try:
                server._db.save_chat_message(session_id, "user", body.message)
            except Exception as e:
                logger.warning(f"Failed to save user message: {e}")

            # ── 1b. Prompt injection defense ──
            sanitizer = getattr(server, "_sanitizer", None)
            sanitized_message = body.message
            if sanitizer and body.message.strip():
                try:
                    result = sanitizer.sanitize_message(body.message)
                    if result.is_blocked:
                        logger.warning(
                            f"Prompt injection BLOCKED (score={result.threat_score:.2f}): "
                            f"{result.reason}"
                        )
                        error_data = json.dumps({
                            "type": "error",
                            "content": (
                                "⚠️ Your message was flagged as potentially unsafe and has been blocked. "
                                "This is a security measure to protect your AI. "
                                "Please rephrase your request."
                            ),
                            "threat_score": result.threat_score,
                        })
                        yield f"data: {error_data}\n\n"
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
                        return
                    if result.is_warned:
                        logger.warning(
                            f"Prompt injection WARNING (score={result.threat_score:.2f}): "
                            f"{result.reason}"
                        )
                        sanitized_message = result.safe_text
                except Exception as e:
                    logger.debug(f"Sanitizer check failed (non-blocking): {e}")

            # ── 2. Gather memory context ──
            memory_context = ""
            if server._memory and sanitized_message.strip():
                results = server._memory.search(sanitized_message, max_results=5)
                if results:
                    snippets = []
                    for doc in results:
                        snippet = doc.text[:300].strip()
                        # Sanitize memory snippets — emails are an external attack vector
                        if sanitizer:
                            try:
                                san_result = sanitizer.sanitize(snippet, source=doc.source_type or "memory")
                                snippet = san_result.safe_text
                            except Exception:
                                pass
                        if doc.source:
                            snippet = f"[{doc.source_type or 'memory'}] {snippet}"
                        snippets.append(snippet)
                    memory_context = (
                        "\n\n---\n**Your memories relevant to this question:**\n"
                        + "\n".join(f"- {s}" for s in snippets)
                    )

            # ── 3. Build system prompt ──
            system = server._system_prompt

            # Inject current date/time so the LLM never hallucinates it
            from datetime import datetime
            now = datetime.now()
            system += (
                f"\n\n## Current Date & Time\n"
                f"Today is {now.strftime('%A, %B %d, %Y')}. "
                f"Current time: {now.strftime('%H:%M')} (local)."
            )

            user_name = server._db.get_preference("user_name", "")
            if user_name:
                system += f"\n\nThe user's name is {user_name}."

            # ── 3-tools. Instruct the LLM about its action capabilities ──
            system += (
                "\n\n## Your Action Capabilities\n"
                "You have tools to ACTUALLY manage the user's data — don't just say you did something, "
                "USE the tools to really do it. Available actions:\n"
                "- **search_events / list_events**: Look up events/appointments before modifying them\n"
                "- **delete_event**: Remove an event (search first to find the correct ID!)\n"
                "- **create_event**: Add a new event/appointment\n"
                "- **update_event**: Modify an existing event (search first to find the ID)\n"
                "- **list_contacts**: See the user's contacts\n"
                "- **list_proposals / approve_proposal / reject_proposal**: Manage pending proposals\n"
                "- **set_preference**: Remember a user preference\n\n"
                "IMPORTANT: When the user asks you to create, delete, or modify an event, "
                "you MUST call the appropriate tool. NEVER just say you did it without actually calling the tool. "
                "When deleting or updating, ALWAYS search first to find the right event ID.\n"
                "Event IDs are listed in the schedule data below — use them directly when the user "
                "refers to a specific event."
            )

            # ── 3a. Inject LIVE structured data from the database ──
            # This is the critical bridge: the LLM sees the same data
            # that the frontend (homepage, timeline, briefing) displays.
            try:
                from datetime import timedelta

                # Today's events (calendar + extracted)
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + timedelta(days=1)
                week_end = today_start + timedelta(days=7)

                today_events = server._db.get_events(
                    since=today_start, until=today_end, limit=30,
                )
                week_events = server._db.get_events(
                    since=today_start, until=week_end, limit=50,
                )

                if today_events:
                    events_text = "\n\n## Today's Schedule\n"
                    for ev in today_events:
                        ts = ev.get("timestamp", "")
                        title = ev.get("title", "Untitled")
                        src = ev.get("source", "")
                        meta = ev.get("metadata", "")
                        eid = ev.get("id", "")
                        time_str = ts[11:16] if len(ts) > 11 and ts[11:16] != "00:00" else "All day"
                        events_text += f"- [id={eid}] {time_str}: {title}"
                        if src:
                            events_text += f" ({src})"
                        if meta and isinstance(meta, str) and len(meta) < 200:
                            try:
                                import json as _json
                                meta_d = _json.loads(meta)
                                if meta_d.get("location"):
                                    events_text += f" @ {meta_d['location']}"
                                if meta_d.get("description"):
                                    events_text += f" — {meta_d['description'][:100]}"
                            except (ValueError, TypeError):
                                pass
                        events_text += "\n"
                    system += events_text

                # This week's events (excluding today, already shown)
                future_events = [
                    ev for ev in week_events
                    if ev.get("timestamp", "")[:10] != now.strftime("%Y-%m-%d")
                ]
                if future_events:
                    system += "\n## This Week (upcoming)\n"
                    for ev in future_events[:20]:
                        ts = ev.get("timestamp", "")
                        title = ev.get("title", "Untitled")
                        eid = ev.get("id", "")
                        date_str = ts[:10] if len(ts) >= 10 else "TBD"
                        time_str = ts[11:16] if len(ts) > 11 and ts[11:16] != "00:00" else "All day"
                        system += f"- [id={eid}] {date_str} {time_str}: {title}\n"

                # Pending proposals
                proposals = server._db.get_pending_proposals()
                if proposals:
                    system += "\n## Pending Proposals (awaiting user decision)\n"
                    for prop in proposals[:10]:
                        system += (
                            f"- [{prop.get('type', 'action')}] {prop.get('title', 'Untitled')}: "
                            f"{prop.get('description', '')[:150]}\n"
                        )

                # Key contacts (top 10 by interaction count)
                contacts = server._db.get_contacts(limit=10)
                if contacts:
                    system += "\n## Key Contacts\n"
                    for c in contacts:
                        name = c.name or c.email
                        system += f"- {name}"
                        if c.organization:
                            system += f" ({c.organization})"
                        if c.relationship:
                            system += f" — {c.relationship}"
                        system += "\n"

                # Recent observations / patterns
                observations = server._db.get_observations(days=30)
                if observations:
                    system += "\n## Behavioral Patterns Observed\n"
                    for obs in observations[:5]:
                        if isinstance(obs, dict):
                            system += f"- {obs.get('description', '')[:150]}\n"
                        else:
                            system += f"- {obs.description[:150]}\n"

            except Exception as e:
                logger.warning(f"Failed to inject live data context: {e}")

            if memory_context:
                system += memory_context

            # ── 3b. Query Skills via match_ask ──
            skill_context = ""
            runtime = getattr(server, "_skill_runtime", None)
            if runtime and body.message.strip():
                try:
                    skill_results = await runtime.match_ask(body.message)
                    if skill_results:
                        parts = []
                        for sr in skill_results:
                            skill_name = sr.get("skill", "unknown")
                            result = sr.get("result")
                            if result:
                                parts.append(f"[Skill: {skill_name}]\n{result}")
                        if parts:
                            skill_context = (
                                "\n\n---\n**Active Skills provided this information:**\n"
                                + "\n\n".join(parts)
                            )
                except Exception as e:
                    logger.warning(f"Skill match_ask failed: {e}")

            if skill_context:
                system += skill_context

            # ── 3c. Inject context resurrection if user mentions a project ──
            tracker = getattr(server, "_context_tracker", None)
            if tracker and body.message.strip():
                try:
                    all_projects = tracker.get_all_projects()
                    msg_lower = body.message.lower()
                    for proj in all_projects:
                        if proj.lower() in msg_lower:
                            summary = tracker.detect_return(proj)
                            if summary:
                                system += (
                                    f"\n\n---\n**Project context for '{proj}'** "
                                    f"(inactive {summary.days_since_last} days):\n"
                                    f"{summary.format_text()}"
                                )
                                break  # Only inject one project
                except Exception as e:
                    logger.warning(f"Context resurrection injection failed: {e}")

            # ── 4. Build messages with conversation history ──
            messages: list[dict[str, str]] = []
            try:
                history = server._db.get_chat_messages(session_id, limit=20)
                # Exclude the message we just saved (last user msg)
                for msg in history[:-1]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            except Exception:
                pass
            # Always append current user message as the last one
            messages.append({"role": "user", "content": body.message})

            # ── 5. Stream from LLM with tool-calling loop ──
            full_response = ""
            total_input_tokens = 0
            total_output_tokens = 0
            tools_were_used = False
            MAX_TOOL_ROUNDS = 5  # Safety limit to prevent infinite loops

            if server._router:
                try:
                    from omnibrain.chat_tools import CHAT_TOOLS, execute_tool

                    tool_round = 0
                    while tool_round <= MAX_TOOL_ROUNDS:
                        pending_tool_calls: list[dict] = []
                        round_content = ""

                        async for chunk in server._router.stream(
                            messages=messages,
                            tools=CHAT_TOOLS,
                            system=system,
                        ):
                            if chunk.content:
                                round_content += chunk.content
                                data = json.dumps({"type": "token", "content": chunk.content})
                                yield f"data: {data}\n\n"
                            if chunk.tool_call:
                                pending_tool_calls.append(chunk.tool_call)
                            if chunk.input_tokens:
                                total_input_tokens += chunk.input_tokens
                            if chunk.output_tokens:
                                total_output_tokens += chunk.output_tokens
                            if chunk.done:
                                break

                        full_response += round_content

                        # If no tool calls, we're done — LLM gave a text response
                        if not pending_tool_calls:
                            break

                        # ── Execute tool calls and feed results back ──
                        tool_round += 1
                        tools_were_used = True
                        logger.info(
                            f"Chat tool round {tool_round}: executing {len(pending_tool_calls)} tool(s): "
                            f"{[tc['name'] for tc in pending_tool_calls]}"
                        )

                        # Notify the user that we're working on it (streamed but NOT persisted)
                        for tc in pending_tool_calls:
                            tool_label = tc["name"].replace("_", " ")
                            status_msg = f"_[Executing: {tool_label}...]_\n\n"
                            data = json.dumps({"type": "token", "content": status_msg})
                            yield f"data: {data}\n\n"

                        # Add assistant message with tool calls to conversation
                        assistant_tool_msg: dict[str, Any] = {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": json.dumps(tc["arguments"]),
                                    },
                                }
                                for tc in pending_tool_calls
                            ],
                        }
                        if round_content:
                            assistant_tool_msg["content"] = round_content
                        messages.append(assistant_tool_msg)

                        # Execute each tool and add results
                        for tc in pending_tool_calls:
                            result = await execute_tool(
                                db=server._db,
                                tool_name=tc["name"],
                                arguments=tc["arguments"],
                                calendar_client=server._get_calendar_client(),
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result,
                            })

                        # Loop continues — LLM will see tool results and respond
                    else:
                        # Exceeded MAX_TOOL_ROUNDS — send a safety message
                        logger.warning("Chat tool-calling exceeded max rounds")
                        safety_msg = "\n\n_[Action limit reached. Please verify the results.]_"
                        data = json.dumps({"type": "token", "content": safety_msg})
                        yield f"data: {data}\n\n"
                        # Don't add safety message to full_response — it's UI-only

                except Exception as e:
                    logger.error(f"LLM streaming failed: {e}")
                    error_msg = "I'm having trouble connecting to the AI service right now. Please try again in a moment."
                    data = json.dumps({"type": "token", "content": error_msg})
                    yield f"data: {data}\n\n"
                    full_response = error_msg
            else:
                # No router — fallback to memory-only response
                if memory_context:
                    fallback = "Based on what I remember:\n"
                    for doc in (server._memory.search(body.message, max_results=3) if server._memory else []):
                        fallback += f"\n- {doc.text[:200]}"
                else:
                    fallback = "Ciao! I'm OmniBrain. I'm awake but the LLM router isn't configured yet. Check your API keys in .env."
                words = fallback.split()
                for i, word in enumerate(words):
                    tok = word + (" " if i < len(words) - 1 else "")
                    data = json.dumps({"type": "token", "content": tok})
                    yield f"data: {data}\n\n"
                    await asyncio.sleep(0.02)
                full_response = fallback

            # ── 6. Persist assistant response ──
            if full_response.strip():
                try:
                    server._db.save_chat_message(session_id, "assistant", full_response)
                except Exception as e:
                    logger.warning(f"Failed to save assistant message: {e}")

            # ── 7. Store conversation in memory ──
            if server._memory and body.message.strip() and full_response.strip():
                try:
                    server._memory.store(
                        text=f"User: {body.message}\nAssistant: {full_response[:500]}",
                        source="chat",
                        source_type="conversation",
                        metadata={"session_id": session_id},
                    )
                except Exception as e:
                    logger.warning(f"Failed to store chat in memory: {e}")

            # ── 8. Observe action for pattern detection ──
            pd = getattr(server, "_pattern_detector", None)
            if pd:
                try:
                    pd.observe_action(
                        action_type="chat",
                        description=f"User asked: {body.message[:100]}",
                        context={"session_id": session_id},
                    )
                except Exception:
                    pass

            # ── 8b. Extract structured data from conversation ──
            # Skip extraction if tool calls were made — tools already
            # performed the actions (created/deleted events, etc.)
            if (
                server._router
                and body.message.strip()
                and full_response.strip()
                and not tools_were_used
            ):
                try:
                    from omnibrain.conversation_extractor import extract_and_persist

                    asyncio.create_task(
                        extract_and_persist(
                            user_message=body.message,
                            assistant_response=full_response,
                            router=server._router,
                            db=server._db,
                            memory=server._memory,
                            session_id=session_id,
                        )
                    )
                except Exception as e:
                    logger.debug("Extraction task launch failed: %s", e)

            # ── 9. Track LLM cost ──
            if total_input_tokens or total_output_tokens:
                try:
                    # Estimate cost using DeepSeek pricing as default
                    cost_in = total_input_tokens * 0.00014 / 1000
                    cost_out = total_output_tokens * 0.00028 / 1000
                    call_cost = cost_in + cost_out
                    month_cost = float(server._db.get_preference("llm_month_cost", "0") or "0")
                    month_calls = int(server._db.get_preference("llm_month_calls", "0") or "0")
                    server._db.set_preference(
                        "llm_month_cost",
                        str(round(month_cost + call_cost, 6)),
                        learned_from="cost_tracker",
                    )
                    server._db.set_preference(
                        "llm_month_calls",
                        str(month_calls + 1),
                        learned_from="cost_tracker",
                    )
                except Exception:
                    pass

            # ── 10. Done signal ──
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

"""
OmniBrain — Agent ↔ Chat Bridge

Maps the OmniBrainAgent's async AgentEvent stream into SSE frames
for the chat endpoint, preserving all side-effects (persistence,
cost tracking, pattern detection, extraction).

Architecture:
    1. One Agent instance per session (LRU cache, max 20)
    2. Before each run: sanitize input, gather context, inject live data
    3. During run: translate AgentEvent → SSE JSON frames
    4. After run: persist response, store in memory, track cost, observe patterns
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("omnibrain.agent_bridge")


class AgentChatBridge:
    """Bridge between OmniBrainAgent and the SSE chat endpoint."""

    MAX_CACHED_AGENTS = 20

    def __init__(self, server: Any) -> None:
        self._server = server
        self._agents: OrderedDict[str, Any] = OrderedDict()  # session_id → agent

    # ─────────────────────────────────────────────────────────────────
    # Agent factory
    # ─────────────────────────────────────────────────────────────────

    def _get_or_create_agent(self, session_id: str) -> Any:
        """Get cached agent or create a new one for the session."""
        if session_id in self._agents:
            self._agents.move_to_end(session_id)
            return self._agents[session_id]

        agent = self._create_agent(session_id)
        self._agents[session_id] = agent

        # Evict oldest if over limit
        while len(self._agents) > self.MAX_CACHED_AGENTS:
            self._agents.popitem(last=False)

        return agent

    def _create_agent(self, session_id: str) -> Any:
        """Create a fresh OmniBrainAgent wired with all dependencies."""
        from omnibrain.agent_tools import build_omnibrain_tools
        from omnibrain.brain import OmniBrainAgent, OmniBrainProfile

        server = self._server

        # Build ToolRegistry with all domain tools
        tools = build_omnibrain_tools(
            db=server._db,
            memory=server._memory,
            data_dir=getattr(server, "_data_dir", None),
            calendar_client_factory=getattr(server, "_get_calendar_client", None),
        )

        # Build user profile from DB
        profile = OmniBrainProfile()
        try:
            profile.user_name = server._db.get_preference("user_name", "") or ""
            profile.timezone = server._db.get_preference("user_timezone", "") or ""
            profile.work = server._db.get_preference("user_work", "") or ""
            profile.goals = server._db.get_preference("user_goals", "") or ""
        except Exception:
            pass

        agent = OmniBrainAgent(
            user_profile=profile,
            router=server._router,
            tools=tools,
            max_iterations=10,  # Chat is conversational, not deep research
            max_tool_calls_per_iteration=10,
            max_total_tool_calls=50,
            chat_mode=True,  # Stop after first text response — prevents duplicate output bug
        )

        # Override _build_dynamic_system_prompt with the conversational chat prompt.
        # This replaces the research/investigation framing from Omnigent with a
        # concise, personal-assistant framing defined in prompts/chat_system.md.
        _chat_prompt = _load_chat_system_prompt()
        _profile = profile  # capture for closure

        def _chat_build_prompt() -> str:
            base = _chat_prompt
            # Append user profile context if available
            profile_ctx = _profile.to_prompt_summary() if hasattr(_profile, "to_prompt_summary") else ""
            if profile_ctx.strip():
                base += f"\n\n## About the User\n{profile_ctx}"
            # Live context (_extra_chat_context) is appended by stream() on each turn
            ctx = getattr(agent, "_extra_chat_context", "")
            return base + ctx if ctx else base

        agent._build_dynamic_system_prompt = _chat_build_prompt

        # Rehydrate conversation history from DB
        try:
            history = server._db.get_chat_messages(session_id, limit=20)
            for msg in history:
                agent.state.add_message(msg["role"], msg["content"])
        except Exception:
            pass

        logger.info(f"Agent created for session {session_id} ({len(tools.tools)} tools)")
        return agent

    # ─────────────────────────────────────────────────────────────────
    # Main streaming entry point
    # ─────────────────────────────────────────────────────────────────

    async def stream(
        self, message: str, session_id: str,
    ) -> AsyncGenerator[str, None]:
        """Run the agent and yield SSE data frames.

        Preserves all chat.py side-effects:
        1. Message persistence
        2. Prompt sanitization
        3. Live data context injection
        4. Cost tracking
        5. Pattern detection
        6. Conversation extraction
        """
        server = self._server

        # ── 1. Persist user message ──
        try:
            server._db.save_chat_message(session_id, "user", message)
        except Exception as e:
            logger.warning(f"Failed to save user message: {e}")

        # ── 2. Prompt injection defense ──
        sanitizer = getattr(server, "_sanitizer", None)
        sanitized_message = message
        if sanitizer and message.strip():
            try:
                result = sanitizer.sanitize_message(message)
                if result.is_blocked:
                    logger.warning(
                        f"Prompt injection BLOCKED (score={result.threat_score:.2f}): "
                        f"{result.reason}"
                    )
                    yield self._sse({
                        "type": "error",
                        "content": (
                            "⚠️ Your message was flagged as potentially unsafe and has been blocked. "
                            "This is a security measure to protect your AI. "
                            "Please rephrase your request."
                        ),
                        "threat_score": result.threat_score,
                    })
                    yield self._sse({"type": "done", "session_id": session_id})
                    return
                if result.is_warned:
                    logger.warning(
                        f"Prompt injection WARNING (score={result.threat_score:.2f}): "
                        f"{result.reason}"
                    )
                    sanitized_message = result.safe_text
            except Exception as e:
                logger.debug(f"Sanitizer check failed (non-blocking): {e}")

        # ── 3. Get or create agent ──
        agent = self._get_or_create_agent(session_id)

        # ── 4. Inject live context into agent's system prompt ──
        # The agent's _build_dynamic_system_prompt (set in _create_agent) already
        # reads _extra_chat_context from the agent — just set it here each turn.
        agent._extra_chat_context = self._build_live_context(sanitized_message)

        # ── 5. Run agent and translate events ──
        full_response = ""
        total_input_tokens = 0
        total_output_tokens = 0
        tools_were_used = False

        try:
            async for event in agent.run(sanitized_message):
                etype = event.type

                if etype == "text":
                    content = event.content
                    full_response += content
                    yield self._sse({"type": "token", "content": content})

                elif etype == "tool_start":
                    tools_were_used = True
                    tool_name = event.data.get("tool_name", "")
                    arguments = event.data.get("arguments", {})
                    yield self._sse({
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    })

                elif etype == "tool_end":
                    tool_name = event.data.get("tool_name", "")
                    tool_result = event.data.get("tool_result", "")
                    yield self._sse({
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "result": tool_result[:500],  # Truncate for SSE
                    })

                elif etype == "plan_generated":
                    plan_text = event.data.get("plan", "")
                    yield self._sse({
                        "type": "plan",
                        "content": plan_text,
                    })

                elif etype == "finding":
                    finding = event.data.get("finding")
                    yield self._sse({
                        "type": "finding",
                        "title": getattr(finding, "title", str(finding)) if finding else "",
                        "content": getattr(finding, "content", "") if finding else "",
                    })

                elif etype == "usage":
                    inp = event.data.get("input_tokens", 0)
                    out = event.data.get("output_tokens", 0)
                    total_input_tokens += inp
                    total_output_tokens += out
                    yield self._sse({
                        "type": "usage",
                        "input_tokens": inp,
                        "output_tokens": out,
                    })

                elif etype == "error":
                    error_msg = event.data.get("message", "Unknown error")
                    yield self._sse({"type": "error", "content": error_msg})

                elif etype in ("done", "paused"):
                    break

        except Exception as e:
            logger.error(f"Agent streaming failed: {e}", exc_info=True)
            error_msg = (
                "I'm having trouble connecting to the AI service right now. "
                "Please try again in a moment."
            )
            yield self._sse({"type": "token", "content": error_msg})
            full_response = error_msg

        # ── 6. Post-processing (same as original chat.py) ──
        await self._post_process(
            session_id=session_id,
            user_message=message,
            full_response=full_response,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            tools_were_used=tools_were_used,
        )

        # ── 7. Done signal ──
        yield self._sse({"type": "done", "session_id": session_id})

    # ─────────────────────────────────────────────────────────────────
    # Live context builder
    # ─────────────────────────────────────────────────────────────────

    def _build_live_context(self, message: str) -> str:
        """Build live data context to inject into agent's system prompt.

        Includes: current time, today's events, this week's events,
        pending proposals, key contacts, behavioral patterns, memory,
        skills, and project context.
        """
        server = self._server
        parts: list[str] = []

        # Current date/time (prevents LLM hallucination)
        now = datetime.now()
        parts.append(
            f"\n\n## Current Date & Time\n"
            f"Today is {now.strftime('%A, %B %d, %Y')}. "
            f"Current time: {now.strftime('%H:%M')} (local)."
        )

        # User name
        try:
            user_name = server._db.get_preference("user_name", "")
            if user_name:
                parts.append(f"\n\nThe user's name is {user_name}.")
        except Exception:
            pass

        # Today's + this week's schedule
        try:
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
                    eid = ev.get("id", "")
                    time_str = ts[11:16] if len(ts) > 11 and ts[11:16] != "00:00" else "All day"
                    events_text += f"- [id={eid}] {time_str}: {title}"
                    src = ev.get("source", "")
                    if src:
                        events_text += f" ({src})"
                    events_text += "\n"
                parts.append(events_text)

            future_events = [
                ev for ev in week_events
                if ev.get("timestamp", "")[:10] != now.strftime("%Y-%m-%d")
            ]
            if future_events:
                week_text = "\n## This Week (upcoming)\n"
                for ev in future_events[:20]:
                    ts = ev.get("timestamp", "")
                    title = ev.get("title", "Untitled")
                    eid = ev.get("id", "")
                    date_str = ts[:10] if len(ts) >= 10 else "TBD"
                    time_str = ts[11:16] if len(ts) > 11 and ts[11:16] != "00:00" else "All day"
                    week_text += f"- [id={eid}] {date_str} {time_str}: {title}\n"
                parts.append(week_text)
        except Exception as e:
            logger.warning(f"Failed to inject schedule: {e}")

        # Pending proposals
        try:
            proposals = server._db.get_pending_proposals()
            if proposals:
                text = "\n## Pending Proposals (awaiting user decision)\n"
                for prop in proposals[:10]:
                    text += (
                        f"- [{prop.get('type', 'action')}] {prop.get('title', 'Untitled')}: "
                        f"{prop.get('description', '')[:150]}\n"
                    )
                parts.append(text)
        except Exception:
            pass

        # Key contacts
        try:
            contacts = server._db.get_contacts(limit=10)
            if contacts:
                text = "\n## Key Contacts\n"
                for c in contacts:
                    name = c.name or c.email
                    text += f"- {name}"
                    if c.organization:
                        text += f" ({c.organization})"
                    if c.relationship:
                        text += f" — {c.relationship}"
                    text += "\n"
                parts.append(text)
        except Exception:
            pass

        # Observations / patterns
        try:
            observations = server._db.get_observations(days=30)
            if observations:
                text = "\n## Behavioral Patterns Observed\n"
                for obs in observations[:5]:
                    if isinstance(obs, dict):
                        text += f"- {obs.get('description', '')[:150]}\n"
                    else:
                        text += f"- {obs.description[:150]}\n"
                parts.append(text)
        except Exception:
            pass

        # Memory context — filter out agent reasoning artifacts
        sanitizer = getattr(server, "_sanitizer", None)
        if server._memory and message.strip():
            try:
                results = server._memory.search(message, max_results=5)
                if results:
                    snippets = []
                    for doc in results:
                        # Skip entries that look like internal agent reasoning
                        if _looks_like_agent_reasoning(doc.text):
                            continue
                        snippet = doc.text[:300].strip()
                        if sanitizer:
                            try:
                                san_result = sanitizer.sanitize(snippet, source=doc.source_type or "memory")
                                snippet = san_result.safe_text
                            except Exception:
                                pass
                        if doc.source:
                            snippet = f"[{doc.source_type or 'memory'}] {snippet}"
                        snippets.append(snippet)
                    if snippets:
                        parts.append(
                            "\n\n---\n**Your memories relevant to this question:**\n"
                            + "\n".join(f"- {s}" for s in snippets[:3])
                        )
            except Exception:
                pass

        # Skill responses
        runtime = getattr(server, "_skill_runtime", None)
        if runtime and message.strip():
            try:
                _loop = asyncio.get_event_loop()
                # Can't await here since we're not async — skill context built synchronously
                # Skills are checked separately if needed
            except Exception:
                pass

        # Project context resurrection
        tracker = getattr(server, "_context_tracker", None)
        if tracker and message.strip():
            try:
                all_projects = tracker.get_all_projects()
                msg_lower = message.lower()
                for proj in all_projects:
                    if proj.lower() in msg_lower:
                        summary = tracker.detect_return(proj)
                        if summary:
                            parts.append(
                                f"\n\n---\n**Project context for '{proj}'** "
                                f"(inactive {summary.days_since_last} days):\n"
                                f"{summary.format_text()}"
                            )
                            break
            except Exception:
                pass

        return "".join(parts)

    # ─────────────────────────────────────────────────────────────────
    # Post-processing
    # ─────────────────────────────────────────────────────────────────

    async def _post_process(
        self,
        session_id: str,
        user_message: str,
        full_response: str,
        total_input_tokens: int,
        total_output_tokens: int,
        tools_were_used: bool,
    ) -> None:
        """Run all post-stream side effects."""
        server = self._server

        # Persist assistant response
        if full_response.strip():
            try:
                server._db.save_chat_message(session_id, "assistant", full_response)
            except Exception as e:
                logger.warning(f"Failed to save assistant message: {e}")

        # Store in semantic memory — strip agent internals before persisting
        if server._memory and user_message.strip() and full_response.strip():
            try:
                clean_response = _strip_agent_internals(full_response)
                if clean_response.strip():
                    server._memory.store(
                        text=f"User: {user_message}\nAssistant: {clean_response[:500]}",
                        source="chat",
                        source_type="conversation",
                        metadata={"session_id": session_id},
                    )
            except Exception as e:
                logger.warning(f"Failed to store chat in memory: {e}")

        # Pattern detection
        pd = getattr(server, "_pattern_detector", None)
        if pd:
            try:
                pd.observe_action(
                    action_type="chat",
                    description=f"User asked: {user_message[:100]}",
                    context={"session_id": session_id},
                )
            except Exception:
                pass

        # Conversation extraction (skip if tools already acted)
        if (
            server._router
            and user_message.strip()
            and full_response.strip()
            and not tools_were_used
        ):
            try:
                from omnibrain.conversation_extractor import extract_and_persist

                asyncio.create_task(
                    extract_and_persist(
                        user_message=user_message,
                        assistant_response=full_response,
                        router=server._router,
                        db=server._db,
                        memory=server._memory,
                        session_id=session_id,
                    )
                )
            except Exception as e:
                logger.debug(f"Extraction task launch failed: {e}")

        # Cost tracking
        if total_input_tokens or total_output_tokens:
            try:
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

    # ─────────────────────────────────────────────────────────────────
    # Inspection (for transparency endpoint)
    # ─────────────────────────────────────────────────────────────────

    def inspect(self, session_id: str) -> dict[str, Any]:
        """Return the agent's internal state for transparency."""
        agent = self._agents.get(session_id)
        if not agent:
            return {"error": f"No agent session '{session_id}'"}

        tools_list = []
        try:
            for name, tool in agent.tools.tools.items():
                schema = tool.get("schema", {})
                tools_list.append({
                    "name": name,
                    "description": schema.get("description", ""),
                })
        except Exception:
            pass

        plan_text = ""
        try:
            plan_text = agent.state.plan.to_prompt_summary()
        except Exception:
            pass

        findings = []
        try:
            for f in agent.state.findings:
                findings.append({
                    "title": getattr(f, "title", str(f)),
                    "content": getattr(f, "content", ""),
                })
        except Exception:
            pass

        return {
            "session_id": session_id,
            "system_prompt_preview": agent._build_dynamic_system_prompt()[:2000],
            "tools": tools_list,
            "plan": plan_text,
            "findings": findings,
            "message_count": len(agent.state.messages),
            "is_running": agent.is_running,
        }

    # ─────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _sse(data: dict) -> str:
        """Format a dict as an SSE data frame."""
        return f"data: {json.dumps(data)}\n\n"


def _load_chat_system_prompt() -> str:
    """Load the conversational chat system prompt from prompts/chat_system.md.

    Falls back to a minimal inline prompt if the file is missing.
    This prompt replaces Omnigent's research/investigation framing with a
    concise personal-assistant framing for chat sessions.
    """
    from pathlib import Path
    prompt_file = Path(__file__).parent.parent / "prompts" / "chat_system.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    # Inline fallback — never investigative, always concise
    return (
        "You are OmniBrain, a personal AI that works exclusively for the user.\n"
        "Be direct, concise, and proactive. Respond in the user's language.\n"
        "Propose actions; never execute without explicit user approval.\n"
        "Never invent facts. Never share the user's data with anyone."
    )


def _strip_agent_internals(text: str) -> str:
    """Remove internal agent reasoning from text before storing in memory.

    Prevents the memory injection bug where the LLM sees its own previous
    reasoning and repeats / confuses itself in subsequent turns.
    """
    import re
    patterns_to_remove = [
        r"Now I need to.*?\n",
        r"I(?:'ve| have) completed Phase.*?\n",
        r"\[FINDING:.*?\].*?\n",
        r"Phase \d+:.*?\n",
        r"Excellent!.*?analysis.*?\n",
        r"I(?:'m| am) now (?:going to|ready to|starting).*?\n",
        r"Let me (?:analyze|investigate|examine|check).*?\n",
        r"This (?:sets up|is|marks).*?Phase.*?\n",
    ]
    result = text
    for pattern in patterns_to_remove:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.DOTALL)
    return result.strip()


def _looks_like_agent_reasoning(text: str) -> bool:
    """Return True if text looks like internal agent reasoning we should not inject."""
    reasoning_markers = [
        "now i need to",
        "i've completed phase",
        "phase 1:", "phase 2:", "phase 3:",
        "[finding:",
        "this sets up phase",
        "i'm now ready to investigate",
        "let me analyze this",
        "excellent! i've completed",
    ]
    text_lower = text.lower()
    return any(marker in text_lower for marker in reasoning_markers)

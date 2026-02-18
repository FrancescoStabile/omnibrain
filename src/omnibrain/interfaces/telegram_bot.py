"""
OmniBrain — Telegram Bot (Day 15-16)

Primary user interface for Phase 1. Handles all commands, inline keyboards
for approval flow, and receives proactive notifications.

Commands:
    /start      — Welcome + setup
    /briefing   — Get current briefing
    /proposals  — View pending proposals
    /approve N  — Approve a proposal
    /reject N   — Reject a proposal
    /search Q   — Search memory
    /status     — Daemon status
    /settings   — Show preferences

Proactive:
    OmniBrain pushes morning briefings, urgent notifications,
    and approval requests via inline keyboard buttons.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from omnibrain.briefing import BriefingGenerator
from omnibrain.db import OmniBrainDB
from omnibrain.memory import MemoryManager

logger = logging.getLogger("omnibrain.telegram")

# Lazy imports for telegram — allows testing without actual library
_telegram_available = False
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    _telegram_available = True
except ImportError:
    logger.warning("python-telegram-bot not installed — Telegram bot disabled")


# ═══════════════════════════════════════════════════════════════════════════
# Formatters
# ═══════════════════════════════════════════════════════════════════════════


def format_proposal(p: dict[str, Any]) -> str:
    """Format a single proposal for Telegram display."""
    priority_emoji = {4: "🔴", 3: "🟠", 2: "🟡", 1: "🟢", 0: "⚪"}
    emoji = priority_emoji.get(p.get("priority", 2), "⚪")
    return (
        f"{emoji} *#{p['id']}* — {_escape_md(p.get('title', 'Untitled'))}\n"
        f"Type: {p.get('type', '?')} | Priority: {p.get('priority', 2)}\n"
        f"{_escape_md(p.get('description', '')[:200])}"
    )


def format_status(stats: dict[str, int], engine_status: dict[str, Any] | None = None) -> str:
    """Format daemon status for Telegram."""
    lines = [
        "📊 *OmniBrain Status*\n",
        f"Events: {stats.get('events', 0)}",
        f"Contacts: {stats.get('contacts', 0)}",
        f"Proposals pending: {stats.get('proposals_pending', 0)}",
        f"Observations: {stats.get('observations', 0)}",
        f"Briefings: {stats.get('briefings', 0)}",
        f"Active sessions: {stats.get('active_sessions', 0)}",
    ]
    if engine_status:
        running = "✅ Running" if engine_status.get("running") else "⏸ Stopped"
        lines.append(f"\nEngine: {running}")
        lines.append(f"Tasks: {engine_status.get('task_count', 0)}")
    return "\n".join(lines)


def format_memory_results(results: list[Any], query: str) -> str:
    """Format memory search results for Telegram."""
    if not results:
        return f"🔍 No results for: _{_escape_md(query)}_"
    lines = [f"🔍 *{len(results)} results* for: _{_escape_md(query)}_\n"]
    for i, doc in enumerate(results[:5], 1):
        text = doc.text if hasattr(doc, "text") else str(doc)
        source = doc.source_type if hasattr(doc, "source_type") else "?"
        score = f" ({doc.score:.2f})" if hasattr(doc, "score") and doc.score else ""
        lines.append(f"{i}\\. \\[{_escape_md(source)}\\]{score} {_escape_md(text[:150])}")
    if len(results) > 5:
        lines.append(f"\n_\\.\\.\\. and {len(results) - 5} more_")
    return "\n".join(lines)


def format_settings(prefs: dict[str, Any]) -> str:
    """Format user preferences for Telegram."""
    if not prefs:
        return "⚙️ No preferences set yet\\."
    lines = ["⚙️ *Settings*\n"]
    for key, value in sorted(prefs.items()):
        lines.append(f"• `{_escape_md(key)}`: {_escape_md(str(value))}")
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    result = []
    for ch in text:
        if ch in special:
            result.append(f"\\{ch}")
        else:
            result.append(ch)
    return "".join(result)


# ═══════════════════════════════════════════════════════════════════════════
# Telegram Bot
# ═══════════════════════════════════════════════════════════════════════════


class OmniBrainTelegramBot:
    """Full Telegram bot for OmniBrain.

    Usage:
        bot = OmniBrainTelegramBot(
            token="...",
            db=db,
            briefing_generator=briefing_gen,
            memory_manager=memory_mgr,
        )
        await bot.start()   # Starts polling in background
        await bot.stop()

    Or for testing without starting the full polling loop:
        bot = OmniBrainTelegramBot(...)
        response = await bot.handle_command("/briefing", chat_id=123)
    """

    def __init__(
        self,
        token: str,
        db: OmniBrainDB,
        briefing_generator: BriefingGenerator | None = None,
        memory_manager: MemoryManager | None = None,
        allowed_chat_ids: list[int] | None = None,
        engine_status_fn: Any = None,
    ):
        self._token = token
        self._db = db
        self._briefing_gen = briefing_generator
        self._memory = memory_manager
        self._allowed_chat_ids = set(allowed_chat_ids) if allowed_chat_ids else None
        self._engine_status_fn = engine_status_fn
        self._app: Any = None
        self._running = False
        self._notification_queue: list[dict[str, str]] = []

    @property
    def running(self) -> bool:
        return self._running

    # ── Access Control ──

    def is_authorized(self, chat_id: int) -> bool:
        """Check if a chat ID is authorized to use the bot.

        If no allowed_chat_ids are set, all chats are allowed.
        """
        if self._allowed_chat_ids is None:
            return True
        return chat_id in self._allowed_chat_ids

    # ── Lifecycle ──

    def build_app(self) -> Any:
        """Build the telegram Application with all handlers registered.

        Returns the Application object (useful for testing).
        """
        if not _telegram_available:
            raise RuntimeError("python-telegram-bot is not installed")

        builder = Application.builder().token(self._token)
        self._app = builder.build()

        # Register command handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("briefing", self._cmd_briefing))
        self._app.add_handler(CommandHandler("proposals", self._cmd_proposals))
        self._app.add_handler(CommandHandler("approve", self._cmd_approve))
        self._app.add_handler(CommandHandler("reject", self._cmd_reject))
        self._app.add_handler(CommandHandler("search", self._cmd_search))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("settings", self._cmd_settings))
        self._app.add_handler(CommandHandler("help", self._cmd_help))

        # Inline keyboard callback handler (for approve/reject buttons)
        self._app.add_handler(CallbackQueryHandler(self._callback_handler))

        # Free text messages — forward to agent (future)
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message,
        ))

        return self._app

    async def start(self) -> None:
        """Start the bot (polling mode)."""
        if not self._app:
            self.build_app()
        self._running = True
        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot running (polling mode)")

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        self._running = False
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram bot stopped")

    # ── Command Handlers ──

    async def _cmd_start(self, update: Any, context: Any) -> None:
        """Handle /start — welcome message."""
        if not self._check_auth(update):
            return
        text = (
            "🧠 *OmniBrain*\n\n"
            "Your personal AI chief of staff\\. "
            "I monitor your email, calendar, and memory to keep you productive\\.\n\n"
            "*Commands:*\n"
            "/briefing — Today's briefing\n"
            "/proposals — Pending proposals\n"
            "/approve N — Approve proposal\n"
            "/reject N — Reject proposal\n"
            "/search query — Search memory\n"
            "/status — System status\n"
            "/settings — Preferences\n"
            "/help — This message"
        )
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    async def _cmd_briefing(self, update: Any, context: Any) -> None:
        """Handle /briefing — show latest or generate new briefing."""
        if not self._check_auth(update):
            return

        # Try to get today's briefing from DB
        latest = self._db.get_latest_briefing("morning")
        if latest and latest.get("date", "")[:10] == datetime.now().strftime("%Y-%m-%d"):
            text = latest.get("content", "No content available.")
            # Briefing is plain Markdown — escape for MarkdownV2
            await update.message.reply_text(
                _escape_md(text[:4000]),
                parse_mode="MarkdownV2",
            )
            return

        # Generate new briefing if we have a generator
        if self._briefing_gen:
            try:
                data, text, briefing_id = self._briefing_gen.generate_and_store("morning")
                await update.message.reply_text(
                    _escape_md(text[:4000]),
                    parse_mode="MarkdownV2",
                )
            except Exception as e:
                logger.error(f"Briefing generation failed: {e}")
                await update.message.reply_text("⚠️ Failed to generate briefing\\.", parse_mode="MarkdownV2")
        else:
            await update.message.reply_text("No briefing available yet\\.", parse_mode="MarkdownV2")

    async def _cmd_proposals(self, update: Any, context: Any) -> None:
        """Handle /proposals — list pending proposals with inline keyboard."""
        if not self._check_auth(update):
            return

        proposals = self._db.get_pending_proposals()
        if not proposals:
            await update.message.reply_text("✅ No pending proposals\\.", parse_mode="MarkdownV2")
            return

        for p in proposals[:10]:
            text = format_proposal(p)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{p['id']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{p['id']}"),
                ]
            ])
            await update.message.reply_text(text, parse_mode="MarkdownV2", reply_markup=keyboard)

        if len(proposals) > 10:
            await update.message.reply_text(
                f"_\\.\\.\\. and {len(proposals) - 10} more proposals_",
                parse_mode="MarkdownV2",
            )

    async def _cmd_approve(self, update: Any, context: Any) -> None:
        """Handle /approve N — approve a proposal by ID."""
        if not self._check_auth(update):
            return

        args = context.args if context and hasattr(context, "args") else []
        if not args:
            await update.message.reply_text("Usage: /approve <proposal\\_id>", parse_mode="MarkdownV2")
            return

        try:
            proposal_id = int(args[0])
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid proposal ID\\.", parse_mode="MarkdownV2")
            return

        ok = self._db.update_proposal_status(proposal_id, "approved")
        if ok:
            await update.message.reply_text(
                f"✅ Proposal \\#{proposal_id} approved\\.",
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(
                f"⚠️ Proposal \\#{proposal_id} not found\\.",
                parse_mode="MarkdownV2",
            )

    async def _cmd_reject(self, update: Any, context: Any) -> None:
        """Handle /reject N — reject a proposal by ID."""
        if not self._check_auth(update):
            return

        args = context.args if context and hasattr(context, "args") else []
        if not args:
            await update.message.reply_text("Usage: /reject <proposal\\_id>", parse_mode="MarkdownV2")
            return

        try:
            proposal_id = int(args[0])
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid proposal ID\\.", parse_mode="MarkdownV2")
            return

        reason = " ".join(args[1:]) if len(args) > 1 else ""
        ok = self._db.update_proposal_status(proposal_id, "rejected", result=reason)
        if ok:
            await update.message.reply_text(
                f"❌ Proposal \\#{proposal_id} rejected\\.",
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(
                f"⚠️ Proposal \\#{proposal_id} not found\\.",
                parse_mode="MarkdownV2",
            )

    async def _cmd_search(self, update: Any, context: Any) -> None:
        """Handle /search query — search memory."""
        if not self._check_auth(update):
            return

        args = context.args if context and hasattr(context, "args") else []
        if not args:
            await update.message.reply_text("Usage: /search <query>", parse_mode="MarkdownV2")
            return

        query = " ".join(args)

        if not self._memory:
            await update.message.reply_text("Memory search not available\\.", parse_mode="MarkdownV2")
            return

        try:
            results = self._memory.search(query, max_results=5)
            text = format_memory_results(results, query)
            await update.message.reply_text(text, parse_mode="MarkdownV2")
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            await update.message.reply_text("⚠️ Search failed\\.", parse_mode="MarkdownV2")

    async def _cmd_status(self, update: Any, context: Any) -> None:
        """Handle /status — show daemon status."""
        if not self._check_auth(update):
            return

        stats = self._db.get_stats()
        engine_status = None
        if self._engine_status_fn:
            try:
                engine_status = self._engine_status_fn()
            except Exception:
                pass

        text = format_status(stats, engine_status)
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    async def _cmd_settings(self, update: Any, context: Any) -> None:
        """Handle /settings — show user preferences."""
        if not self._check_auth(update):
            return

        prefs = self._db.get_all_preferences()
        text = format_settings(prefs)
        await update.message.reply_text(text, parse_mode="MarkdownV2")

    async def _cmd_help(self, update: Any, context: Any) -> None:
        """Handle /help — same as /start."""
        await self._cmd_start(update, context)

    # ── Callback Handler (Inline Keyboards) ──

    async def _callback_handler(self, update: Any, context: Any) -> None:
        """Handle inline keyboard button presses (approve/reject)."""
        query = update.callback_query
        if not query or not query.data:
            return

        chat_id = query.message.chat_id if query.message else 0
        if not self.is_authorized(chat_id):
            await query.answer("Unauthorized", show_alert=True)
            return

        data = query.data
        if data.startswith("approve:"):
            try:
                proposal_id = int(data.split(":")[1])
                ok = self._db.update_proposal_status(proposal_id, "approved")
                if ok:
                    await query.answer(f"✅ Approved #{proposal_id}")
                    await query.edit_message_text(
                        f"✅ Proposal \\#{proposal_id} — *Approved*",
                        parse_mode="MarkdownV2",
                    )
                else:
                    await query.answer(f"Not found: #{proposal_id}", show_alert=True)
            except (ValueError, IndexError):
                await query.answer("Invalid ID", show_alert=True)

        elif data.startswith("reject:"):
            try:
                proposal_id = int(data.split(":")[1])
                ok = self._db.update_proposal_status(proposal_id, "rejected")
                if ok:
                    await query.answer(f"❌ Rejected #{proposal_id}")
                    await query.edit_message_text(
                        f"❌ Proposal \\#{proposal_id} — *Rejected*",
                        parse_mode="MarkdownV2",
                    )
                else:
                    await query.answer(f"Not found: #{proposal_id}", show_alert=True)
            except (ValueError, IndexError):
                await query.answer("Invalid ID", show_alert=True)

    # ── Free Text Handler ──

    async def _handle_message(self, update: Any, context: Any) -> None:
        """Handle free text messages — performs a memory search."""
        if not self._check_auth(update):
            return

        text = update.message.text or ""
        if not text.strip():
            return

        if self._memory:
            try:
                results = self._memory.search(text, max_results=3)
                if results:
                    reply = format_memory_results(results, text)
                else:
                    reply = (
                        "🤔 I don't have anything relevant in memory yet\\.\n"
                        "Try /briefing or /status\\."
                    )
                await update.message.reply_text(reply, parse_mode="MarkdownV2")
            except Exception as e:
                logger.error(f"Message handling failed: {e}")
                await update.message.reply_text("Hmm, something went wrong\\.", parse_mode="MarkdownV2")
        else:
            await update.message.reply_text(
                "\ud83e\udd14 Memory not available\\. Use /help to see commands\\.",
                parse_mode="MarkdownV2",
            )

    # ── Auth Check ──

    def _check_auth(self, update: Any) -> bool:
        """Check authorization. Returns True if authorized."""
        if not update.message:
            return False
        chat_id = update.message.chat_id
        if not self.is_authorized(chat_id):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    update.message.reply_text("⛔ Unauthorized\\.", parse_mode="MarkdownV2")
                )
            except RuntimeError:
                pass  # No running loop — skip notification
            return False
        return True

    # ── Proactive Notifications ──

    async def send_notification(
        self,
        chat_id: int,
        level: str,
        title: str,
        message: str,
    ) -> bool:
        """Send a proactive notification to a specific chat.

        Called by ProactiveEngine via the notify callback.
        Returns True if sent successfully.
        """
        if not _telegram_available or not self._app or not self._app.bot:
            self._notification_queue.append({
                "chat_id": str(chat_id),
                "level": level,
                "title": title,
                "message": message,
            })
            return False

        level_emoji = {
            "silent": "🔇",
            "fyi": "ℹ️",
            "important": "⚠️",
            "critical": "🚨",
        }
        emoji = level_emoji.get(level, "📌")
        text = f"{emoji} *{_escape_md(title)}*\n\n{_escape_md(message[:3500])}"

        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            self._notification_queue.append({
                "chat_id": str(chat_id),
                "level": level,
                "title": title,
                "message": message,
            })
            return False

    async def send_proposal_notification(
        self,
        chat_id: int,
        proposal: dict[str, Any],
    ) -> bool:
        """Send a proposal with inline approve/reject buttons."""
        if not _telegram_available or not self._app or not self._app.bot:
            return False

        text = format_proposal(proposal)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{proposal['id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{proposal['id']}"),
            ]
        ])

        try:
            await self._app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send proposal notification: {e}")
            return False

    async def flush_notification_queue(self, chat_id: int) -> int:
        """Send any queued notifications. Returns count sent."""
        if not self._notification_queue:
            return 0

        sent = 0
        remaining: list[dict[str, str]] = []
        for notif in self._notification_queue:
            ok = await self.send_notification(
                chat_id=int(notif["chat_id"]) or chat_id,
                level=notif["level"],
                title=notif["title"],
                message=notif["message"],
            )
            if ok:
                sent += 1
            else:
                remaining.append(notif)

        self._notification_queue = remaining
        return sent

    # ── Handle Commands (for testing without Update objects) ──

    async def handle_command(self, command: str, chat_id: int = 0) -> str:
        """Process a command string and return the response text.

        This method is for testing and internal use — it doesn't require
        actual Telegram Update objects.
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""

        if cmd in ("/start", "/help"):
            return "OmniBrain — your personal AI chief of staff."

        if cmd == "/briefing":
            latest = self._db.get_latest_briefing("morning")
            if latest and latest.get("date", "")[:10] == datetime.now().strftime("%Y-%m-%d"):
                return latest.get("content", "No content.")
            if self._briefing_gen:
                try:
                    data, text, _ = self._briefing_gen.generate_and_store("morning")
                    return text
                except Exception:
                    return "Failed to generate briefing."
            return "No briefing available."

        if cmd == "/proposals":
            proposals = self._db.get_pending_proposals()
            if not proposals:
                return "No pending proposals."
            return "\n\n".join(format_proposal(p) for p in proposals[:10])

        if cmd == "/approve":
            try:
                pid = int(args_str.strip())
                ok = self._db.update_proposal_status(pid, "approved")
                return f"Approved #{pid}" if ok else f"Not found: #{pid}"
            except (ValueError, TypeError):
                return "Usage: /approve <id>"

        if cmd == "/reject":
            parts_args = args_str.strip().split(maxsplit=1)
            try:
                pid = int(parts_args[0])
                reason = parts_args[1] if len(parts_args) > 1 else ""
                ok = self._db.update_proposal_status(pid, "rejected", result=reason)
                return f"Rejected #{pid}" if ok else f"Not found: #{pid}"
            except (ValueError, IndexError):
                return "Usage: /reject <id> [reason]"

        if cmd == "/search":
            if not args_str.strip():
                return "Usage: /search <query>"
            if not self._memory:
                return "Memory search not available."
            try:
                results = self._memory.search(args_str.strip(), max_results=5)
                return f"Found {len(results)} results." if results else "No results."
            except Exception:
                return "Search failed."

        if cmd == "/status":
            stats = self._db.get_stats()
            return format_status(stats)

        if cmd == "/settings":
            prefs = self._db.get_all_preferences()
            return format_settings(prefs)

        return f"Unknown command: {cmd}"

"""
OmniBrain — Daemon

The main process that runs continuously via systemd or foreground.
Manages all asyncio tasks: collector, proactive engine, Telegram bot,
API server, and cleanup.

Usage:
    python -m omnibrain          # Start daemon
    python -m omnibrain start    # Same thing

Process model:
    omnibrain-daemon (main process)
    ├── collector_loop      — polls Gmail, Calendar, GitHub
    ├── proactive_loop      — checks patterns, proposes actions
    ├── briefing_scheduler  — generates daily/weekly briefings
    ├── telegram_bot        — listens for user messages
    ├── api_server          — REST API for CLI + desktop app
    └── cleanup_loop        — maintains DB, prunes old data
"""

from __future__ import annotations

import asyncio
import logging
import logging.handlers
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from omnibrain import __version__
from omnibrain.config import OmniBrainConfig
from omnibrain.db import OmniBrainDB
from omnibrain.skill_context import EventBus

logger = logging.getLogger("omnibrain.daemon")


# ═══════════════════════════════════════════════════════════════════════════
# Shared Resource Container — eliminates triple resource creation
# ═══════════════════════════════════════════════════════════════════════════


class ResourceContainer:
    """Shared resources for all daemon subsystems.

    Created once in run(), used everywhere — no more
    MemoryManager×3, LLMRouter×3, etc.
    """

    def __init__(self, config: OmniBrainConfig, db: OmniBrainDB) -> None:
        self.config = config
        self.db = db
        self.memory: Any = None
        self.router: Any = None
        self.briefing_gen: Any = None
        self.knowledge_graph: Any = None
        self.pattern_detector: Any = None
        self.review_engine: Any = None
        self.approval_gate: Any = None
        self.sanitizer: Any = None
        self.context_tracker: Any = None
        self.transparency_logger: Any = None
        self.secure_storage: Any = None
        self.preference_model: Any = None

    def initialize(self) -> None:
        """Create all shared resources once."""
        # Memory
        try:
            from omnibrain.memory import MemoryManager
            self.memory = MemoryManager(self.config.data_dir, enable_chroma=False)
        except Exception as e:
            logger.warning("Failed to create MemoryManager: %s", e)

        # LLM Router
        try:
            import os

            from omnigent.router import LLMRouter, Provider
            if os.environ.get("DEEPSEEK_API_KEY"):
                self.router = LLMRouter(primary=Provider.DEEPSEEK)
            elif os.environ.get("OPENAI_API_KEY"):
                self.router = LLMRouter(primary=Provider.OPENAI)
            elif os.environ.get("ANTHROPIC_API_KEY"):
                self.router = LLMRouter(primary=Provider.CLAUDE)
            if self.router:
                logger.info("LLM router initialized")
        except Exception as e:
            logger.warning("Failed to create LLM router: %s", e)

        # BriefingGenerator
        try:
            from omnibrain.briefing import BriefingGenerator
            self.briefing_gen = BriefingGenerator(self.db, self.memory, router=self.router)
        except Exception as e:
            logger.warning("Failed to create BriefingGenerator: %s", e)

        # KnowledgeGraph
        if self.memory:
            try:
                from omnibrain.knowledge_graph import KnowledgeGraph
                self.knowledge_graph = KnowledgeGraph(self.db, self.memory)
                logger.info("KnowledgeGraph wired")
            except Exception as e:
                logger.warning("Failed to create KnowledgeGraph: %s", e)

        # PatternDetector
        try:
            from omnibrain.proactive.patterns import PatternDetector
            self.pattern_detector = PatternDetector(self.db)
        except Exception as e:
            logger.warning("Failed to create PatternDetector: %s", e)

        # ReviewEngine
        try:
            from omnibrain.review_engine import ReviewEngine
            self.review_engine = ReviewEngine(self.db, self.memory)
            logger.info("ReviewEngine wired")
        except Exception as e:
            logger.warning("Failed to create ReviewEngine: %s", e)

        # ApprovalGate
        try:
            from omnibrain.approval import ApprovalGate
            self.approval_gate = ApprovalGate(self.db)
            logger.info("ApprovalGate wired")
        except Exception as e:
            logger.warning("Failed to create ApprovalGate: %s", e)

        # PromptSanitizer
        try:
            from omnibrain.prompt_injection import PromptSanitizer
            self.sanitizer = PromptSanitizer()
            logger.info("PromptSanitizer wired")
        except Exception as e:
            logger.warning("Failed to create PromptSanitizer: %s", e)

        # ContextTracker
        try:
            from omnibrain.context_resurrection import ContextTracker
            self.context_tracker = ContextTracker(self.db, memory=self.memory)
            logger.info("ContextTracker wired")
        except Exception as e:
            logger.warning("Failed to create ContextTracker: %s", e)

        # TransparencyLogger — audit trail for every LLM call
        try:
            from omnibrain.transparency import TransparencyLogger
            self.transparency_logger = TransparencyLogger(self.config.data_dir)
            logger.info("TransparencyLogger wired")
            # Wire the router stream hook so every LLM call is logged automatically
            if self.router and self.transparency_logger:
                self.router.set_stream_hook(
                    self.transparency_logger.log_from_hook, source="daemon"
                )
                logger.info("TransparencyLogger hooked into router")
        except Exception as e:
            logger.warning("Failed to create TransparencyLogger: %s", e)

        # SecureStorage — encrypted vault for tokens and secrets
        try:
            from omnibrain.secure_storage import SecureStorage
            passphrase = self.config.get("OMNIBRAIN_ENCRYPTION_KEY", "")
            self.secure_storage = SecureStorage(self.config.data_dir, passphrase=passphrase)
            # Migrate plaintext Google token to vault on first run
            self.secure_storage.migrate_google_token(self.config.data_dir)
            logger.info("SecureStorage wired (encrypted=%s)", self.secure_storage.is_encrypted)
        except Exception as e:
            logger.warning("Failed to create SecureStorage: %s", e)

        # PreferenceModel — behavioral profile learned from interactions
        try:
            from omnibrain.preference_model import PreferenceModel
            self.preference_model = PreferenceModel(self.db)
            logger.info("PreferenceModel wired")
        except Exception as e:
            logger.warning("Failed to create PreferenceModel: %s", e)


class OmniBrainDaemon:
    """The OmniBrain daemon — runs forever, monitors everything."""

    def __init__(self, config: OmniBrainConfig | None = None) -> None:
        self.config = config or OmniBrainConfig()
        self.db: OmniBrainDB | None = None
        self.resources: ResourceContainer | None = None
        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []
        self._console = Console()
        self._start_time: datetime | None = None
        self._event_bus = EventBus()
        self._proactive_engine: Any = None
        self._skill_runtime: Any = None
        # Startup coordination events
        self._skill_ready = asyncio.Event()
        self._proactive_ready = asyncio.Event()

    async def run(self) -> None:
        """Main entry point — start the daemon and run forever."""
        self._running = True
        self._start_time = datetime.now()

        # Setup
        self._setup_logging()
        self._setup_signals()
        self.config.ensure_data_dir()
        self.db = OmniBrainDB(self.config.data_dir)

        self._print_banner()

        # Verify minimum config
        if not self.config.has_api_key():
            self._console.print(
                "\n[bold red]⚠ No LLM API keys configured.[/]\n"
                "Run [bold cyan]omnibrain setup[/] or set DEEPSEEK_API_KEY in .env\n"
            )

        logger.info(f"OmniBrain v{__version__} starting — PID {self._get_pid()}")
        logger.info(f"Data directory: {self.config.data_dir}")
        logger.info(f"Database: {self.config.db_path}")

        # Initialize shared resources ONCE
        self.resources = ResourceContainer(self.config, self.db)
        self.resources.initialize()

        # Auto-activate demo mode if no real data present
        try:
            from omnibrain.demo_data import DemoDataManager
            memory = getattr(self.resources, "memory", None)
            demo_mgr = DemoDataManager(self.db, memory=memory)
            if demo_mgr.should_auto_activate():
                demo_mgr.activate()
                logger.info("Demo mode auto-activated (no real data detected)")
        except Exception as e:
            logger.debug("Demo mode auto-activation skipped: %s", e)

        try:
            # Launch all concurrent tasks
            self._tasks = [
                asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
                asyncio.create_task(self._collector_loop(), name="collector"),
                asyncio.create_task(self._proactive_loop(), name="proactive"),
                asyncio.create_task(self._cleanup_loop(), name="cleanup"),
                asyncio.create_task(self._skill_runtime_loop(), name="skill_runtime"),
                asyncio.create_task(self._api_server(), name="api"),
                asyncio.create_task(self._telegram_bot(), name="telegram"),
            ]

            # Wait for all tasks (they run until shutdown)
            await asyncio.gather(*self._tasks, return_exceptions=True)

        except asyncio.CancelledError:
            logger.info("Daemon received cancellation signal.")
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Graceful shutdown — cancel all tasks, close connections."""
        logger.info("Shutting down OmniBrain daemon...")
        self._running = False

        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to finish cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._console.print("\n[bold cyan]OmniBrain daemon stopped.[/]\n")
        logger.info("OmniBrain daemon stopped.")

    # ── Signal Handling ──

    def _setup_signals(self) -> None:
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_signal, sig)

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name} — initiating graceful shutdown")
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

    # ── Logging ──

    def _setup_logging(self) -> None:
        """Configure structured logging."""
        log_dir = self.config.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "omnibrain.log"

        # File handler (JSON)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB per file, 5 backups
        )
        file_handler.setFormatter(logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "msg": "%(message)s"}'
        ))

        # Console handler (simple, colored)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

        # Configure root omnibrain logger
        root_logger = logging.getLogger("omnibrain")
        root_logger.setLevel(getattr(logging, self.config.log_level, logging.INFO))
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    # ── Core Loops ──

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat — confirms daemon is alive."""
        while self._running:
            try:
                uptime = self._get_uptime()
                stats = self.db.get_stats() if self.db else {}
                logger.info(
                    f"OmniBrain alive — uptime: {uptime}, "
                    f"events: {stats.get('events', 0)}, "
                    f"proposals: {stats.get('proposals_pending', 0)} pending"
                )
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(30)

    async def _collector_loop(self) -> None:
        """Poll integrations for new data.

        Currently implements Gmail and Calendar polling.
        Phase 2: GitHub polling.
        """
        logger.info("Collector loop started")

        # Track last check time to avoid re-fetching
        last_gmail_check: datetime | None = None
        last_calendar_check: datetime | None = None

        while self._running:
            try:
                # ── Gmail Polling ──
                if self.config.has_google():
                    try:
                        last_gmail_check = await self._collect_gmail(last_gmail_check)
                    except Exception as e:
                        logger.error(f"Gmail collection failed: {e}")

                # ── Calendar Polling ──
                if self.config.has_google():
                    try:
                        last_calendar_check = await self._collect_calendar(last_calendar_check)
                    except Exception as e:
                        logger.error(f"Calendar collection failed: {e}")

                # Phase 2: GitHub polling

                await asyncio.sleep(self.config.check_interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Collector error: {e}")
                await asyncio.sleep(60)

    async def _collect_gmail(self, last_check: datetime | None) -> datetime:
        """Fetch new emails from Gmail and store in DB.

        Runs in executor to avoid blocking the event loop (Gmail API is sync).

        Args:
            last_check: When we last checked. None = first check.

        Returns:
            The current timestamp (for next check's since_hours calculation).
        """
        loop = asyncio.get_running_loop()

        # Calculate hours since last check (default: 1 hour for first run after startup)
        if last_check:
            hours_since = max(1, int((datetime.now() - last_check).total_seconds() / 3600) + 1)
        else:
            hours_since = 1  # First check: just last hour

        def _sync_fetch() -> tuple[int, int]:
            """Synchronous Gmail fetch — runs in thread executor."""
            from omnibrain.integrations.gmail import GmailClient
            from omnibrain.tools.email_tools import store_emails_in_db

            client = GmailClient(self.config.data_dir)
            if not client.authenticate():
                logger.warning("Gmail authentication failed in collector")
                return (0, 0)

            emails = client.fetch_recent(
                max_results=50,
                since_hours=hours_since,
            )

            if not emails:
                return (0, 0)

            # Store in database
            events_stored, contacts_updated = store_emails_in_db(emails, self.db)
            return (events_stored, contacts_updated)

        events, contacts = await loop.run_in_executor(None, _sync_fetch)

        if events > 0:
            logger.info(f"Gmail collector: {events} new emails, {contacts} contacts updated")
            # Emit event for skills to react
            self._event_bus.publish("new_email", {"count": events, "source": "gmail"})

        return datetime.now()

    async def _collect_calendar(self, last_check: datetime | None) -> datetime:
        """Fetch today's + upcoming calendar events and store in DB.

        Runs in executor to avoid blocking the event loop.

        Args:
            last_check: When we last checked. None = first check.

        Returns:
            The current timestamp (for next check's tracking).
        """
        loop = asyncio.get_running_loop()

        def _sync_fetch() -> int:
            """Synchronous Calendar fetch — runs in thread executor."""
            from omnibrain.integrations.calendar import CalendarClient
            from omnibrain.tools.calendar_tools import store_events_in_db

            client = CalendarClient(self.config.data_dir)
            if not client.authenticate():
                logger.warning("Calendar authentication failed in collector")
                return 0

            # Fetch today's events + next 7 days
            events = client.get_upcoming_events(days=7, max_results=50)

            if not events:
                return 0

            # Store in database
            return store_events_in_db(events, self.db)

        events_stored = await loop.run_in_executor(None, _sync_fetch)

        if events_stored > 0:
            logger.info(f"Calendar collector: {events_stored} events stored")
            # Emit event for skills to react
            self._event_bus.publish("calendar_synced", {"count": events_stored, "source": "calendar"})

        return datetime.now()

    async def _proactive_loop(self) -> None:
        """Run proactive checks via the ProactiveEngine."""
        logger.info("Proactive engine starting")

        try:
            from omnibrain.proactive.engine import ProactiveEngine

            rc = self.resources

            self._proactive_engine = ProactiveEngine(self.db, self.config)
            self._proactive_engine.register_defaults(
                briefing_generator=rc.briefing_gen,
                memory_manager=rc.memory,
                review_engine=rc.review_engine,
                pattern_detector=rc.pattern_detector,
                context_tracker=rc.context_tracker,
                check_interval_minutes=self.config.check_interval_minutes,
                briefing_time=self.config.briefing_time,
                evening_time=self.config.evening_time,
            )
            logger.info(
                f"ProactiveEngine wired — {len(self._proactive_engine.tasks)} tasks"
            )
            
            # Signal that proactive engine is ready for API server wiring
            self._proactive_ready.set()
            
            await self._proactive_engine.run()
        except asyncio.CancelledError:
            if self._proactive_engine:
                await self._proactive_engine.stop()
        except Exception as e:
            logger.error(f"Proactive engine fatal: {e}", exc_info=True)
            # Fatal error — exit cleanly and let daemon handle restart if needed

    async def _cleanup_loop(self) -> None:
        """Periodic maintenance — prune old data, expire proposals, vacuum DB.

        Runs every hour.
        """
        logger.info("Cleanup loop started")

        while self._running:
            try:
                await asyncio.sleep(3600)  # Every hour

                if not self._running or not self.db:
                    break

                # Expire old proposals
                expired = self.db.expire_old_proposals()
                if expired:
                    logger.info(f"Expired {expired} old proposals")

                # Prune old data (respects retention settings)
                pruned = self.db.prune_old_data()
                if any(pruned.values()):
                    logger.info(f"Pruned old data: {pruned}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(3600)

    async def _telegram_bot(self) -> None:
        """Telegram bot interface — delegates to ``interfaces/telegram_bot.py``."""
        if not self.config.has_telegram():
            logger.info("Telegram not configured — bot disabled")
            return

        logger.info("Telegram bot starting...")
        try:
            from omnibrain.interfaces.telegram_bot import OmniBrainTelegramBot

            bot = OmniBrainTelegramBot(
                token=self.config.telegram_bot_token,
                chat_id=self.config.telegram_chat_id,
                db=self.db,
            )
            await bot.run()
        except ImportError:
            logger.warning("python-telegram-bot not installed — Telegram disabled")
        except asyncio.CancelledError:
            logger.info("Telegram bot stopped")
        except Exception as e:
            logger.error(f"Telegram bot fatal: {e}", exc_info=True)

    async def _api_server(self) -> None:
        """FastAPI REST server — delegates to ``interfaces/api_server.py``.

        Uses shared ResourceContainer for all subsystems.
        """
        logger.info(
            f"API server starting on {self.config.api_host}:{self.config.api_port}"
        )
        try:
            from omnibrain.interfaces.api_server import OmniBrainAPIServer

            rc = self.resources
            
            # Wait for subsystems to initialize before wiring (with timeout)
            logger.info("API server waiting for subsystems to initialize...")
            try:
                await asyncio.wait_for(self._skill_ready.wait(), timeout=30.0)
                logger.info("✓ SkillRuntime ready")
            except TimeoutError:
                logger.warning("SkillRuntime initialization timeout — proceeding anyway")
            
            try:
                await asyncio.wait_for(self._proactive_ready.wait(), timeout=30.0)
                logger.info("✓ ProactiveEngine ready")
            except TimeoutError:
                logger.warning("ProactiveEngine initialization timeout — proceeding anyway")
            
            engine_status = None
            if self._proactive_engine:
                engine_status = self._proactive_engine.get_status

            server = OmniBrainAPIServer(
                db=self.db,
                memory_manager=rc.memory,
                briefing_gen=rc.briefing_gen,
                engine_status_fn=engine_status,
                version=__version__,
                data_dir=self.config.data_dir,
                router=rc.router,
            )

            # Attach subsystems so endpoints can access them
            server._pattern_detector = rc.pattern_detector  # type: ignore[attr-defined]
            server._knowledge_graph = rc.knowledge_graph  # type: ignore[attr-defined]
            server._event_bus = self._event_bus  # type: ignore[attr-defined]
            server._approval_gate = rc.approval_gate  # type: ignore[attr-defined]
            server._sanitizer = rc.sanitizer  # type: ignore[attr-defined]
            server._context_tracker = rc.context_tracker  # type: ignore[attr-defined]

            # Wire new subsystems: transparency + secure storage
            if rc.transparency_logger:
                server._transparency_logger = rc.transparency_logger  # type: ignore[attr-defined]
            if rc.secure_storage:
                server._secure_storage = rc.secure_storage  # type: ignore[attr-defined]

            # Wire SkillRuntime into the API server (now guaranteed to be initialized)
            if self._skill_runtime:
                server._skill_runtime = self._skill_runtime  # type: ignore[attr-defined]
                logger.info("✓ SkillRuntime wired to API server")

            # Wire EventBus → WebSocket bridge so live events reach the frontend
            if self._event_bus:
                from omnibrain.interfaces.api_server import wire_event_bus_to_ws
                wire_event_bus_to_ws(server, self._event_bus)
                logger.info("✓ EventBus → WebSocket bridge wired")

            # Run uvicorn programmatically
            import uvicorn

            uvi_config = uvicorn.Config(
                app=server.app,
                host=self.config.api_host,
                port=self.config.api_port,
                log_level="warning",
            )
            uvi_server = uvicorn.Server(uvi_config)
            await uvi_server.serve()
        except ImportError as e:
            logger.warning(f"API server dependency missing ({e}) — API disabled")
            # Keep task alive so daemon doesn't restart it
            while self._running:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("API server stopped")
        except Exception as e:
            logger.error(f"API server fatal: {e}", exc_info=True)

    async def _skill_runtime_loop(self) -> None:
        """Discover and run Skills via the SkillRuntime."""
        logger.info("SkillRuntime starting")
        try:
            from omnibrain.skill_runtime import SkillRuntime

            rc = self.resources

            # Resolve skill directories
            project_root = Path(__file__).resolve().parent.parent.parent
            skill_dirs = [
                project_root / "skills",
                self.config.data_dir / "skills",
            ]

            self._skill_runtime = SkillRuntime(
                db=self.db,
                memory=rc.memory,
                knowledge_graph=rc.knowledge_graph,
                approval_gate=rc.approval_gate,
                config=self.config,
                event_bus=self._event_bus,
                llm_router=rc.router,
            )

            discovered = self._skill_runtime.discover(skill_dirs)
            logger.info(f"SkillRuntime: {len(discovered)} skills discovered")

            # Signal that skill runtime is ready for API server wiring
            self._skill_ready.set()

            await self._skill_runtime.run()
        except asyncio.CancelledError:
            if self._skill_runtime:
                await self._skill_runtime.stop()
        except Exception as e:
            logger.error(f"SkillRuntime fatal: {e}", exc_info=True)

    # ── Helpers ──

    def _print_banner(self) -> None:
        """Print startup banner."""
        self._console.print(Panel.fit(
            f"[bold cyan]OmniBrain v{__version__}[/]\n"
            f"[dim]The AI that never sleeps.[/]\n\n"
            f"Data: {self.config.data_dir}\n"
            f"API:  http://{self.config.api_host}:{self.config.api_port}\n"
            f"Telegram: {'configured' if self.config.has_telegram() else 'not configured'}\n"
            f"Google: {'configured' if self.config.has_google() else 'not configured'}\n"
            f"LLM keys: {self._describe_api_keys()}",
            border_style="cyan",
            title="[bold]OmniBrain Daemon[/]",
        ))

    def _describe_api_keys(self) -> str:
        """Describe which API keys are set."""
        keys = []
        if self.config.deepseek_api_key:
            keys.append("DeepSeek")
        if self.config.anthropic_api_key:
            keys.append("Anthropic")
        if self.config.openai_api_key:
            keys.append("OpenAI")
        return ", ".join(keys) if keys else "[red]none[/]"

    def _get_uptime(self) -> str:
        """Get human-readable uptime."""
        if not self._start_time:
            return "0s"
        delta = datetime.now() - self._start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @staticmethod
    def _get_pid() -> int:
        """Get current process ID."""
        import os
        return os.getpid()

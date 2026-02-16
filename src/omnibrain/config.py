"""
OmniBrain — Configuration

Extends Omnigent's Config with OmniBrain-specific settings.
Manages all API keys, preferences, and daemon configuration.

Config sources (priority: ENV > .env > config.yaml > defaults):
1. Environment variables
2. .env file in project root
3. ~/.omnibrain/config.yaml
4. Hardcoded defaults
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger("omnibrain.config")

# ═══════════════════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_DATA_DIR = Path.home() / ".omnibrain"


# ═══════════════════════════════════════════════════════════════════════════
# OmniBrain Config
# ═══════════════════════════════════════════════════════════════════════════


class OmniBrainConfig:
    """OmniBrain configuration — all settings for the daemon, integrations, and interfaces."""

    # All known config keys with their defaults
    DEFAULTS: dict[str, Any] = {
        # LLM keys
        "DEEPSEEK_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        # Telegram
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        # Daemon settings
        "OMNIBRAIN_TIMEZONE": "Europe/Rome",
        "OMNIBRAIN_BRIEFING_TIME": "07:00",
        "OMNIBRAIN_EVENING_TIME": "22:00",
        "OMNIBRAIN_CHECK_INTERVAL_MINUTES": 5,
        "OMNIBRAIN_LOG_LEVEL": "INFO",
        "OMNIBRAIN_DATA_DIR": str(DEFAULT_DATA_DIR),
        # API server
        "OMNIBRAIN_API_HOST": "127.0.0.1",
        "OMNIBRAIN_API_PORT": 7432,
        # Optional
        "OMNIBRAIN_GITHUB_TOKEN": "",
        "OMNIBRAIN_ENCRYPTION_KEY": "",
    }

    # Keys that hold sensitive API credentials
    SECRET_KEYS: set[str] = {
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "OMNIBRAIN_GITHUB_TOKEN",
        "OMNIBRAIN_ENCRYPTION_KEY",
    }

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(self.DEFAULTS)
        self._load()

    def _load(self) -> None:
        """Load config from all sources."""
        # 1. Load .env file
        load_dotenv()

        # 2. Load YAML config
        config_file = self.data_dir / "config.yaml"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    yaml_data = yaml.safe_load(f) or {}
                self._data.update(yaml_data)
            except Exception as e:
                logger.warning(f"Failed to load {config_file}: {e}")

        # 3. Environment overrides (highest priority)
        for key in self.DEFAULTS:
            env_val = os.environ.get(key)
            if env_val is not None:
                self._data[key] = env_val

    # ── Properties ──

    @property
    def data_dir(self) -> Path:
        """Where all OmniBrain data lives."""
        raw = self._data.get("OMNIBRAIN_DATA_DIR", str(DEFAULT_DATA_DIR))
        return Path(str(raw)).expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "omnibrain.db"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def google_credentials_path(self) -> Path:
        return self.data_dir / "google_credentials.json"

    @property
    def google_token_path(self) -> Path:
        return self.data_dir / "google_token.json"

    @property
    def timezone(self) -> str:
        return str(self._data["OMNIBRAIN_TIMEZONE"])

    @property
    def briefing_time(self) -> str:
        return str(self._data["OMNIBRAIN_BRIEFING_TIME"])

    @property
    def evening_time(self) -> str:
        return str(self._data["OMNIBRAIN_EVENING_TIME"])

    @property
    def check_interval_minutes(self) -> int:
        return int(self._data["OMNIBRAIN_CHECK_INTERVAL_MINUTES"])

    @property
    def log_level(self) -> str:
        return str(self._data["OMNIBRAIN_LOG_LEVEL"]).upper()

    @property
    def api_host(self) -> str:
        return str(self._data["OMNIBRAIN_API_HOST"])

    @property
    def api_port(self) -> int:
        return int(self._data["OMNIBRAIN_API_PORT"])

    @property
    def deepseek_api_key(self) -> str:
        return str(self._data.get("DEEPSEEK_API_KEY", ""))

    @property
    def anthropic_api_key(self) -> str:
        return str(self._data.get("ANTHROPIC_API_KEY", ""))

    @property
    def openai_api_key(self) -> str:
        return str(self._data.get("OPENAI_API_KEY", ""))

    @property
    def telegram_bot_token(self) -> str:
        return str(self._data.get("TELEGRAM_BOT_TOKEN", ""))

    @property
    def telegram_chat_id(self) -> str:
        return str(self._data.get("TELEGRAM_CHAT_ID", ""))

    @property
    def github_token(self) -> str:
        return str(self._data.get("OMNIBRAIN_GITHUB_TOKEN", ""))

    # ── Access ──

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has_api_key(self) -> bool:
        """Check if at least one LLM API key is set."""
        return bool(
            self.deepseek_api_key
            or self.anthropic_api_key
            or self.openai_api_key
        )

    def has_telegram(self) -> bool:
        """Check if Telegram is configured."""
        return bool(self.telegram_bot_token)

    def has_google(self) -> bool:
        """Check if Google OAuth tokens exist."""
        return self.google_token_path.exists()

    # ── Persistence ──

    def save(self) -> None:
        """Save non-secret config to YAML. Secrets stay in .env or env vars."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.data_dir / "config.yaml"

        safe_data = {
            k: v for k, v in self._data.items()
            if k not in self.SECRET_KEYS and v != self.DEFAULTS.get(k)
        }

        try:
            with open(config_file, "w") as f:
                yaml.dump(safe_data, f, default_flow_style=False)
            logger.info(f"Config saved to {config_file}")
        except OSError as e:
            logger.error(f"Failed to save config: {e}")

    def ensure_data_dir(self) -> None:
        """Create data directory and subdirectories."""
        for subdir in ["", "logs", "chroma", "sessions", "exports"]:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)

        # Set secure permissions on data dir
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:
            pass

    def __repr__(self) -> str:
        keys = []
        if self.deepseek_api_key:
            keys.append("DeepSeek")
        if self.anthropic_api_key:
            keys.append("Anthropic")
        if self.openai_api_key:
            keys.append("OpenAI")
        return (
            f"OmniBrainConfig(data_dir={self.data_dir}, "
            f"api_keys=[{', '.join(keys)}], "
            f"telegram={'yes' if self.has_telegram() else 'no'})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Interactive Setup
# ═══════════════════════════════════════════════════════════════════════════


def interactive_setup() -> OmniBrainConfig:
    """Interactive first-time setup wizard."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    config = OmniBrainConfig()

    console.print(Panel.fit(
        "[bold cyan]OmniBrain Setup Wizard[/]\n\n"
        "Let's configure your personal AI agent.\n"
        "You'll need at least one LLM API key to start.",
        border_style="cyan",
    ))

    # ── LLM Keys ──
    console.print("\n[bold]Step 1: LLM API Keys[/]")
    console.print("[dim]At least one is required. DeepSeek is cheapest (~$0.50/month).[/]\n")

    console.print("[bold green]DeepSeek[/] → https://platform.deepseek.com/api_keys")
    key = Prompt.ask("  DeepSeek API Key", default="", password=True)
    if key:
        config.set("DEEPSEEK_API_KEY", key)

    console.print("\n[bold yellow]Anthropic Claude[/] → https://console.anthropic.com/settings/keys")
    key = Prompt.ask("  Claude API Key (Enter to skip)", default="", password=True)
    if key:
        config.set("ANTHROPIC_API_KEY", key)

    console.print("\n[bold blue]OpenAI[/] → https://platform.openai.com/api-keys")
    key = Prompt.ask("  OpenAI API Key (Enter to skip)", default="", password=True)
    if key:
        config.set("OPENAI_API_KEY", key)

    if not config.has_api_key():
        console.print("\n[bold red]⚠ No API keys set.[/] OmniBrain needs at least one LLM provider.")
        console.print("Set one via environment: [dim]export DEEPSEEK_API_KEY=sk-...[/]\n")
        return config

    # ── Telegram ──
    console.print("\n[bold]Step 2: Telegram Bot (optional)[/]")
    console.print("[dim]Message @BotFather on Telegram to create a bot.[/]\n")

    token = Prompt.ask("  Telegram Bot Token (Enter to skip)", default="")
    if token:
        config.set("TELEGRAM_BOT_TOKEN", token)
        chat_id = Prompt.ask("  Your Telegram Chat ID", default="")
        if chat_id:
            config.set("TELEGRAM_CHAT_ID", chat_id)

    # ── Preferences ──
    console.print("\n[bold]Step 3: Preferences[/]\n")

    tz = Prompt.ask("  Timezone", default=config.timezone)
    config.set("OMNIBRAIN_TIMEZONE", tz)

    briefing = Prompt.ask("  Morning briefing time", default=config.briefing_time)
    config.set("OMNIBRAIN_BRIEFING_TIME", briefing)

    # ── Save ──
    config.ensure_data_dir()
    config.save()

    # Save secrets to .env in data dir
    env_path = config.data_dir / ".env"
    secrets = {k: config.get(k) for k in config.SECRET_KEYS if config.get(k)}
    if secrets:
        with open(env_path, "w") as f:
            for k, v in secrets.items():
                f.write(f'{k}="{v}"\n')
        os.chmod(env_path, 0o600)

    console.print(f"\n[bold green]✓ Setup complete![/]")
    console.print(f"  Config: {config.data_dir / 'config.yaml'}")
    if secrets:
        console.print(f"  Secrets: {env_path} (chmod 600)")
    console.print(f"\n  Start OmniBrain: [bold cyan]omnibrain start[/]\n")

    return config

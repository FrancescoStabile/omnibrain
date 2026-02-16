#!/usr/bin/env python3
"""
OmniBrain — Google OAuth Setup Wizard

Interactive wizard to authenticate OmniBrain with Google APIs (Gmail + Calendar).

Usage:
    python scripts/setup_google.py
    # or
    omnibrain setup-google

Steps:
    1. User downloads credentials.json from Google Cloud Console
    2. This script reads credentials.json and opens browser for OAuth consent
    3. After consent, stores token.json in ~/.omnibrain/
    4. Token auto-refreshes — user never needs to re-auth unless revoked

Prerequisites:
    1. Go to https://console.cloud.google.com/
    2. Create a project (or use existing)
    3. Enable "Gmail API" and "Google Calendar API"
    4. Create OAuth 2.0 credentials (Desktop App type)
    5. Download credentials.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Ensure we can import omnibrain even when run as a script ──
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root / "src") not in sys.path:
    sys.path.insert(0, str(_project_root / "src"))


# ═══════════════════════════════════════════════════════════════════════════
# Scopes
# ═══════════════════════════════════════════════════════════════════════════

# Phase 1: read-only access
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

# Phase 2 will add:
# "https://www.googleapis.com/auth/gmail.send"
# "https://www.googleapis.com/auth/gmail.modify"
# "https://www.googleapis.com/auth/calendar.events"


def find_credentials_file(config_data_dir: Path) -> Path | None:
    """Look for credentials.json in common locations."""
    candidates = [
        config_data_dir / "google_credentials.json",
        config_data_dir / "credentials.json",
        Path.cwd() / "credentials.json",
        Path.home() / "Downloads" / "credentials.json",
        Path.home() / "credentials.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def validate_credentials_file(path: Path) -> bool:
    """Check that the credentials file looks like a valid Google OAuth client config."""
    try:
        with open(path) as f:
            data = json.load(f)
        # Google OAuth credentials have "installed" or "web" top-level key
        return "installed" in data or "web" in data
    except (json.JSONDecodeError, OSError):
        return False


def setup_google() -> bool:
    """Run the Google OAuth setup flow. Returns True on success."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("\n❌ Google auth libraries not installed.")
        print("   Run: pip install google-auth-oauthlib google-api-python-client google-auth-httplib2\n")
        return False

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm, Prompt
        console = Console()
        _rich = True
    except ImportError:
        console = None  # type: ignore[assignment]
        _rich = False

    from omnibrain.config import OmniBrainConfig

    config = OmniBrainConfig()
    config.ensure_data_dir()
    token_path = config.google_token_path
    creds_path = config.google_credentials_path

    # ── Check if already authenticated ──
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds and creds.valid:
                if _rich:
                    console.print("\n[bold green]✓ Google already authenticated![/]")
                    console.print(f"  Token: [dim]{token_path}[/]\n")
                else:
                    print(f"\n✓ Google already authenticated! Token: {token_path}\n")

                # Ask if they want to re-authenticate
                if _rich:
                    redo = Confirm.ask("  Re-authenticate?", default=False)
                else:
                    redo = input("  Re-authenticate? [y/N]: ").strip().lower() == "y"

                if not redo:
                    return True
        except Exception:
            pass  # Token corrupt or invalid — proceed with setup

    # ── Banner ──
    if _rich:
        console.print(Panel.fit(
            "[bold cyan]Google OAuth Setup[/]\n\n"
            "This wizard connects OmniBrain to your Gmail and Google Calendar.\n"
            "You'll need a [bold]credentials.json[/] file from Google Cloud Console.\n\n"
            "[dim]Guide: https://console.cloud.google.com/apis/credentials[/]",
            border_style="cyan",
            title="[bold]OmniBrain[/]",
        ))
    else:
        print("\n═══ Google OAuth Setup ═══")
        print("This wizard connects OmniBrain to your Gmail and Google Calendar.\n")

    # ── Find or ask for credentials.json ──
    found = find_credentials_file(config.data_dir)
    if found:
        if _rich:
            console.print(f"\n[bold green]✓ Found credentials file:[/] {found}")
            use_found = Confirm.ask("  Use this file?", default=True)
        else:
            print(f"\n✓ Found credentials file: {found}")
            use_found = input("  Use this file? [Y/n]: ").strip().lower() != "n"

        if use_found:
            source_creds = found
        else:
            if _rich:
                source_creds = Path(Prompt.ask("  Path to credentials.json"))
            else:
                source_creds = Path(input("  Path to credentials.json: ").strip())
    else:
        if _rich:
            console.print("\n[bold yellow]⚠ No credentials.json found.[/]")
            console.print("  Download from: [link]https://console.cloud.google.com/apis/credentials[/]")
            console.print("  Steps:")
            console.print("    1. Create/select project")
            console.print("    2. Enable Gmail API + Calendar API")
            console.print("    3. Create OAuth 2.0 Client ID (Desktop App)")
            console.print("    4. Download JSON\n")
            path_str = Prompt.ask("  Path to downloaded credentials.json")
        else:
            print("\n⚠ No credentials.json found.")
            print("  Download from: https://console.cloud.google.com/apis/credentials")
            path_str = input("  Path to downloaded credentials.json: ").strip()
        source_creds = Path(path_str)

    # Validate
    if not source_creds.exists():
        print(f"\n❌ File not found: {source_creds}")
        return False

    if not validate_credentials_file(source_creds):
        print(f"\n❌ Invalid credentials file: {source_creds}")
        print("   Expected a Google OAuth Client ID JSON file.")
        return False

    # Copy to data dir if needed
    if source_creds.resolve() != creds_path.resolve():
        import shutil
        shutil.copy2(source_creds, creds_path)
        creds_path.chmod(0o600)  # Secure permissions
        if _rich:
            console.print(f"  Copied to [dim]{creds_path}[/]")
        else:
            print(f"  Copied to {creds_path}")

    # ── Run OAuth Flow ──
    if _rich:
        console.print("\n[bold]Opening browser for Google authentication...[/]")
        console.print("[dim]If browser doesn't open, copy the URL from the terminal.[/]\n")
    else:
        print("\nOpening browser for Google authentication...")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(creds_path),
            scopes=SCOPES,
        )
        # Run local server to receive OAuth callback
        creds = flow.run_local_server(
            port=0,  # Random available port
            prompt="consent",
            authorization_prompt_message="",
        )
    except Exception as e:
        print(f"\n❌ OAuth flow failed: {e}")
        return False

    # ── Save Token ──
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }

    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)
    token_path.chmod(0o600)  # Secure permissions

    if _rich:
        console.print(f"\n[bold green]✓ Authentication successful![/]")
        console.print(f"  Token saved to: [dim]{token_path}[/]")
        console.print(f"  Scopes: [dim]{', '.join(SCOPES)}[/]")
        console.print()

        # Quick test
        console.print("[dim]Testing connection...[/]")
        try:
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())

            service = build("gmail", "v1", credentials=creds)
            profile = service.users().getProfile(userId="me").execute()  # noqa: ASYNC101
            email = profile.get("emailAddress", "unknown")
            console.print(f"  [bold green]✓ Connected as:[/] {email}")
            console.print(f"  [bold green]✓ Total messages:[/] {profile.get('messagesTotal', 'N/A')}")
        except Exception as e:
            console.print(f"  [yellow]⚠ Quick test failed: {e}[/]")
            console.print("  [dim]Token was saved — this might work when daemon starts.[/]")

        console.print("\n[bold cyan]Setup complete! You can now run:[/]")
        console.print("  [bold]omnibrain fetch-emails[/]   — Fetch latest emails")
        console.print("  [bold]omnibrain start[/]          — Start daemon with Gmail polling\n")
    else:
        print(f"\n✓ Authentication successful!")
        print(f"  Token saved to: {token_path}")
        print(f"  Run 'omnibrain fetch-emails' to test.\n")

    return True


def main() -> None:
    """Entry point when run as a script."""
    success = setup_google()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

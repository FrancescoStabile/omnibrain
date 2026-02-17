"""
OmniBrain — Entry Point

Usage:
    omnibrain                     # Start daemon (foreground)
    omnibrain status              # Show daemon status
    omnibrain briefing            # Generate morning briefing
    omnibrain search "query"      # Semantic search
    omnibrain proposals           # List pending proposals
    omnibrain approve <id>        # Approve a proposal
    omnibrain setup               # Interactive setup wizard
    omnibrain --version           # Show version
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from omnibrain import __version__


def main() -> None:
    """Main entry point for OmniBrain CLI."""
    parser = argparse.ArgumentParser(
        prog="omnibrain",
        description="OmniBrain — The AI that never sleeps.",
    )
    parser.add_argument("--version", action="version", version=f"omnibrain {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # omnibrain start (default — run daemon)
    sub_start = subparsers.add_parser("start", help="Start OmniBrain daemon (foreground)")
    sub_start.add_argument("--no-proactive", action="store_true", help="Disable proactive engine")

    # omnibrain status
    subparsers.add_parser("status", help="Show daemon status and stats")

    # omnibrain briefing
    subparsers.add_parser("briefing", help="Generate and show morning briefing")

    # omnibrain search
    sub_search = subparsers.add_parser("search", help="Semantic search across memory")
    sub_search.add_argument("query", type=str, help="Search query")
    sub_search.add_argument("--limit", type=int, default=10, help="Max results")

    # omnibrain proposals
    subparsers.add_parser("proposals", help="List pending action proposals")

    # omnibrain approve
    sub_approve = subparsers.add_parser("approve", help="Approve a proposal")
    sub_approve.add_argument("proposal_id", type=str, help="Proposal ID to approve")

    # omnibrain reject
    sub_reject = subparsers.add_parser("reject", help="Reject a proposal")
    sub_reject.add_argument("proposal_id", type=str, help="Proposal ID to reject")

    # omnibrain setup
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # omnibrain fetch-emails
    sub_fetch = subparsers.add_parser("fetch-emails", help="Fetch and display recent emails")
    sub_fetch.add_argument("--max", type=int, default=10, help="Max emails to show")
    sub_fetch.add_argument("--query", type=str, default="", help="Gmail search query")
    sub_fetch.add_argument("--hours", type=int, default=24, help="Fetch emails from last N hours")
    sub_fetch.add_argument("--store", action="store_true", help="Store emails in database")

    # omnibrain setup-google
    subparsers.add_parser("setup-google", help="Interactive Google OAuth setup wizard")

    # omnibrain today
    subparsers.add_parser("today", help="Show today's calendar events")

    # omnibrain upcoming
    sub_upcoming = subparsers.add_parser("upcoming", help="Show upcoming calendar events")
    sub_upcoming.add_argument("--days", type=int, default=7, help="Days to look ahead")
    sub_upcoming.add_argument("--max", type=int, default=20, help="Max events to show")
    sub_upcoming.add_argument("--store", action="store_true", help="Store events in database")

    # omnibrain logs
    subparsers.add_parser("logs", help="Tail daemon logs")

    # omnibrain api
    sub_api = subparsers.add_parser("api", help="Start REST API server")
    sub_api.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    sub_api.add_argument("--port", type=int, default=7432, help="Port to listen on")

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # Route commands
    if args.command is None or args.command == "start":
        _cmd_start(args)
    elif args.command == "status":
        _cmd_status()
    elif args.command == "briefing":
        _cmd_briefing()
    elif args.command == "search":
        _cmd_search(args.query, args.limit)
    elif args.command == "proposals":
        _cmd_proposals()
    elif args.command == "approve":
        _cmd_approve(args.proposal_id)
    elif args.command == "reject":
        _cmd_reject(args.proposal_id)
    elif args.command == "setup":
        _cmd_setup()
    elif args.command == "fetch-emails":
        _cmd_fetch_emails(args)
    elif args.command == "setup-google":
        _cmd_setup_google()
    elif args.command == "today":
        _cmd_today()
    elif args.command == "upcoming":
        _cmd_upcoming(args)
    elif args.command == "logs":
        _cmd_logs()
    elif args.command == "api":
        _cmd_api(args)
    else:
        parser.print_help()


def _cmd_start(args: argparse.Namespace) -> None:
    """Start the OmniBrain daemon."""
    from omnibrain.daemon import OmniBrainDaemon

    daemon = OmniBrainDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        pass


def _cmd_status() -> None:
    """Show daemon status."""
    from rich.console import Console

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB

    console = Console()
    config = OmniBrainConfig()
    db = OmniBrainDB(config.data_dir)

    stats = db.get_stats()
    console.print(f"\n[bold cyan]OmniBrain v{__version__}[/]\n")
    console.print(f"  Data directory: [dim]{config.data_dir}[/]")
    console.print(f"  Events stored:  [bold]{stats.get('events', 0)}[/]")
    console.print(f"  Contacts:       [bold]{stats.get('contacts', 0)}[/]")
    console.print(f"  Proposals:      [bold]{stats.get('proposals_pending', 0)}[/] pending")
    console.print(f"  Briefings:      [bold]{stats.get('briefings', 0)}[/]")
    console.print()


def _cmd_briefing() -> None:
    """Generate and display morning briefing."""
    from rich.console import Console
    from rich.markdown import Markdown

    from omnibrain.briefing import BriefingGenerator
    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB
    from omnibrain.memory import MemoryManager

    console = Console()
    config = OmniBrainConfig()
    db = OmniBrainDB(config.data_dir)

    # Check for existing today's briefing first
    latest = db.get_latest_briefing("morning")
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    if latest and latest.get("date", "")[:10] == today:
        console.print("\n[bold cyan]Morning Briefing[/]\n")
        console.print(Markdown(latest.get("content", "No content.")))
        console.print()
        return

    # Generate new briefing
    console.print("\n[bold cyan]Generating Briefing...[/]\n")
    try:
        memory = MemoryManager(config.data_dir, enable_chroma=False)
        gen = BriefingGenerator(db, memory)
        data, text, briefing_id = gen.generate_and_store("morning")
        console.print(Markdown(text))
        console.print(f"\n[dim]Briefing saved (id={briefing_id}, events={data.events_processed}, actions={data.actions_proposed})[/]\n")
    except Exception as e:
        console.print(f"\n[bold red]Error generating briefing:[/] {e}\n")


def _cmd_search(query: str, limit: int) -> None:
    """Semantic search across memory."""
    from rich.console import Console
    from rich.table import Table

    from omnibrain.config import OmniBrainConfig
    from omnibrain.memory import MemoryManager

    console = Console()
    config = OmniBrainConfig()

    try:
        memory = MemoryManager(config.data_dir, enable_chroma=False)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/] {e}\n")
        return

    console.print(f"\n[bold cyan]Search:[/] {query}\n")
    results = memory.search(query, max_results=limit)

    if not results:
        console.print("[dim]No results found.[/]\n")
        return

    table = Table(title=f"Results ({len(results)})")
    table.add_column("#", style="dim", width=3)
    table.add_column("Source", width=10)
    table.add_column("Text", max_width=60)
    table.add_column("Score", width=8)
    table.add_column("Date", width=20, style="dim")

    for i, doc in enumerate(results, 1):
        score_str = f"{doc.score:.3f}" if doc.score else "-"
        date_str = doc.timestamp.strftime("%Y-%m-%d %H:%M") if hasattr(doc.timestamp, "strftime") else (str(doc.timestamp)[:16] if doc.timestamp else "-")
        table.add_row(str(i), doc.source_type or doc.source, doc.text[:60], score_str, date_str)

    console.print(table)
    console.print()


def _cmd_proposals() -> None:
    """List pending proposals."""
    from rich.console import Console
    from rich.table import Table

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB

    console = Console()
    config = OmniBrainConfig()
    db = OmniBrainDB(config.data_dir)

    proposals = db.get_pending_proposals()
    if not proposals:
        console.print("\n[dim]No pending proposals.[/]\n")
        return

    table = Table(title="Pending Proposals")
    table.add_column("ID", style="bold")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Priority")
    table.add_column("Created")

    for p in proposals:
        table.add_row(str(p["id"]), p["type"], p["title"], str(p["priority"]), p["created_at"])

    console.print()
    console.print(table)
    console.print()


def _cmd_approve(proposal_id: str) -> None:
    """Approve a proposal."""
    from rich.console import Console

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB

    console = Console()
    config = OmniBrainConfig()
    db = OmniBrainDB(config.data_dir)

    if db.update_proposal_status(int(proposal_id), "approved"):
        console.print(f"\n[bold green]✓[/] Proposal {proposal_id} approved.\n")
    else:
        console.print(f"\n[bold red]✗[/] Proposal {proposal_id} not found.\n")


def _cmd_reject(proposal_id: str) -> None:
    """Reject a proposal."""
    from rich.console import Console

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB

    console = Console()
    config = OmniBrainConfig()
    db = OmniBrainDB(config.data_dir)

    if db.update_proposal_status(int(proposal_id), "rejected"):
        console.print(f"\n[bold yellow]✗[/] Proposal {proposal_id} rejected.\n")
    else:
        console.print(f"\n[bold red]✗[/] Proposal {proposal_id} not found.\n")


def _cmd_setup() -> None:
    """Interactive setup wizard."""
    from omnibrain.config import interactive_setup
    interactive_setup()


def _cmd_logs() -> None:
    """Tail daemon logs."""
    from omnibrain.config import OmniBrainConfig

    config = OmniBrainConfig()
    log_file = config.data_dir / "logs" / "omnibrain.log"

    if not log_file.exists():
        print(f"No log file found at {log_file}")
        sys.exit(1)

    import subprocess
    try:
        subprocess.run(["tail", "-f", "-n", "50", str(log_file)])
    except KeyboardInterrupt:
        pass


def _cmd_fetch_emails(args: argparse.Namespace) -> None:
    """Fetch and display recent emails from Gmail."""
    from rich.console import Console
    from rich.table import Table

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB
    from omnibrain.tools.email_tools import fetch_emails, store_emails_in_db
    from omnibrain.integrations.gmail import GmailClient

    console = Console()
    config = OmniBrainConfig()

    if not config.has_google():
        console.print("\n[bold red]⚠ Google not configured.[/]")
        console.print("Run [bold cyan]omnibrain setup-google[/] first.\n")
        sys.exit(1)

    console.print(f"\n[bold cyan]Fetching emails[/] (last {args.hours}h, max {args.max})...")

    result = fetch_emails(
        data_dir=config.data_dir,
        max_results=args.max,
        query=args.query,
        since_hours=args.hours,
    )

    if result.get("error"):
        console.print(f"\n[bold red]Error:[/] {result['error']}\n")
        sys.exit(1)

    emails = result.get("emails", [])
    if not emails:
        console.print("\n[dim]No emails found.[/]\n")
        return

    # Display table
    table = Table(title=f"Recent Emails ({result['count']})")
    table.add_column("#", style="dim", width=3)
    table.add_column("From", style="bold", max_width=30)
    table.add_column("Subject", max_width=50)
    table.add_column("Date", style="dim", width=18)
    table.add_column("Read", width=4)
    table.add_column("📎", width=2)

    for i, email in enumerate(emails, 1):
        sender = email.get("sender_name") or email.get("sender_email", "?")
        subject = email.get("subject", "(no subject)")
        date_str = email.get("date", "")[:16]  # Trim to "YYYY-MM-DDTHH:MM"
        is_read = "✓" if email.get("is_read") else "[bold yellow]●[/]"
        has_attach = "📎" if email.get("has_attachments") else ""

        table.add_row(str(i), sender, subject, date_str, is_read, has_attach)

    console.print()
    console.print(table)

    # Store in DB if requested
    if args.store:
        console.print("\n[dim]Storing in database...[/]")
        # Re-fetch as EmailMessage objects for proper storage
        client = GmailClient(config.data_dir)
        if client.authenticate():
            email_msgs = client.fetch_recent(
                max_results=args.max,
                query=args.query,
                since_hours=args.hours,
            )
            db = OmniBrainDB(config.data_dir)
            events_stored, contacts_updated = store_emails_in_db(email_msgs, db)
            console.print(
                f"  [green]✓[/] Stored {events_stored} events, "
                f"updated {contacts_updated} contacts"
            )

    console.print()


def _cmd_setup_google() -> None:
    """Run Google OAuth setup wizard."""
    import os
    import subprocess

    # Find the script relative to the project root
    # omnibrain package is at src/omnibrain/, project root is ../../
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(pkg_dir, "..", "..")
    script = os.path.normpath(os.path.join(project_root, "scripts", "setup_google.py"))

    if os.path.exists(script):
        result = subprocess.run([sys.executable, script])
        sys.exit(result.returncode)
    else:
        # Fallback: try adding scripts dir to path and importing
        scripts_dir = os.path.normpath(os.path.join(project_root, "scripts"))
        sys.path.insert(0, scripts_dir)
        try:
            from setup_google import setup_google
            success = setup_google()
            sys.exit(0 if success else 1)
        except ImportError:
            print(f"setup_google.py not found at {script}")
            print("Run 'python scripts/setup_google.py' manually from the project root.")
            sys.exit(1)


def _cmd_today() -> None:
    """Show today's calendar events."""
    from rich.console import Console
    from rich.table import Table

    from omnibrain.config import OmniBrainConfig
    from omnibrain.tools.calendar_tools import get_today_events

    console = Console()
    config = OmniBrainConfig()

    if not config.has_google():
        console.print("\n[bold red]⚠ Google not configured.[/]")
        console.print("Run [bold cyan]omnibrain setup-google[/] first.\n")
        sys.exit(1)

    console.print("\n[bold cyan]Today's Calendar[/]")

    result = get_today_events(data_dir=config.data_dir)

    if result.get("error"):
        console.print(f"\n[bold red]Error:[/] {result['error']}\n")
        sys.exit(1)

    events = result.get("events", [])
    if not events:
        console.print("\n[dim]No events today. 🎉[/]\n")
        return

    table = Table(title=f"Calendar — {result.get('date', 'Today')} ({len(events)} events)")
    table.add_column("Time", style="bold", width=12)
    table.add_column("Title", max_width=40)
    table.add_column("Duration", width=10)
    table.add_column("Attendees", max_width=30)
    table.add_column("Location", max_width=20, style="dim")

    for event in events:
        start = event.get("start_time", "")
        if "T" in start:
            time_str = start.split("T")[1][:5]
        else:
            time_str = "All day"

        duration = f"{event.get('duration_minutes', 0)}min"
        attendees = event.get("attendees_summary", "solo")
        location = event.get("location", "")[:20]

        table.add_row(time_str, event.get("title", ""), duration, attendees, location)

    console.print()
    console.print(table)

    # Print summary
    if result.get("summary"):
        console.print(f"\n[dim]{result['summary']}[/]")

    console.print()


def _cmd_upcoming(args: argparse.Namespace) -> None:
    """Show upcoming calendar events."""
    from rich.console import Console
    from rich.table import Table

    from omnibrain.config import OmniBrainConfig
    from omnibrain.db import OmniBrainDB
    from omnibrain.integrations.calendar import CalendarClient
    from omnibrain.tools.calendar_tools import get_upcoming_events, store_events_in_db

    console = Console()
    config = OmniBrainConfig()

    if not config.has_google():
        console.print("\n[bold red]⚠ Google not configured.[/]")
        console.print("Run [bold cyan]omnibrain setup-google[/] first.\n")
        sys.exit(1)

    console.print(f"\n[bold cyan]Upcoming Events[/] (next {args.days} days)")

    result = get_upcoming_events(
        data_dir=config.data_dir,
        days=args.days,
        max_results=args.max,
    )

    if result.get("error"):
        console.print(f"\n[bold red]Error:[/] {result['error']}\n")
        sys.exit(1)

    events = result.get("events", [])
    if not events:
        console.print(f"\n[dim]No events in the next {args.days} days.[/]\n")
        return

    table = Table(title=f"Upcoming Events ({len(events)} events)")
    table.add_column("Date", style="bold", width=12)
    table.add_column("Time", width=8)
    table.add_column("Title", max_width=40)
    table.add_column("Duration", width=10)
    table.add_column("Attendees", max_width=20)

    for event in events:
        start = event.get("start_time", "")
        if "T" in start:
            date_str = start.split("T")[0]
            time_str = start.split("T")[1][:5]
        else:
            date_str = start[:10]
            time_str = "All day"

        duration = f"{event.get('duration_minutes', 0)}min"
        attendees = event.get("attendees_summary", "solo")

        table.add_row(date_str, time_str, event.get("title", ""), duration, attendees)

    console.print()
    console.print(table)

    # Store in DB if requested
    if args.store:
        console.print("\n[dim]Storing in database...[/]")
        client = CalendarClient(config.data_dir)
        if client.authenticate():
            cal_events = client.get_upcoming_events(days=args.days, max_results=args.max)
            db = OmniBrainDB(config.data_dir)
            stored = store_events_in_db(cal_events, db)
            console.print(f"  [green]✓[/] Stored {stored} calendar events")

    console.print()


def _cmd_api(args: argparse.Namespace) -> None:
    """Start REST API server."""
    from omnibrain.interfaces.api_server import create_api_server

    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn")
        sys.exit(1)

    server = create_api_server()
    print(f"\nOmniBrain API starting on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.\n")
    uvicorn.run(server.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

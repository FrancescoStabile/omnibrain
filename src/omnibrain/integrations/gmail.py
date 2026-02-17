"""
OmniBrain — Gmail Integration

Async-friendly Gmail client built on Google API Python Client.
Handles authentication, token refresh, email fetching, parsing,
and search. Phase 1 is read-only; Phase 2 adds send/modify.

Architecture:
    GmailClient (this file)
    └── uses google-api-python-client + google-auth
    └── returns EmailMessage dataclasses
    └── stores raw events in db.events via tools layer
"""

from __future__ import annotations

import base64
import email.utils
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from omnibrain.auth.google_oauth import GMAIL_SCOPES
from omnibrain.integrations import _is_auth_error
from omnibrain.models import EmailMessage

logger = logging.getLogger("omnibrain.integrations.gmail")

# Maximum batch size per API call
MAX_BATCH_SIZE = 100


class GmailAuthError(Exception):
    """Raised when Gmail authentication fails or token is invalid."""


class GmailClient:
    """Gmail API client — fetches and parses emails.

    Thread-safe for use in asyncio (all API calls happen in executor).
    Token refresh is automatic via google-auth.

    Usage:
        client = GmailClient(data_dir=Path("~/.omnibrain"))
        if client.authenticate():
            emails = client.fetch_recent(max_results=20)
            for email in emails:
                print(email.sender, email.subject)
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._credentials_path = data_dir / "google_credentials.json"
        self._token_path = data_dir / "google_token.json"
        self._service: Any = None
        self._creds: Any = None
        self._user_email: str = ""

    # ── Authentication ──

    def authenticate(self) -> bool:
        """Load and validate credentials. Returns True if authenticated.

        Automatically refreshes expired tokens using the refresh_token.
        Does NOT open browser — use setup_google.py for initial auth.
        """
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
        except ImportError:
            logger.error("google-auth not installed. Run: pip install google-auth-oauthlib google-api-python-client")
            return False

        if not self._token_path.exists():
            logger.warning(f"No Google token found at {self._token_path}. Run 'omnibrain setup-google' first.")
            return False

        try:
            self._creds = Credentials.from_authorized_user_file(
                str(self._token_path),
                scopes=GMAIL_SCOPES,
            )
        except Exception as e:
            logger.error(f"Failed to load Google token: {e}")
            return False

        # Refresh if expired
        if self._creds.expired and self._creds.refresh_token:
            try:
                self._creds.refresh(Request())
                # Save refreshed token
                self._save_token()
                logger.info("Google token refreshed successfully")
            except Exception as e:
                logger.error(f"Failed to refresh Google token: {e}")
                return False

        if not self._creds.valid:
            logger.error("Google credentials invalid. Run 'omnibrain setup-google' to re-authenticate.")
            return False

        # Build Gmail service
        try:
            from googleapiclient.discovery import build

            self._service = build("gmail", "v1", credentials=self._creds)
            logger.info("Gmail client authenticated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to build Gmail service: {e}")
            return False

    def _save_token(self) -> None:
        """Persist refreshed credentials back to token.json."""
        import json

        if not self._creds:
            return

        token_data = {
            "token": self._creds.token,
            "refresh_token": self._creds.refresh_token,
            "token_uri": self._creds.token_uri,
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            "scopes": list(self._creds.scopes or GMAIL_SCOPES),
        }
        try:
            with open(self._token_path, "w") as f:
                json.dump(token_data, f, indent=2)
            self._token_path.chmod(0o600)
        except OSError as e:
            logger.warning(f"Failed to save refreshed token: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Check if client is ready for API calls."""
        return self._service is not None and self._creds is not None and self._creds.valid

    @property
    def user_email(self) -> str:
        """Get the authenticated user's email address."""
        if self._user_email:
            return self._user_email
        if not self.is_authenticated:
            return ""
        try:
            profile = self._service.users().getProfile(userId="me").execute()
            self._user_email = profile.get("emailAddress", "")
            return self._user_email
        except Exception:
            return ""

    # ── Fetch Emails ──

    def fetch_recent(
        self,
        max_results: int = 20,
        query: str = "",
        since_hours: int = 24,
    ) -> list[EmailMessage]:
        """Fetch recent emails from inbox.

        Args:
            max_results: Maximum number of emails to return (capped at 100).
            query: Gmail search query (supports full Gmail search syntax).
            since_hours: Only fetch emails from the last N hours.

        Returns:
            List of EmailMessage dataclasses, newest first.

        Raises:
            GmailAuthError: If not authenticated.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated. Call authenticate() first.")

        max_results = min(max_results, MAX_BATCH_SIZE)

        # Build Gmail search query with time filter
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        # Gmail uses epoch seconds for after: filter
        after_epoch = int(since_dt.timestamp())
        full_query = f"after:{after_epoch}"
        if query:
            full_query = f"{query} {full_query}"

        try:
            # Step 1: List message IDs
            result = self._service.users().messages().list(
                userId="me",
                q=full_query,
                maxResults=max_results,
            ).execute()

            messages = result.get("messages", [])
            if not messages:
                logger.info(f"No emails found for query: {full_query}")
                return []

            logger.info(f"Found {len(messages)} emails matching query")

            # Step 2: Fetch full message details
            emails: list[EmailMessage] = []
            for msg_stub in messages:
                try:
                    email_msg = self._get_message(msg_stub["id"])
                    if email_msg:
                        emails.append(email_msg)
                except Exception as e:
                    logger.warning(f"Failed to fetch message {msg_stub['id']}: {e}")
                    continue

            logger.info(f"Fetched {len(emails)} emails successfully")
            return emails

        except Exception as e:
            if _is_auth_error(e):
                raise GmailAuthError(f"Authentication error: {e}") from e
            logger.error(f"Failed to fetch emails: {e}")
            raise

    def fetch_message(self, message_id: str) -> EmailMessage | None:
        """Fetch a single email by ID.

        Args:
            message_id: The Gmail message ID.

        Returns:
            EmailMessage or None if not found.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated.")
        return self._get_message(message_id)

    def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[EmailMessage]:
        """Search emails with Gmail search syntax.

        Examples:
            "from:boss@company.com"
            "is:unread label:important"
            "subject:invoice after:2026/02/01"

        Args:
            query: Gmail search query string.
            max_results: Maximum results to return.

        Returns:
            List of matching EmailMessage objects.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated.")

        max_results = min(max_results, MAX_BATCH_SIZE)

        try:
            result = self._service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()

            messages = result.get("messages", [])
            if not messages:
                return []

            emails: list[EmailMessage] = []
            for msg_stub in messages:
                try:
                    email_msg = self._get_message(msg_stub["id"])
                    if email_msg:
                        emails.append(email_msg)
                except Exception as e:
                    logger.warning(f"Failed to fetch message {msg_stub['id']}: {e}")
                    continue

            return emails

        except Exception as e:
            if _is_auth_error(e):
                raise GmailAuthError(f"Authentication error: {e}") from e
            logger.error(f"Search failed for query '{query}': {e}")
            raise

    def get_thread(self, thread_id: str) -> list[EmailMessage]:
        """Get all messages in an email thread.

        Args:
            thread_id: The Gmail thread ID.

        Returns:
            List of EmailMessage objects in the thread, oldest first.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated.")

        try:
            result = self._service.users().threads().get(
                userId="me",
                id=thread_id,
                format="full",
            ).execute()

            messages = result.get("messages", [])
            emails = []
            for msg_data in messages:
                email_msg = _parse_message(msg_data)
                if email_msg:
                    emails.append(email_msg)

            return emails

        except Exception as e:
            logger.error(f"Failed to fetch thread {thread_id}: {e}")
            raise

    # ── Draft & Send ──

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        thread_id: str = "",
    ) -> dict[str, str]:
        """Create an email draft in Gmail. Returns {"draft_id": ..., "message_id": ...}.

        Args:
            to: Recipient email address(es), comma-separated.
            subject: Email subject.
            body: Plain text email body.
            cc: CC addresses, comma-separated.
            bcc: BCC addresses, comma-separated.
            in_reply_to: Message-ID header of email being replied to.
            thread_id: Gmail thread ID for threading.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated")

        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        draft_body: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id

        try:
            draft = self._service.users().drafts().create(
                userId="me", body=draft_body,
            ).execute()
            draft_id = draft.get("id", "")
            message_id = draft.get("message", {}).get("id", "")
            logger.info(f"Created draft: {draft_id}")
            return {"draft_id": draft_id, "message_id": message_id}
        except Exception as e:
            logger.error(f"Failed to create draft: {e}")
            raise

    def send_draft(self, draft_id: str) -> dict[str, str]:
        """Send an existing draft. Returns {"message_id": ..., "thread_id": ...}.

        This is the actual send action — requires user approval in the approval gate.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated")

        try:
            result = self._service.users().drafts().send(
                userId="me", body={"id": draft_id},
            ).execute()
            message_id = result.get("id", "")
            thread_id = result.get("threadId", "")
            logger.info(f"Sent draft {draft_id} → message {message_id}")
            return {"message_id": message_id, "thread_id": thread_id}
        except Exception as e:
            logger.error(f"Failed to send draft {draft_id}: {e}")
            raise

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        thread_id: str = "",
    ) -> dict[str, str]:
        """Send an email directly (no draft step). Returns {"message_id": ..., "thread_id": ...}.

        Use create_draft + approval + send_draft for the approval flow.
        This is a shortcut for pre-approved sends.
        """
        if not self.is_authenticated:
            raise GmailAuthError("Not authenticated")

        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        send_body: dict[str, Any] = {"raw": raw}
        if thread_id:
            send_body["threadId"] = thread_id

        try:
            result = self._service.users().messages().send(
                userId="me", body=send_body,
            ).execute()
            message_id = result.get("id", "")
            thread_id_out = result.get("threadId", "")
            logger.info(f"Sent email → message {message_id}")
            return {"message_id": message_id, "thread_id": thread_id_out}
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise

    # ── Internal ──

    def _get_message(self, message_id: str) -> EmailMessage | None:
        """Fetch and parse a single message."""
        try:
            msg_data = self._service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()
            return _parse_message(msg_data)
        except Exception as e:
            logger.warning(f"Failed to get message {message_id}: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════
# Parsing Helpers (module-level for testability)
# ═══════════════════════════════════════════════════════════════════════════


def _parse_message(msg_data: dict[str, Any]) -> EmailMessage | None:
    """Parse a Gmail API message response into an EmailMessage.

    Handles multipart messages, decodes base64 bodies, extracts
    headers, labels, and attachment info.
    """
    try:
        headers = {
            h["name"].lower(): h["value"]
            for h in msg_data.get("payload", {}).get("headers", [])
        }

        msg_id = msg_data.get("id", "")
        thread_id = msg_data.get("threadId", "")
        label_ids = msg_data.get("labelIds", [])

        sender = headers.get("from", "")
        to_header = headers.get("to", "")
        subject = headers.get("subject", "(no subject)")
        date_str = headers.get("date", "")

        # Parse recipients
        recipients = _parse_recipients(to_header)

        # Parse date
        msg_date = _parse_date(date_str)

        # Extract body text
        body = _extract_body(msg_data.get("payload", {}))

        # Check for attachments
        has_attachments = _has_attachments(msg_data.get("payload", {}))

        # Check if read
        is_read = "UNREAD" not in label_ids

        return EmailMessage(
            id=msg_id,
            thread_id=thread_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            body=body,
            date=msg_date,
            labels=label_ids,
            is_read=is_read,
            has_attachments=has_attachments,
        )

    except Exception as e:
        logger.warning(f"Failed to parse message: {e}")
        return None


def _parse_recipients(to_header: str) -> list[str]:
    """Parse To header into list of email addresses."""
    if not to_header:
        return []

    # Handle "Name <email>, Name2 <email2>" format
    addresses = []
    for addr in email.utils.getaddresses([to_header]):
        # addr is (name, email)
        if addr[1]:
            addresses.append(addr[1])
    return addresses


def _parse_date(date_str: str) -> datetime:
    """Parse email Date header into datetime."""
    if not date_str:
        return datetime.now(timezone.utc)

    try:
        # email.utils.parsedate_to_datetime handles RFC 2822 dates
        return email.utils.parsedate_to_datetime(date_str)
    except Exception:
        # Fallback: try common formats
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return datetime.now(timezone.utc)


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract plain text body from Gmail message payload.

    Handles both simple and multipart messages.
    Prefers text/plain over text/html.
    """
    mime_type = payload.get("mimeType", "")

    # Simple message with direct body
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return _decode_base64(data)

    # Multipart message
    parts = payload.get("parts", [])
    if parts:
        # First pass: look for text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return _decode_base64(data)

        # Second pass: look for text/html and strip tags
        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    html = _decode_base64(data)
                    return _strip_html(html)

        # Recursive: check nested multipart
        for part in parts:
            if "parts" in part:
                result = _extract_body(part)
                if result:
                    return result

    # Fallback for text/html at top level
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = _decode_base64(data)
            return _strip_html(html)

    return ""


def _has_attachments(payload: dict[str, Any]) -> bool:
    """Check if message has file attachments (beyond inline images)."""
    for part in payload.get("parts", []):
        filename = part.get("filename", "")
        if filename:
            return True
        if "parts" in part:
            if _has_attachments(part):
                return True
    return False


def _decode_base64(data: str) -> str:
    """Decode Gmail's URL-safe base64 encoded content."""
    try:
        # Gmail uses URL-safe base64 with = padding stripped
        decoded = base64.urlsafe_b64decode(data + "==")
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Strip HTML tags for plain text extraction. Simple but effective."""
    # Remove style and script blocks
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace br and p tags with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# _is_auth_error is imported from omnibrain.integrations (shared helper)

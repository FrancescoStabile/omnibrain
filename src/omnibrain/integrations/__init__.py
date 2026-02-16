"""OmniBrain integrations — external service connectors.

Available integrations:
    gmail       — GmailClient for fetching and searching emails
    calendar    — CalendarClient for fetching and searching events
    github      — (Phase 2)
"""

from omnibrain.integrations.gmail import GmailClient, GmailAuthError
from omnibrain.integrations.calendar import CalendarClient, CalendarAuthError

__all__ = ["GmailClient", "GmailAuthError", "CalendarClient", "CalendarAuthError"]
